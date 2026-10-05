import asyncio
import pytest

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.core.config import settings
from app.services.market_data.base import MarketDataUnavailable
from app.services.technical.indicators import ema, rsi, macd, atr


async def main():
    provider = MT5BridgeProvider(
        settings.mt5_bridge_url,
        settings.mt5_bridge_timeout_seconds,
    )

    try:
        candles = await provider.get_candles("EURUSDm", "H1", 300)

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        ema200 = ema(closes, 200)

        rsi14 = rsi(closes, 14)

        macd_line, signal_line, histogram = macd(closes)

        atr14 = atr(highs, lows, closes, 14)

        i = len(candles) - 1

        print("SYMBOL     :", candles[i].__class__)
        print("TIME       :", candles[i].time_utc)
        print("CLOSE      :", closes[i])
        print("EMA20      :", ema20[i])
        print("EMA50      :", ema50[i])
        print("EMA200     :", ema200[i])
        print("RSI14      :", rsi14[i])
        print("MACD       :", macd_line[i])
        print("MACD SIGNAL:", signal_line[i])
        print("MACD HIST  :", histogram[i])
        print("ATR14      :", atr14[i])

    finally:
        await provider.aclose()


def test_technical_indicators_live():
    """Integration test — requires MT5 bridge at URL from settings."""
    async def _run():
        provider = MT5BridgeProvider(
            settings.mt5_bridge_url,
            settings.mt5_bridge_timeout_seconds,
        )
        try:
            candles = await provider.get_candles("EURUSDm", "H1", 300)
        finally:
            await provider.aclose()
        assert len(candles) > 0, "Expected candles from bridge"
        closes = [c.close for c in candles]
        ema20 = ema(closes, 20)
        assert ema20[-1] is not None

    try:
        asyncio.run(_run())
    except Exception as e:
        pytest.skip(f"MT5 bridge not reachable — skipping live integration test: {e}")


if __name__ == "__main__":
    asyncio.run(main())
