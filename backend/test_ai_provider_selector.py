"""Unit tests for the multi-provider selector (no network, no DB).

Run inside the backend container:
    python test_ai_provider_selector.py
"""

import asyncio
from types import SimpleNamespace

import httpx

from app.core.config import settings
from app.services.ai import openrouter_provider, registry
from app.services.ai.base import AIResponse
from app.services.ai.errors import AIProviderConfigError, AIProviderHTTPError, classify_error
from app.services.ai.factory import resolve_provider_chain
from app.services.ai.routing import RoutedAIProvider, clear_cooldowns

CTX = {"system_instruction": "sys", "analysis_prompt": "prompt", "max_tokens": 100}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

class StatusError(Exception):
    """Mimics SDK errors that expose `status_code` (Groq) or `code` (Gemini)."""

    def __init__(self, status_code=None, code=None, status="", message=""):
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.status = status
        self.message = message
        super().__init__(message)


class FakeProvider:
    def __init__(self, name, model, error=None, calls=None):
        self.provider, self.model = name, model
        self.error = error
        self.calls = calls if calls is not None else []

    async def analyze(self, context):
        self.calls.append(self.provider)
        if self.error is not None:
            raise self.error
        return AIResponse(provider=self.provider, model=self.model, analysis=f"from {self.provider}",
                          raw={"usage": {"type": "ACTUAL"}})


def make_router(errors, *, auto_switch=True, max_attempts=3, chain=None, builder_errors=None):
    calls = []
    chain = chain or [("groq", "g-model"), ("gemini", "gm-model"), ("openrouter", "or-model")]

    def builder(provider, model):
        if builder_errors and provider in builder_errors:
            raise builder_errors[provider]
        return FakeProvider(provider, model, error=errors.get(provider), calls=calls)

    routed = RoutedAIProvider(chain, auto_switch=auto_switch, max_attempts=max_attempts,
                              cooldown_seconds=60, builder=builder)
    return routed, calls


def run(coro):
    return asyncio.run(coro)


