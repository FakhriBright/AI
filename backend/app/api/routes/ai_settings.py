import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.db.session import get_db
from app.models.ai_provider_settings import AIProviderSettings
from app.models.user import User
from app.schemas.ai_settings import (
    AIConnectionTestRequest,
    AIConnectionTestResponse,
    AIModelListResponse,
    AIProviderInfo,
    AIProviderModelRef,
    AISettingsResponse,
    AISettingsUpdate,
)
from app.services.ai.errors import classify_error
from app.services.ai.factory import load_user_ai_settings
from app.services.ai.registry import (
    PROVIDER_LABELS,
    SELECTABLE_PROVIDERS,
    build_provider,
    default_model,
    fallback_order_default,
    is_configured,
    list_models,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai-settings"])

_TEST_PAYLOAD = {
    "system_instruction": "You are a connectivity check. Answer with one word.",
    "analysis_prompt": "Reply with the single word OK.",
    "max_tokens": 64,
}


def _label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider)


def _server_default() -> AIProviderModelRef:
    provider = settings.ai_provider
    model = default_model(provider) or ("mock-reasoning-v1" if provider == "mock" else "")
    return AIProviderModelRef(provider=provider, model=model)


def _settings_response(prefs: AIProviderSettings | None) -> AISettingsResponse:
    providers = [
        AIProviderInfo(
            id=p,
            label=_label(p),
            configured=is_configured(p),
            default_model=default_model(p),
        )
        for p in SELECTABLE_PROVIDERS
    ]
    server_default = _server_default()

    if prefs is None:
        return AISettingsResponse(
            provider=server_default.provider,
            model=server_default.model,
            model_by_provider={p: default_model(p) for p in SELECTABLE_PROVIDERS if default_model(p)},
            auto_switch=False,
            fallback_order=fallback_order_default(),
            source="server_default",
            server_default=server_default,
            providers=providers,
        )

    models = dict(prefs.model_by_provider or {})
    return AISettingsResponse(
        provider=prefs.provider,
        model=models.get(prefs.provider) or default_model(prefs.provider),
        model_by_provider=models,
        auto_switch=prefs.auto_switch,
        fallback_order=list(prefs.fallback_order or []),
        source="user",
        server_default=server_default,
        providers=providers,
        updated_at=prefs.updated_at.isoformat() if prefs.updated_at else None,
    )


@router.get("/settings", response_model=AISettingsResponse)
def get_ai_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _settings_response(load_user_ai_settings(db, current_user))


@router.put("/settings", response_model=AISettingsResponse)
async def update_ai_settings(
    payload: AISettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    provider = payload.provider
    if provider not in SELECTABLE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported AI provider: {provider!r}.")
    if not is_configured(provider):
        raise HTTPException(
            status_code=400,
            detail=f"{_label(provider)} API key is not configured on the server.",
        )

    models = {
        p: m.strip()
        for p, m in payload.model_by_provider.items()
        if p in SELECTABLE_PROVIDERS and isinstance(m, str) and m.strip()
    }
    if not models.get(provider):
        raise HTTPException(status_code=400, detail=f"Select a model for {_label(provider)}.")

    prefs = load_user_ai_settings(db, current_user)
    stored = dict(prefs.model_by_provider or {}) if prefs else {}

    # Validate the active model always, and any other entry that changed.
    for p, model in list(models.items()):
        if p != provider and stored.get(p) == model:
            continue
        if not is_configured(p):
            models.pop(p)
            continue
        listing = await list_models(p)
        if not listing.ok:
            raise HTTPException(
                status_code=502,
                detail=f"Cannot verify {_label(p)} models: {listing.error}",
            )
        if model not in listing.ids():
            raise HTTPException(
                status_code=400,
                detail=f"Model {model!r} is not available for the {_label(p)} API key.",
            )

    fallback_order: list[str] = []
    for p in payload.fallback_order:
        if p in SELECTABLE_PROVIDERS and p not in fallback_order:
            fallback_order.append(p)

    if prefs is None:
        prefs = AIProviderSettings(user_id=current_user.id)
        db.add(prefs)
    prefs.provider = provider
    prefs.model_by_provider = models
    prefs.auto_switch = payload.auto_switch
    prefs.fallback_order = fallback_order
    db.commit()
    db.refresh(prefs)

    logger.info(
        "AI_SETTINGS user=%s provider=%s model=%s auto_switch=%s fallback=%s",
        current_user.id, provider, models[provider], payload.auto_switch, fallback_order,
    )
    return _settings_response(prefs)


@router.get("/providers/{provider}/models", response_model=AIModelListResponse)
async def get_provider_models(
    provider: str,
    refresh: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
):
    if provider not in SELECTABLE_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown AI provider: {provider!r}.")

    listing = await list_models(provider, refresh=refresh)
    return AIModelListResponse(
        provider=provider,
        models=listing.models,
        source=listing.source,
        verified=listing.verified,
        error_kind=listing.error_kind,
        error=listing.error,
    )


@router.post("/test", response_model=AIConnectionTestResponse)
async def test_ai_connection(
    payload: AIConnectionTestRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Send a tiny prompt to exactly this provider/model — no fallback."""
    rate_limiter.check(request, custom_limit=10)

    provider, model = payload.provider, payload.model.strip()
    if provider not in SELECTABLE_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown AI provider: {provider!r}.")

    started = time.monotonic()
    try:
        response = await build_provider(provider, model).analyze(dict(_TEST_PAYLOAD))
    except Exception as exc:
        info = classify_error(exc)
        logger.warning(
            "AI_TEST provider=%s model=%s failed kind=%s status=%s",
            provider, model, info.kind, info.status_code,
        )
        return AIConnectionTestResponse(
            ok=False,
            provider=provider,
            model=model,
            error_kind=info.kind,
            message=info.message,
        )

    latency_ms = int((time.monotonic() - started) * 1000)
    return AIConnectionTestResponse(
        ok=True,
        provider=provider,
        model=response.model or model,
        latency_ms=latency_ms,
        message=f"Connected to {_label(provider)} ({latency_ms} ms).",
    )
