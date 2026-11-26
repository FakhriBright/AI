import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limit import rate_limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.analysis import AnalysisResponse, AnalysisChatRequest, AnalysisChatResponse
from app.services.ai.chat_context import select_chat_context
from app.services.ai.factory import get_ai_provider_for_user
from app.services.ai.metrics import metrics_collector
from app.services.ai.reasoning import AIReasoningService
from app.services.analysis.pipeline import (
    AnalysisPipelineResult,
    analyze_symbol,
    get_deterministic_context,
)
from app.services.analysis.errors import market_data_error_detail
from app.services.chart.chat_commands import build_chat_chart_command
from app.services.chart.overlays import build_chart_overlays
from app.services.market_data.factory import get_market_data_provider
from app.services.market_data.base import MarketDataProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "item"):
        return _json_safe(value.item())

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())

    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))

    return value


def _chart_overlays(ai_context: dict[str, Any] | None) -> dict[str, Any] | None:
    # Drawing must never break the analysis response.
    try:
        return build_chart_overlays(ai_context) if ai_context else None
    except Exception:
        logger.exception("Chart overlay build failed")
        return None


def _build_response(
    result: AnalysisPipelineResult,
) -> AnalysisResponse:
    return AnalysisResponse(
        symbol=result.snapshot.symbol,
        generated_at_utc=_json_safe(
            result.snapshot.generated_at_utc
        ),
        market_bias=_json_safe(result.bias),
        multi_timeframe=_json_safe(result.context),
        key_levels=_json_safe(result.levels),
        scenarios=_json_safe(result.scenarios),
        selected_scenario=_json_safe(
            result.selected_scenario
        ),
        latest_candle=_json_safe(result.latest_candle),
        confirmation=_json_safe(result.confirmation),
        stop_plan=(
            _json_safe(result.stop_plan)
            if result.stop_plan is not None
            else None
        ),
        trade_plan=_json_safe(result.trade_plan),
        ai={
            "provider": result.ai_response.provider,
            "model": result.ai_response.model,
            "analysis": result.ai_response.analysis,
            "raw": _json_safe(result.ai_response.raw),
        },
        chart_overlays=_chart_overlays(_json_safe(result.ai_context)),
    )


