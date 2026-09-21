from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.services.market_data.base import MarketDataUnavailable


router = APIRouter(prefix="/market", tags=["market"])


def get_provider() -> MT5BridgeProvider:
    return MT5BridgeProvider(
        base_url=settings.mt5_bridge_url,
        timeout_seconds=settings.mt5_bridge_timeout_seconds,
    )


@router.get("/health")
async def market_health():
    provider = get_provider()

    try:
        return await provider.health()
    except MarketDataUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "retryable": exc.retryable,
            },
        )
    finally:
        await provider.aclose()


@router.get("/symbols")
async def market_symbols():
    provider = get_provider()

    try:
        return {"symbols": await provider.list_symbols()}
    except MarketDataUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "retryable": exc.retryable,
            },
        )
    finally:
        await provider.aclose()


@router.get("/candles")
async def market_candles(
    symbol: str,
    timeframe: str,
    count: int = Query(default=100, ge=1, le=5000),
):
    provider = get_provider()

    try:
        candles = await provider.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            count=count,
        )

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(candles),
            "candles": candles,
        }

    except MarketDataUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "retryable": exc.retryable,
            },
        )
    finally:
        await provider.aclose()


@router.get("/tick")
async def market_tick(symbol: str):
    provider = get_provider()

    try:
        return await provider.get_tick(symbol)
    except MarketDataUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "retryable": exc.retryable,
            },
        )
    finally:
        await provider.aclose()


@router.get("/symbols/{symbol}/info")
async def market_symbol_info(symbol: str):
    provider = get_provider()

    try:
        return await provider.symbol_info(symbol)
    except MarketDataUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "retryable": exc.retryable,
            },
        )
    finally:
        await provider.aclose()
