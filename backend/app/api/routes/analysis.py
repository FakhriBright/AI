from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.analysis import AnalysisResponse
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
