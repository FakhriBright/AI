"""Per-user provider routing with optional Auto Switch.

RoutedAIProvider satisfies the same AIProvider contract as a single
provider, so AIReasoningService, the prompt and the pipeline are unchanged.

- Auto Switch off: only the user's provider/model is called. Its errors
  propagate unchanged (same behavior as a plain provider).
- Auto Switch on: on a retryable failure (rate limit, quota, server error,
  timeout, connection) the next provider in the user's fallback order is
  tried, at most `max_attempts` provider calls per request. Request and
  configuration errors (400/401/403/404/413, missing key) on the selected
  provider are raised immediately — another provider would not fix them.

Providers that just returned 429/quota are put on a short cooldown, so the
dashboard's periodic refresh does not hammer a provider that is out of quota.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from app.services.ai.base import AIProvider, AIResponse
from app.services.ai.errors import classify_error

logger = logging.getLogger(__name__)

_COOLDOWN_KINDS = {"rate_limit", "quota"}
# Errors that belong to the request itself: no provider would accept it.
_REQUEST_KINDS = {"bad_request", "request_too_large"}

_COOLDOWN_UNTIL: dict[str, float] = {}


def clear_cooldowns() -> None:
    _COOLDOWN_UNTIL.clear()


def _in_cooldown(provider: str) -> bool:
    return _COOLDOWN_UNTIL.get(provider, 0.0) > time.monotonic()


class RoutedAIProvider:

    def __init__(
        self,
        chain: list[tuple[str, str]],
        *,
        auto_switch: bool,
        max_attempts: int,
        cooldown_seconds: int,
        builder: Callable[[str, str], AIProvider],
    ):
        if not chain:
            raise ValueError("RoutedAIProvider needs at least one (provider, model)")

        self.chain = chain
        self.auto_switch = auto_switch
        self.max_attempts = max(1, max_attempts)
        self.cooldown_seconds = cooldown_seconds
        self._builder = builder

        # Identity used by the pipeline for cache fingerprints and metrics.
        self.provider, self.model = chain[0]

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

        if not self.auto_switch:
            provider, model = self.chain[0]
            response = await self._builder(provider, model).analyze(context)
            return self._annotate(response, attempts=[], fallback_used=False)

        attempts: list[dict[str, Any]] = []
        last_exc: BaseException | None = None
        calls = 0

        candidates = list(enumerate(self.chain))
        # If every candidate is cooling down, still try the selected provider once.
        if all(_in_cooldown(p) for _, (p, _m) in candidates):
            candidates = candidates[:1]
        else:
            skipped = [(i, pm) for i, pm in candidates if _in_cooldown(pm[0])]
            for _, (provider, model) in skipped:
                attempts.append({"provider": provider, "model": model, "outcome": "skipped_cooldown"})
            candidates = [(i, pm) for i, pm in candidates if not _in_cooldown(pm[0])]

        for index, (provider, model) in candidates:
            if calls >= self.max_attempts:
                break

            try:
                instance = self._builder(provider, model)
                calls += 1
                response = await instance.analyze(context)
            except Exception as exc:
                info = classify_error(exc)
                attempts.append({
                    "provider": provider,
                    "model": model,
                    "outcome": "error",
                    "error_kind": info.kind,
                    "status_code": info.status_code,
                })
                logger.warning(
                    "AI_ROUTING provider=%s model=%s failed kind=%s status=%s",
                    provider, model, info.kind, info.status_code,
                )

                if info.kind in _COOLDOWN_KINDS:
                    _COOLDOWN_UNTIL[provider] = time.monotonic() + self.cooldown_seconds

                is_selected = index == 0
                if info.kind in _REQUEST_KINDS or (is_selected and not info.retryable):
                    raise
                last_exc = exc
                continue

            _COOLDOWN_UNTIL.pop(provider, None)
            fallback_used = (provider, model) != self.chain[0]
            if fallback_used:
                logger.warning(
                    "AI_FALLBACK requested=%s/%s served_by=%s/%s",
                    self.provider, self.model, provider, model,
                )
            return self._annotate(response, attempts=attempts, fallback_used=fallback_used)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No AI provider available (all candidates cooling down or unconfigured)")

    def _annotate(
        self,
        response: AIResponse,
        *,
        attempts: list[dict[str, Any]],
        fallback_used: bool,
    ) -> AIResponse:
        raw = dict(response.raw or {})
        raw["provider_routing"] = {
            "requested_provider": self.provider,
            "requested_model": self.model,
            "served_by_provider": response.provider,
            "served_by_model": response.model,
            "auto_switch": self.auto_switch,
            "fallback_used": fallback_used,
            "attempts": attempts,
        }
        response.raw = raw
        return response
