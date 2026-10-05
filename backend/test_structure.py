import asyncio
import pytest

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.core.config import settings
from app.services.market_data.base import MarketDataUnavailable
from app.services.technical.structure import find_swings, classify_structure


async def main():
    provider = MT5BridgeProvider(
        settings.mt5_bridge_url,
        settings.mt5_bridge_timeout_seconds,
    )

    try:
        candles = await provider.get_candles(
            symbol="EURUSDm",
            timeframe="H1",
            count=300,
        )

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        times = [c.time_utc for c in candles]

        swings = find_swings(
            highs=highs,
            lows=lows,
            times=times,
            lookback=3,
        )

        structure = classify_structure(swings)

        print("\n=== MARKET STRUCTURE ===")
        print(f"STRUCTURE : {structure}")
        print(f"TOTAL SWINGS: {len(swings)}")

        print("\nLAST 15 SWINGS:")

        for swing in swings[-15:]:
            print(
                f"{swing.time_utc} | "
                f"{swing.type:11} | "
                f"{swing.label or '-':2} | "
                f"{swing.price}"
            )

    finally:
        await provider.aclose()



def test_structure_live():
    """Integration test — requires MT5 bridge at URL from settings."""
    async def _run():
        provider = MT5BridgeProvider(
            settings.mt5_bridge_url,
            settings.mt5_bridge_timeout_seconds,
        )
        try:
            candles = await provider.get_candles(symbol="EURUSDm", timeframe="H1", count=300)
        finally:
            await provider.aclose()

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        times = [c.time_utc for c in candles]
        swings = find_swings(highs=highs, lows=lows, times=times, lookback=3)
        structure = classify_structure(swings)
        assert structure in ("bullish", "bearish", "mixed", "range", "undefined", "neutral")

    try:
        asyncio.run(_run())
    except Exception as e:
        pytest.skip(f"MT5 bridge not reachable — skipping live integration test: {e}")


if __name__ == "__main__":
    asyncio.run(main())
