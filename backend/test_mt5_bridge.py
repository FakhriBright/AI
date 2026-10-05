import asyncio
from app.core.config import settings

from app.services.market_data.mt5_bridge import MT5BridgeProvider


async def main():
    provider = MT5BridgeProvider(
        settings.mt5_bridge_url,
        settings.mt5_bridge_timeout_seconds,
    )

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


if __name__ == "__main__":
    asyncio.run(main())
