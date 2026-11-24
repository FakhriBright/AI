"""Catalog of the AI providers the dashboard can select, plus model discovery.

Models shown in the dashboard come from each provider's model-listing API
using the server's own key, so only models that key can actually use are
offered. An optional <PROVIDER>_MODELS allowlist in the environment narrows
that list, and is used on its own (marked unverified) only when discovery
is unreachable.
"""

import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import settings
from app.services.ai.base import AIProvider
from app.services.ai.errors import AIProviderConfigError, AIProviderHTTPError, classify_error

logger = logging.getLogger(__name__)

SELECTABLE_PROVIDERS: tuple[str, ...] = ("groq", "gemini", "openrouter")

PROVIDER_LABELS = {
    "groq": "Groq",
    "gemini": "Google Gemini",
    "openrouter": "OpenRouter",
    "mock": "Mock",
}

_DISCOVERY_TIMEOUT_SECONDS = 15.0

# Ids that the listing APIs return but that cannot serve chat completions
# (speech, safety classifiers, embeddings, image/music generation, agents).
_NON_CHAT_MARKERS = ("whisper", "tts", "orpheus", "playai", "guard", "embedding", "embed",
                     "imagen", "veo", "image-generation", "aqa", "live", "-image",
                     "transcribe", "lyria", "nano-banana", "computer-use", "robotics",
                     "deep-research", "antigravity")


def provider_api_key(provider: str) -> str:
    if provider == "groq":
        return settings.groq_api_key
    if provider == "gemini":
        return settings.gemini_api_key or settings.ai_api_key
    if provider == "openrouter":
        return settings.openrouter_api_key
    return ""


def is_configured(provider: str) -> bool:
    return bool(provider_api_key(provider))


def default_model(provider: str) -> str:
    return {
        "groq": settings.groq_model,
        "gemini": settings.gemini_model,
        "openrouter": settings.openrouter_model,
    }.get(provider, "")


def configured_models(provider: str) -> list[str]:
    raw = getattr(settings, f"{provider}_models", "") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def fallback_order_default() -> list[str]:
    order = [p.strip() for p in settings.ai_fallback_order.split(",") if p.strip()]
    return [p for p in order if p in SELECTABLE_PROVIDERS]


@lru_cache(maxsize=32)
def build_provider(provider: str, model: str | None = None) -> AIProvider:
    """One client per (provider, model); construction errors are not cached."""
    if provider == "groq":
        from app.services.ai.groq_provider import GroqAIProvider
        return GroqAIProvider(model=model)

    if provider == "gemini":
        from app.services.ai.gemini_provider import GeminiAIProvider
        return GeminiAIProvider(model=model)

    if provider == "openrouter":
        from app.services.ai.openrouter_provider import OpenRouterAIProvider
        return OpenRouterAIProvider(model=model)

    raise AIProviderConfigError(f"Unknown AI provider: {provider!r}")


# --------------------------------------------------------------------------
# Model discovery
# --------------------------------------------------------------------------

@dataclass
class ModelListing:
    provider: str
    models: list[dict[str, Any]] = field(default_factory=list)
    source: str = "discovery"  # "discovery" | "configured"
    verified: bool = True
    error_kind: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_kind is None

    def ids(self) -> set[str]:
        return {m["id"] for m in self.models}


_MODEL_CACHE: dict[str, tuple[float, ModelListing]] = {}


def clear_model_cache() -> None:
    _MODEL_CACHE.clear()


def _is_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NON_CHAT_MARKERS)


async def _get_json(client: httpx.AsyncClient, provider: str, url: str, **kwargs) -> dict[str, Any]:
    response = await client.get(url, **kwargs)
    if response.status_code >= 400:
        raise AIProviderHTTPError(provider, response.status_code)
    return response.json()


