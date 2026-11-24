"""Provider-neutral classification of AI provider failures.

Groq, Gemini and the httpx-based providers raise different exception types.
Routing (auto switch) and the settings API only need to know *what kind* of
failure happened, plus a message that is safe to show in the dashboard.
Raw exception text is never returned to the client.
"""

import asyncio
from dataclasses import dataclass

import httpx


class AIProviderHTTPError(Exception):
    """Non-2xx answer from an httpx-based provider.

    Exposes `status_code` like the Groq SDK errors do, so the existing 413
    retry in reasoning.py and the chat route's status mapping keep working.
    """

    def __init__(self, provider: str, status_code: int, message: str = ""):
        self.provider = provider
        self.status_code = status_code
        self.message = (message or "")[:300]
        super().__init__(f"{provider} HTTP {status_code}: {self.message}")


class AIProviderConfigError(RuntimeError):
    """Provider cannot be used as configured (missing key, unknown provider/model)."""


@dataclass(frozen=True)
class ProviderErrorInfo:
    kind: str
    status_code: int | None
    retryable: bool
    message: str


SAFE_MESSAGES = {
    "auth": "API key is invalid or not authorized for this provider.",
    "quota": "Quota exhausted or insufficient credits for this provider.",
    "rate_limit": "Rate limit reached. Please wait and retry.",
    "server": "Provider is temporarily unavailable (server error).",
    "timeout": "Provider request timed out.",
    "connection": "Could not connect to the provider.",
    "model_not_found": "Model is not available for this API key.",
    "request_too_large": "Request is too large for this model.",
    "bad_request": "Provider rejected the request.",
    "config": "Provider is not configured on the server (missing API key or model).",
    "unknown": "Unexpected provider error.",
}

# Failures another provider may not share: fallback is allowed for these.
RETRYABLE_KINDS = {"rate_limit", "quota", "server", "timeout", "connection"}

_QUOTA_HINTS = (
    "quota",
    "resource_exhausted",
    "insufficient",
    "credit",
    "billing",
    "exceeded your current",
)
_AUTH_HINTS = ("api key not valid", "api_key_invalid", "invalid api key", "unauthorized")
_TIMEOUT_NAMES = {"APITimeoutError", "ReadTimeout", "ConnectTimeout", "Timeout", "TimeoutException"}
_CONNECTION_NAMES = {"APIConnectionError", "ConnectError", "ConnectionError", "RemoteProtocolError"}


def _status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def _text(exc: Exception) -> str:
    parts = [str(getattr(exc, "status", "") or ""), str(getattr(exc, "message", "") or ""), str(exc)]
    return " ".join(parts).lower()


def classify_error(exc: BaseException) -> ProviderErrorInfo:
    kind = _classify_kind(exc)
    return ProviderErrorInfo(
        kind=kind,
        status_code=_status_code(exc) if isinstance(exc, Exception) else None,
        retryable=kind in RETRYABLE_KINDS,
        message=SAFE_MESSAGES[kind],
    )


def _classify_kind(exc: BaseException) -> str:
    if isinstance(exc, AIProviderConfigError):
        return "config"

    names = {cls.__name__ for cls in type(exc).__mro__}
    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)) or names & _TIMEOUT_NAMES:
        return "timeout"

    status = _status_code(exc) if isinstance(exc, Exception) else None
    if status is None:
        if isinstance(exc, (httpx.TransportError, ConnectionError)) or names & _CONNECTION_NAMES:
            return "connection"
        if isinstance(exc, RuntimeError) and "not configured" in str(exc).lower():
            return "config"
        return "unknown"

    text = _text(exc)
    if status == 402:
        return "quota"
    if status == 429:
        return "quota" if any(h in text for h in _QUOTA_HINTS) else "rate_limit"
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "model_not_found"
    if status == 408:
        return "timeout"
    if status == 413:
        return "request_too_large"
    if status in (400, 422):
        return "auth" if any(h in text for h in _AUTH_HINTS) else "bad_request"
    if status >= 500:
        return "server"
    return "unknown"
