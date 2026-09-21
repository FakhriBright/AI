import asyncio

from app.services.market_data.mt5_bridge import MT5BridgeProvider


async def main():
    provider = MT5BridgeProvider("http://172.16.204.62:8765")

    try:
        health = await provider.health()
        print("HEALTH:")
        print(health)

        candles = await provider.get_candles("EURUSDm", "H1", 3)
        print("\nCANDLES:")
        for candle in candles:
            print(candle)

    finally:
        await provider.aclose()


asyncio.run(main())
