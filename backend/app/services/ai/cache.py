from collections import OrderedDict
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from typing import Any

from app.services.ai.base import AIResponse
from app.services.ai.serializer import dumps_compact, fingerprint_context


_MAX_ENTRIES = 64
_CACHE: OrderedDict[str, AIResponse] = OrderedDict()


def make_analysis_fingerprint(
    ai_context: dict[str, Any],
    *,
    provider_name: str,
    model: str,
) -> str:
    payload = {
        "provider": provider_name,
        "model": model,
        "context": fingerprint_context(ai_context),
    }
    blob = dumps_compact(payload)
    return sha256(blob.encode("utf-8")).hexdigest()


def get_cached_analysis(fingerprint: str) -> AIResponse | None:
    cached = _CACHE.get(fingerprint)
    if cached is None:
        return None

    _CACHE.move_to_end(fingerprint)
    return replace(
        cached,
        raw=deepcopy(cached.raw) if cached.raw is not None else None,
    )


def store_cached_analysis(fingerprint: str, response: AIResponse) -> None:
    stored = replace(
        response,
        raw=deepcopy(response.raw) if response.raw is not None else None,
    )
    _CACHE[fingerprint] = stored
    _CACHE.move_to_end(fingerprint)

    while len(_CACHE) > _MAX_ENTRIES:
        _CACHE.popitem(last=False)


def clear_analysis_cache() -> None:
    _CACHE.clear()


def analysis_cache_size() -> int:
    return len(_CACHE)
