from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_provider_settings import AIProviderSettings
from app.models.user import User
from app.services.ai.base import AIProvider
from app.services.ai.gemini_provider import GeminiAIProvider
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.registry import (
    SELECTABLE_PROVIDERS,
    build_provider,
    default_model,
    is_configured,
)
from app.services.ai.routing import RoutedAIProvider

# Gemini and Groq are the production AI providers. Anthropic support existed
# in an earlier iteration (backend/app/services/ai/anthropic_provider.py
# remains on disk for reference) but is intentionally not imported or
# selectable here, so there is no accidental runtime switch to it.


@lru_cache
def get_ai_provider() -> AIProvider:

    if settings.ai_provider == "gemini":
        # No silent fallback to a mock/other provider if the API key is
        # missing. GeminiAIProvider itself raises a clear RuntimeError in
        # that case, which the API layer turns into a controlled 502
        # "AI service misconfigured" response — never a response that looks
        # like a real AI answer.
        return GeminiAIProvider()

    if settings.ai_provider == "groq":
        from app.services.ai.groq_provider import GroqAIProvider
        return GroqAIProvider()

    if settings.ai_provider == "openrouter":
        from app.services.ai.openrouter_provider import OpenRouterAIProvider
        return OpenRouterAIProvider()

    if settings.ai_provider == "mock":
        # Explicit opt-in only (AI_PROVIDER=mock), for local development and
        # automated tests without a live Gemini API key. Never selected as a
        # side effect of another provider failing.
        return MockAIProvider(provider="mock", model="mock-reasoning-v1")

    raise ValueError(
        f"Unknown AI_PROVIDER: {settings.ai_provider!r}. "
        "Supported values in this build: 'gemini', 'groq', 'openrouter', 'mock'."
    )


def load_user_ai_settings(db: Session, user: User) -> AIProviderSettings | None:
    return db.scalar(
        select(AIProviderSettings).where(AIProviderSettings.user_id == user.id)
    )


def resolve_provider_chain(prefs: AIProviderSettings) -> list[tuple[str, str]]:
    """(provider, model) pairs: the user's selection first, then fallbacks."""
    models = prefs.model_by_provider or {}
    chain = [(prefs.provider, models.get(prefs.provider) or default_model(prefs.provider))]

    if prefs.auto_switch:
        for provider in prefs.fallback_order or []:
            if provider in SELECTABLE_PROVIDERS and provider not in {p for p, _ in chain}:
                model = models.get(provider) or default_model(provider)
                if model and is_configured(provider):
                    chain.append((provider, model))

    return chain


def get_ai_provider_for_user(db: Session, user: User) -> AIProvider:
    """Provider for AI endpoints, honoring the user's dashboard selection.

    Users who never saved AI settings keep the server default (AI_PROVIDER),
    exactly as before the selector existed.
    """
    prefs = load_user_ai_settings(db, user)
    if prefs is None:
        return get_ai_provider()

    return RoutedAIProvider(
        resolve_provider_chain(prefs),
        auto_switch=prefs.auto_switch,
        max_attempts=settings.ai_fallback_max_attempts,
        cooldown_seconds=settings.ai_provider_cooldown_seconds,
        builder=build_provider,
    )

