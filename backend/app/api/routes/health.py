from fastapi import APIRouter, Depends

from app.services.market_data.base import MarketDataProvider, MarketDataUnavailable
from app.services.market_data.factory import get_market_data_provider

router = APIRouter(tags=["health"])


@router.get("/health")
def app_health() -> dict:
    return {"status": "ok"}


@router.get("/health/market-data")
async def market_data_health(
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> dict:
    """
    Surfaces the MT5 bridge's own health rather than assuming it's up.
    Never fabricates a connected status if the bridge can't be reached.
    """
    try:
        health = await provider.health()
        return health.model_dump(mode="json")
    except MarketDataUnavailable as exc:
        return {
            "bridge_status": "down",
            "data_source_connected": False,
            "error": exc.reason,
            "retryable": exc.retryable,
        }
