from functools import lru_cache

from app.core.config import settings
from app.services.ai.anthropic_provider import AnthropicAIProvider
from app.services.ai.base import AIProvider
from app.services.ai.gemini_provider import GeminiAIProvider
from app.services.ai.mock_provider import MockAIProvider


@lru_cache
def get_ai_provider() -> AIProvider:

    if settings.ai_provider == "gemini":
        return GeminiAIProvider()

    if settings.ai_provider == "anthropic":
        return AnthropicAIProvider()

    if settings.ai_provider == "mock":
        return MockAIProvider()

    raise ValueError(
        f"Unknown AI_PROVIDER: {settings.ai_provider}"
    )
