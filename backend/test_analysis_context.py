import asyncio

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.services.analysis.builder import build_analysis_snapshot
from app.services.analysis.context import (
    build_multi_timeframe_context,
    print_multi_timeframe_context,
)
from app.services.analysis.bias import (
    build_market_bias,
    print_market_bias,
)
from app.services.analysis.levels import (
    build_key_levels,
    print_key_levels,
)
from app.services.analysis.scenario import (
    build_scenarios,
    print_scenarios,
)


BRIDGE_URL = "http://172.16.204.62:8765"


async def main():
    provider = MT5BridgeProvider(BRIDGE_URL)

    try:
        symbols = ["EURUSDm", "XAUUSDm"]

        for symbol in symbols:
            print(f"\n\n{'=' * 60}")
            print(f"ANALYZING {symbol}")
            print(f"{'=' * 60}")

            snapshot = await build_analysis_snapshot(
                provider,
                symbol,
            )

            context = build_multi_timeframe_context(snapshot)

            print_multi_timeframe_context(context)

            bias = build_market_bias(context)

            print_market_bias(bias)

            levels = build_key_levels(context)
            print_key_levels(levels)

            scenarios = build_scenarios(
            context,
            bias,
            levels,
            )

            print_scenarios(scenarios)

    finally:
        await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
