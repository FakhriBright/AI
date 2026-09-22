from functools import lru_cache

from app.core.config import settings
from app.services.ai.base import AIProvider
from app.services.ai.gemini_provider import GeminiAIProvider
from app.services.ai.mock_provider import MockAIProvider

# Gemini is the only production AI provider. Anthropic support existed in an
# earlier iteration (backend/app/services/ai/anthropic_provider.py remains on
# disk for reference) but is intentionally not imported or selectable here,
# so there is no accidental runtime switch to it.


@lru_cache
def get_ai_provider() -> AIProvider:

    if settings.ai_provider == "gemini":
        # No silent fallback to a mock/other provider if the API key is
        # missing. GeminiAIProvider itself raises a clear RuntimeError in
        # that case, which the API layer turns into a controlled 502
        # "AI service misconfigured" response — never a response that looks
        # like a real AI answer.
        return GeminiAIProvider()

    if settings.ai_provider == "mock":
        # Explicit opt-in only (AI_PROVIDER=mock), for local development and
        # automated tests without a live Gemini API key. Never selected as a
        # side effect of another provider failing.
        return MockAIProvider(provider="mock", model="mock-reasoning-v1")

    raise ValueError(
        f"Unknown AI_PROVIDER: {settings.ai_provider!r}. "
        "Supported values in this build: 'gemini', 'mock'."
    )

