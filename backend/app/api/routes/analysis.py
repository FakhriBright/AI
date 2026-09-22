from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.analysis import AnalysisResponse, AnalysisChatRequest, AnalysisChatResponse
from app.services.ai.factory import get_ai_provider
from app.services.ai.reasoning import AIReasoningService
from app.services.analysis.pipeline import AnalysisPipelineResult, analyze_symbol
from app.services.market_data.factory import get_market_data_provider
from app.services.market_data.base import MarketDataProvider


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
    )


@router.get(
    "/{symbol}",
    response_model=AnalysisResponse,
)
async def analyze_market(
    symbol: str,
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
    risk_settings = current_user.risk_settings
    risk_percent = (
        float(risk_settings.risk_percent)
        if risk_settings is not None
        else None
    )

    try:
        result = await analyze_symbol(
            symbol=symbol,
            provider=provider,
            ai_service=AIReasoningService(
                provider=get_ai_provider()
            ),
            risk_percent=risk_percent,
            count=count,
        )

        return _build_response(result)

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


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
    symbol: str | None = None,
    provider: MarketDataProvider = Depends(get_market_data_provider),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_symbol = symbol or payload.symbol

    try:
        ai_service = AIReasoningService(provider=get_ai_provider())
    except Exception as exc:
        # e.g. GeminiAIProvider raising because AI_API_KEY is not configured.
        # Controlled, explicit failure — never a response that looks like a
        # real AI answer.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # --- Server-side deterministic context (authoritative) ---
    # Always run the deterministic analysis pipeline to obtain fresh,
    # trustworthy market context. Client-provided analysis_context is
    # intentionally ignored — the AI must reason from server-verified data,
    # never from arbitrary payloads the browser could fabricate.
    risk_percent = (
        float(current_user.risk_settings.risk_percent)
        if current_user.risk_settings
        else None
    )
    try:
        result = await analyze_symbol(
            symbol=target_symbol,
            provider=provider,
            ai_service=ai_service,
            risk_percent=risk_percent,
            count=300,
        )
        context = _json_safe(result.ai_context)
    except Exception as exc:
        # Pipeline failure → controlled 502. Never send incomplete/error
        # data to Gemini and ask it to answer from that.
        raise HTTPException(
            status_code=502,
            detail="Live market analysis is unavailable.",
        ) from exc

    # --- Conversational reasoning layer ---
    # Any provider failure (missing key, network error, rate limit, outage)
    # propagates as a controlled 502 rather than a silently generated
    # fallback answer.
    history_dicts = [{"role": h.role, "content": h.content} for h in payload.history]
    try:
        ai_response = await ai_service.chat(
            context=context,
            message=payload.message,
            history=history_dicts,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AnalysisChatResponse(
        symbol=target_symbol,
        reply=ai_response.analysis,
        provider=ai_response.provider,
        model=ai_response.model,
    )