def mock_async_client(module, handler):
    """Make `module.httpx.AsyncClient(...)` use an in-memory transport."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    module.httpx.AsyncClient = factory
    return lambda: setattr(module.httpx, "AsyncClient", real)


# --------------------------------------------------------------------------
# error classification
# --------------------------------------------------------------------------

def test_classify_error_kinds():
    cases = [
        (StatusError(status_code=429, message="Rate limit reached for model"), "rate_limit", True),
        (StatusError(code=429, status="RESOURCE_EXHAUSTED", message="Quota exceeded"), "quota", True),
        (AIProviderHTTPError("openrouter", 402, "Insufficient credits"), "quota", True),
        (StatusError(status_code=401), "auth", False),
        (StatusError(code=400, status="INVALID_ARGUMENT", message="API key not valid."), "auth", False),
        (StatusError(status_code=400, message="bad field"), "bad_request", False),
        (StatusError(status_code=404), "model_not_found", False),
        (StatusError(status_code=413), "request_too_large", False),
        (StatusError(status_code=503), "server", True),
        (httpx.ConnectError("refused"), "connection", True),
        (httpx.ReadTimeout("slow"), "timeout", True),
        (asyncio.TimeoutError(), "timeout", True),
        (RuntimeError("GROQ_API_KEY is not configured."), "config", False),
        (AIProviderConfigError("no model"), "config", False),
        (ValueError("boom"), "unknown", False),
    ]
    for exc, kind, retryable in cases:
        info = classify_error(exc)
        assert info.kind == kind, (exc, info)
        assert info.retryable is retryable, (exc, info)
        assert info.message  # always a safe, non-empty message


def test_safe_message_never_echoes_exception_text():
    secret = "sk-or-v1-THIS-MUST-NOT-LEAK"
    info = classify_error(StatusError(status_code=401, message=f"bad key {secret}"))
    assert secret not in info.message


# --------------------------------------------------------------------------
# routing / auto switch
# --------------------------------------------------------------------------

def test_auto_switch_off_never_falls_back():
    clear_cooldowns()
    routed, calls = make_router({"groq": StatusError(status_code=429)}, auto_switch=False)
    try:
        run(routed.analyze(CTX))
        raise AssertionError("expected the selected provider's error")
    except StatusError as exc:
        assert exc.status_code == 429
    assert calls == ["groq"]


def test_auto_switch_off_annotates_success():
    clear_cooldowns()
    routed, calls = make_router({}, auto_switch=False)
    response = run(routed.analyze(CTX))
    assert response.provider == "groq"
    routing = response.raw["provider_routing"]
    assert routing["fallback_used"] is False and routing["served_by_provider"] == "groq"
    assert response.raw["usage"] == {"type": "ACTUAL"}  # provider raw is preserved


def test_rate_limit_falls_back_and_records_actual_provider():
    clear_cooldowns()
    routed, calls = make_router({"groq": StatusError(status_code=429)})
    response = run(routed.analyze(CTX))
    assert calls == ["groq", "gemini"]
    assert (response.provider, response.model) == ("gemini", "gm-model")
    routing = response.raw["provider_routing"]
    assert routing["requested_provider"] == "groq"
    assert routing["served_by_provider"] == "gemini"
    assert routing["fallback_used"] is True
    assert routing["attempts"][0]["error_kind"] == "rate_limit"
    # Pipeline identity (cache fingerprint) stays the user's selection.
    assert (routed.provider, routed.model) == ("groq", "g-model")


def test_quota_falls_back():
    clear_cooldowns()
    routed, calls = make_router({"groq": StatusError(code=429, status="RESOURCE_EXHAUSTED", message="quota")})
    assert run(routed.analyze(CTX)).provider == "gemini"


def test_cooldown_skips_rate_limited_provider_on_next_request():
    clear_cooldowns()
    routed, calls = make_router({"groq": StatusError(status_code=429)})
    run(routed.analyze(CTX))
    routed2, calls2 = make_router({})
    response = run(routed2.analyze(CTX))
    assert calls2 == ["gemini"], calls2
    assert response.raw["provider_routing"]["attempts"][0]["outcome"] == "skipped_cooldown"
    clear_cooldowns()


def test_request_errors_do_not_fall_back():
    for status in (400, 401, 404, 413):
        clear_cooldowns()
        routed, calls = make_router({"groq": StatusError(status_code=status)})
        try:
            run(routed.analyze(CTX))
            raise AssertionError(f"expected HTTP {status} to propagate")
        except StatusError as exc:
            assert exc.status_code == status  # 413 must stay intact for reasoning.py's retry
        assert calls == ["groq"], (status, calls)


def test_server_errors_respect_max_attempts():
    clear_cooldowns()
    errors = {p: StatusError(status_code=503) for p in ("groq", "gemini", "openrouter")}
    routed, calls = make_router(errors, max_attempts=2)
    try:
        run(routed.analyze(CTX))
        raise AssertionError("expected failure")
    except StatusError:
        pass
    assert calls == ["groq", "gemini"]


def test_unusable_fallback_is_skipped():
    clear_cooldowns()
    routed, calls = make_router(
        {"groq": StatusError(status_code=503)},
        builder_errors={"gemini": RuntimeError("GEMINI_API_KEY (or legacy AI_API_KEY) is not configured")},
    )
    response = run(routed.analyze(CTX))
    assert response.provider == "openrouter"
    assert calls == ["groq", "openrouter"]


def test_resolve_provider_chain():
    saved = (settings.groq_api_key, settings.gemini_api_key, settings.ai_api_key, settings.openrouter_api_key)
    try:
        settings.groq_api_key, settings.gemini_api_key, settings.ai_api_key = "k", "", "legacy"
        settings.openrouter_api_key = ""
        prefs = SimpleNamespace(
            provider="groq",
            model_by_provider={"groq": "g1", "openrouter": "o1"},
            auto_switch=True,
            fallback_order=["groq", "openrouter", "gemini", "bogus"],
        )
        chain = resolve_provider_chain(prefs)
        # openrouter has no key -> skipped; gemini uses legacy AI_API_KEY + default model.
        assert chain == [("groq", "g1"), ("gemini", settings.gemini_model)], chain

        prefs.auto_switch = False
        assert resolve_provider_chain(prefs) == [("groq", "g1")]
    finally:
        (settings.groq_api_key, settings.gemini_api_key, settings.ai_api_key,
         settings.openrouter_api_key) = saved


# --------------------------------------------------------------------------
# OpenRouter provider
# --------------------------------------------------------------------------

def _with_openrouter_key(fn):
    def wrapper():
        saved = settings.openrouter_api_key
        settings.openrouter_api_key = "sk-or-test"
        try:
            fn()
        finally:
            settings.openrouter_api_key = saved
    wrapper.__name__ = fn.__name__
    return wrapper


@_with_openrouter_key
def test_openrouter_success_matches_contract():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={
            "id": "gen-1", "model": "meta/llama-test",
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        })

    restore = mock_async_client(openrouter_provider, handler)
    try:
        response = run(openrouter_provider.OpenRouterAIProvider(model="meta/llama-test").analyze(CTX))
    finally:
        restore()

    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-or-test"
    body = seen["body"].replace(" ", "")
    assert '"role":"system"' in body
    assert f'"max_tokens":{100 + settings.ai_reasoning_tokens}' in body, body
    assert (response.provider, response.model, response.analysis) == ("openrouter", "meta/llama-test", "hello")
    assert response.raw["usage"] == {"type": "ACTUAL", "prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}


@_with_openrouter_key
def test_openrouter_errors_are_classified():
    for status, body, kind in [
        (402, {"error": {"code": 402, "message": "Insufficient credits"}}, "quota"),
        (429, {"error": {"code": 429, "message": "Rate limit exceeded"}}, "rate_limit"),
        (401, {"error": {"code": 401, "message": "No auth credentials found"}}, "auth"),
        (200, {"error": {"code": 502, "message": "upstream failed"}}, "server"),
    ]:
        restore = mock_async_client(openrouter_provider, lambda r, s=status, b=body: httpx.Response(s, json=b))
        try:
            run(openrouter_provider.OpenRouterAIProvider(model="x/y").analyze(CTX))
            raise AssertionError("expected error")
        except AIProviderHTTPError as exc:
            assert classify_error(exc).kind == kind, (status, exc)
            assert "sk-or-test" not in str(exc)
        finally:
            restore()


@_with_openrouter_key
def test_openrouter_requires_model():
    saved = settings.openrouter_model
    settings.openrouter_model = ""
    try:
        openrouter_provider.OpenRouterAIProvider()
        raise AssertionError("expected config error")
    except AIProviderConfigError:
        pass
    finally:
        settings.openrouter_model = saved


# --------------------------------------------------------------------------
# model discovery
# --------------------------------------------------------------------------

_OR_MODELS = {"data": [
    {"id": "paid/model", "name": "Paid", "context_length": 8000,
     "pricing": {"prompt": "0.000001", "completion": "0.000002"},
     "architecture": {"output_modalities": ["text"]}},
    {"id": "free/model:free", "name": "Free", "context_length": 4000,
     "pricing": {"prompt": "0", "completion": "0"},
     "architecture": {"output_modalities": ["text"]}},
    {"id": "image/model", "name": "Img", "pricing": {"prompt": "0", "completion": "0"},
     "architecture": {"output_modalities": ["image"]}},
]}


def _openrouter_handler(key_data, key_status=200):
    def handler(request):
        if request.url.path.endswith("/key"):
            return httpx.Response(key_status, json={"data": key_data})
        return httpx.Response(200, json=_OR_MODELS)
    return handler


@_with_openrouter_key
def test_openrouter_free_tier_only_lists_free_text_models():
    registry.clear_model_cache()
    restore = mock_async_client(registry, _openrouter_handler({"is_free_tier": True, "limit_remaining": None}))
    try:
        listing = run(registry.list_models("openrouter", refresh=True))
    finally:
        restore()
    assert listing.ok and listing.ids() == {"free/model:free"}, listing


@_with_openrouter_key
def test_openrouter_paid_key_lists_all_text_models():
    registry.clear_model_cache()
    restore = mock_async_client(registry, _openrouter_handler({"is_free_tier": False, "limit_remaining": 5.0}))
    try:
        listing = run(registry.list_models("openrouter", refresh=True))
    finally:
        restore()
    assert listing.ids() == {"paid/model", "free/model:free"}, listing


@_with_openrouter_key
def test_invalid_key_returns_error_not_models():
    registry.clear_model_cache()
    saved = settings.openrouter_models
    settings.openrouter_models = "paid/model"  # allowlist must not mask an invalid key
    restore = mock_async_client(registry, _openrouter_handler({}, key_status=401))
    try:
        listing = run(registry.list_models("openrouter", refresh=True))
    finally:
        restore()
        settings.openrouter_models = saved
    assert not listing.ok and listing.error_kind == "auth" and listing.models == []


def test_groq_discovery_filters_and_allowlist():
    registry.clear_model_cache()
    saved = (settings.groq_api_key, settings.groq_models)
    settings.groq_api_key, settings.groq_models = "gsk-test", ""

    def handler(request):
        assert request.headers["authorization"] == "Bearer gsk-test"
        return httpx.Response(200, json={"data": [
            {"id": "openai/gpt-oss-120b", "active": True, "context_window": 131072},
            {"id": "whisper-large-v3", "active": True},
            {"id": "meta-llama/llama-guard-4-12b", "active": True},
            {"id": "old-model", "active": False},
            {"id": "llama-3.3-70b-versatile", "active": True},
        ]})

    restore = mock_async_client(registry, handler)
    try:
        listing = run(registry.list_models("groq", refresh=True))
        assert listing.ids() == {"openai/gpt-oss-120b", "llama-3.3-70b-versatile"}, listing

        settings.groq_models = "llama-3.3-70b-versatile, not-on-account"
        listing = run(registry.list_models("groq", refresh=True))
        assert listing.ids() == {"llama-3.3-70b-versatile"}, listing
    finally:
        restore()
        settings.groq_api_key, settings.groq_models = saved
        registry.clear_model_cache()


def test_discovery_outage_uses_configured_models_unverified():
    registry.clear_model_cache()
    saved = (settings.groq_api_key, settings.groq_models, settings.groq_model)
    settings.groq_api_key, settings.groq_model = "gsk-test", "openai/gpt-oss-120b"

    def handler(request):
        raise httpx.ConnectError("down")

    restore = mock_async_client(registry, handler)
    try:
        settings.groq_models = "llama-3.3-70b-versatile"
        listing = run(registry.list_models("groq", refresh=True))
        assert listing.ok and listing.source == "configured" and listing.verified is False
        assert listing.ids() == {"llama-3.3-70b-versatile", "openai/gpt-oss-120b"}, listing

        # Without an allowlist the .env default model is still selectable.
        settings.groq_models = ""
        listing = run(registry.list_models("groq", refresh=True))
        assert listing.ok and listing.ids() == {"openai/gpt-oss-120b"}, listing
    finally:
        restore()
        settings.groq_api_key, settings.groq_models, settings.groq_model = saved
        registry.clear_model_cache()


def test_gemini_adds_reasoning_allowance_and_reports_finish_reason():
    from app.services.ai.gemini_provider import GeminiAIProvider

    saved = (settings.gemini_api_key, settings.ai_reasoning_tokens)
    settings.gemini_api_key, settings.ai_reasoning_tokens = "test-key", 6144
    seen = {}

    async def fake_generate_content(model, contents, config=None):
        seen["model"], seen["max_output_tokens"] = model, config.max_output_tokens
        return SimpleNamespace(
            text="analysis",
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(value="STOP"))],
            usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=5, total_token_count=900),
        )

    try:
        provider = GeminiAIProvider(model="gemini-x")
        provider.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content)))
        response = run(provider.analyze(CTX))
    finally:
        settings.gemini_api_key, settings.ai_reasoning_tokens = saved

    assert seen == {"model": "gemini-x", "max_output_tokens": 100 + 6144}, seen
    assert (response.provider, response.model) == ("gemini", "gemini-x")
    assert response.raw["finish_reason"] == "STOP"


def test_unconfigured_provider_lists_nothing():
    saved = settings.openrouter_api_key
    settings.openrouter_api_key = ""
    try:
        listing = run(registry.list_models("openrouter"))
    finally:
        settings.openrouter_api_key = saved
    assert listing.error_kind == "config" and listing.models == []


def main():
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
