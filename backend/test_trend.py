import asyncio

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.services.technical.indicators import ema
from app.services.technical.structure import find_swings, classify_structure
from app.services.technical.trend import analyze_trend


async def main():
    provider = MT5BridgeProvider("http://172.16.204.62:8765")

    try:
        candles = await provider.get_candles(
            symbol="EURUSDm",
            timeframe="H1",
            count=300,
        )

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        ema20 = ema(closes, 20)[-1]
        ema50 = ema(closes, 50)[-1]
        ema200 = ema(closes, 200)[-1]

        swings = find_swings(highs, lows, lookback=3)
        structure = classify_structure(swings)

        trend = analyze_trend(
            price=closes[-1],
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            structure=structure,
        )

        print("\n=== TREND ANALYSIS ===")
        print(f"TIME       : {candles[-1].time_utc}")
        print(f"PRICE      : {trend.price}")
        print(f"EMA20      : {trend.ema20}")
        print(f"EMA50      : {trend.ema50}")
        print(f"EMA200     : {trend.ema200}")
        print(f"STRUCTURE  : {trend.structure}")
        print(f"EMA ALIGN  : {trend.ema_alignment}")
        print(f"PRICE/EMA20 : {trend.price_vs_ema20}")
        print(f"PRICE/EMA50 : {trend.price_vs_ema50}")
        print(f"PRICE/EMA200: {trend.price_vs_ema200}")
        print(f"DIRECTION  : {trend.direction}")

        print("\nREASONS:")
        for reason in trend.reasons:
            print(f"- {reason}")

    finally:
        await provider.aclose()


asyncio.run(main())