async def _discover_groq(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    data = await _get_json(
        client, "groq", "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
    )
    models = []
    for item in data.get("data") or []:
        model_id = item.get("id")
        if not model_id or item.get("active") is False or not _is_chat_model(model_id):
            continue
        models.append({
            "id": model_id,
            "name": model_id,
            "context_length": item.get("context_window"),
            "free": None,
        })
    return sorted(models, key=lambda m: m["id"])


async def _discover_gemini(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    models = []
    page_token = None
    for _ in range(5):
        params = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        data = await _get_json(
            client, "gemini", "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": provider_api_key("gemini")},
            params=params,
        )
        for item in data.get("models") or []:
            model_id = (item.get("name") or "").removeprefix("models/")
            methods = item.get("supportedGenerationMethods") or []
            if not model_id or "generateContent" not in methods or not _is_chat_model(model_id):
                continue
            models.append({
                "id": model_id,
                "name": item.get("displayName") or model_id,
                "context_length": item.get("inputTokenLimit"),
                "free": None,
            })
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return sorted(models, key=lambda m: m["id"])


def _is_free(pricing: dict[str, Any]) -> bool:
    try:
        return float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0
    except (TypeError, ValueError):
        return False


async def _openrouter_key_info(client: httpx.AsyncClient, base: str, headers: dict[str, str]) -> dict[str, Any]:
    try:
        data = await _get_json(client, "openrouter", f"{base}/key", headers=headers)
    except AIProviderHTTPError as exc:
        if exc.status_code != 404:
            raise
        data = await _get_json(client, "openrouter", f"{base}/auth/key", headers=headers)
    return data.get("data") or {}


async def _discover_openrouter(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    base = settings.openrouter_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}

    # The key endpoint validates the key and tells us whether it can use paid
    # models at all. A free-tier key (no credits) only gets ":free"-priced models.
    key_info = await _openrouter_key_info(client, base, headers)
    remaining = key_info.get("limit_remaining")
    free_only = bool(key_info.get("is_free_tier")) or (
        isinstance(remaining, (int, float)) and remaining <= 0
    )

    data = await _get_json(client, "openrouter", f"{base}/models", headers=headers)
    models = []
    for item in data.get("data") or []:
        model_id = item.get("id")
        architecture = item.get("architecture") or {}
        outputs = architecture.get("output_modalities") or []
        text_out = "text" in outputs if outputs else str(architecture.get("modality", "")).endswith("->text")
        if not model_id or not text_out or not _is_chat_model(model_id):
            continue
        free = _is_free(item.get("pricing") or {})
        if free_only and not free:
            continue
        models.append({
            "id": model_id,
            "name": item.get("name") or model_id,
            "context_length": item.get("context_length"),
            "free": free,
        })
    return sorted(models, key=lambda m: m["id"])


_DISCOVERERS = {
    "groq": _discover_groq,
    "gemini": _discover_gemini,
    "openrouter": _discover_openrouter,
}


async def list_models(provider: str, *, refresh: bool = False) -> ModelListing:
    if provider not in SELECTABLE_PROVIDERS:
        return ModelListing(provider, error_kind="config", error="Unknown provider.")
    if not is_configured(provider):
        return ModelListing(provider, error_kind="config",
                            error="API key is not configured on the server.")

    cached = _MODEL_CACHE.get(provider)
    if cached and not refresh and cached[0] > time.monotonic():
        return cached[1]

    allowlist = configured_models(provider)
    try:
        async with httpx.AsyncClient(timeout=_DISCOVERY_TIMEOUT_SECONDS) as client:
            discovered = await _DISCOVERERS[provider](client)
    except Exception as exc:
        info = classify_error(exc)
        logger.warning("AI model discovery failed provider=%s kind=%s status=%s",
                       provider, info.kind, info.status_code)
        # If the listing API is merely unreachable, fall back to the models set
        # in .env (allowlist + default) so manual selection still works; Test
        # Connection verifies them. An invalid key or exhausted credits is
        # reported as-is and never masked by configured models.
        fallback = list(dict.fromkeys(allowlist + [default_model(provider)]))
        fallback = [m for m in fallback if m]
        if fallback and info.kind in {"timeout", "connection", "server", "rate_limit"}:
            return ModelListing(
                provider,
                models=[{"id": m, "name": m, "context_length": None, "free": None} for m in fallback],
                source="configured",
                verified=False,
                error_kind=None,
                error="Model discovery unavailable; showing configured models (unverified).",
            )
        return ModelListing(provider, error_kind=info.kind, error=info.message)

    if allowlist:
        allowed = set(allowlist)
        discovered = [m for m in discovered if m["id"] in allowed]

    listing = ModelListing(provider, models=discovered)
    _MODEL_CACHE[provider] = (time.monotonic() + settings.ai_model_cache_seconds, listing)
    return listing
