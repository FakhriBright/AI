import asyncio

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.services.technical.structure import find_swings, classify_structure


async def main():
    provider = MT5BridgeProvider("http://172.16.204.62:8765")

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


asyncio.run(main())