@router.get(
    "/{symbol}",
    response_model=AnalysisResponse,
)
async def analyze_market(
    symbol: str,
    request: Request,
    count: int = Query(
        default=300,
        ge=200,
        le=1000,
    ),
    provider: MarketDataProvider = Depends(
        get_market_data_provider
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rate_limiter.check(request, custom_limit=20)
    risk_settings = current_user.risk_settings
    risk_percent = (
        float(risk_settings.risk_percent)
        if risk_settings is not None
        else None
    )

    try:
        # Deterministic only: no AI provider is created and no AI call is made
        # (auto-refresh, symbol switch and every dashboard load go through
        # here). AI runs only in the chat endpoint below, on a user message.
        result = await analyze_symbol(
            symbol=symbol,
            provider=provider,
            ai_service=None,
            risk_percent=risk_percent,
            count=count,
            run_ai=False,
        )

        return _build_response(result)

    except HTTPException:
        raise
    except Exception as exc:
        known = market_data_error_detail(exc)
        if known is not None:
            logger.warning("analyze_market data problem for %s: %s", symbol, exc)
            raise HTTPException(status_code=503, detail=known) from exc
        logger.exception("Unexpected error during analyze_market")
        raise HTTPException(
            status_code=502,
            detail="Market analysis temporarily unavailable",
        ) from exc


def _provider_http_status(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    try:
        status_code = int(status_code)
    except (TypeError, ValueError):
        status_code = None

    if status_code in {413, 429, 500, 502, 503, 504}:
        return status_code
    return None


def _chat_selection_context(det: Any) -> dict[str, Any]:
    """Selected scenario + confirmation of the SAME deterministic snapshot the
    dashboard shows (chart, Trade Plan), so the AI explains engine values
    instead of inferring its own setup."""
    sc = det.selected_scenario
    conf = det.confirmation
    return {
        "selected_scenario": {
            "name": sc.name,
            "direction": sc.direction,
            "status": sc.status,
            "trigger": sc.trigger,
            "trigger_reference": sc.trigger_reference,
            "trigger_confirmed": sc.trigger_confirmed,
            "breakout_status": sc.breakout_status,
            "invalidation": sc.invalidation,
            "invalidation_reference": sc.invalidation_reference,
            "conviction": sc.conviction,
        },
        "confirmation": {
            "confirmed": conf.confirmed,
            "confirmation_type": conf.confirmation_type,
            "entry_price": conf.entry_price,
            "reasons": list(conf.reasons)[:4],
        },
    }


@router.post(
    "/{symbol}/chat",
    response_model=AnalysisChatResponse,
)
@router.post(
    "/chat",
    response_model=AnalysisChatResponse,
)
async def chat_analysis(
    payload: AnalysisChatRequest,
    request: Request,
    symbol: str | None = None,
    provider: MarketDataProvider = Depends(get_market_data_provider),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rate_limiter.check(request, custom_limit=15)
    target_symbol = symbol or payload.symbol
    capped_message = payload.message.strip()[:500]

    try:
        ai_service = AIReasoningService(provider=get_ai_provider_for_user(db, current_user))
    except Exception as exc:
        logger.exception("Error initializing AI service for chat")
        raise HTTPException(status_code=502, detail="AI analysis temporarily unavailable") from exc

    risk_percent = (
        float(current_user.risk_settings.risk_percent)
        if current_user.risk_settings
        else None
    )
    try:
        det = await get_deterministic_context(
            symbol=target_symbol,
            provider=provider,
            risk_percent=risk_percent,
            count=300,
        )
        context = select_chat_context(
            det.ai_context,
            capped_message,
        )
        context.update(_chat_selection_context(det))
        context = _json_safe(context)
    except Exception as exc:
        known = market_data_error_detail(exc)
        if known is not None:
            logger.warning("chat data problem for %s: %s", target_symbol, exc)
            raise HTTPException(status_code=503, detail=known) from exc
        logger.exception("Error preparing context for chat")
        raise HTTPException(
            status_code=502,
            detail=f"Live market analysis is unavailable ({type(exc).__name__}).",
        ) from exc

    # Cap conversational history depth to last 4 messages to save prompt tokens
    history_dicts = [{"role": h.role, "content": h.content[:300]} for h in payload.history[-4:]]
    try:
        ai_response = await ai_service.chat(
            context=context,
            message=capped_message,
            history=history_dicts,
        )
        raw = ai_response.raw or {}
        usage = raw.get("usage", {})
        p_tok = usage.get("prompt_tokens", len(str(context)) // 4)
        c_tok = usage.get("completion_tokens", len(ai_response.analysis) // 4)
        t_type = usage.get("type", "ESTIMATED")
        metrics_collector.record_call(
            feature="AI Analyst Chat",
            provider=ai_response.provider,
            model=ai_response.model,
            cache_status="MISS",
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            token_type=t_type,
        )
    except Exception as exc:
        logger.exception("Error during AI chat completion")
        provider_status = _provider_http_status(exc)
        if provider_status is not None:
            if provider_status == 413:
                detail = "AI provider rejected the request because the payload is too large."
            elif provider_status == 429:
                detail = "AI provider rate limit reached. Please wait and retry."
            else:
                detail = "AI provider temporarily unavailable."
            raise HTTPException(status_code=provider_status, detail=detail) from exc

        raise HTTPException(
            status_code=502,
            detail="AI analysis temporarily unavailable.",
        ) from exc

    chart = None
    try:
        full_context = _json_safe(det.ai_context)
        overlays = build_chart_overlays(full_context)
        chart = {
            **build_chat_chart_command(capped_message, ai_response.analysis, overlays, full_context),
            "overlay_payload": overlays,
        }
    except Exception:
        logger.exception("Chat chart command build failed")

    return AnalysisChatResponse(
        symbol=target_symbol,
        reply=ai_response.analysis,
        provider=ai_response.provider,
        model=ai_response.model,
        chart=chart,
    )
