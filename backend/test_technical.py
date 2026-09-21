import asyncio

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.services.technical.indicators import ema, rsi, macd, atr


async def main():
    provider = MT5BridgeProvider("http://172.16.204.62:8765")

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


asyncio.run(main())
