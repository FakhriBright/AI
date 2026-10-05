import asyncio
import pytest

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.core.config import settings
from app.services.market_data.base import MarketDataUnavailable
from app.services.analysis.builder import build_analysis_snapshot
from app.services.analysis.context import build_multi_timeframe_context
from app.services.analysis.bias import build_market_bias
from app.services.analysis.levels import build_key_levels
from app.services.analysis.scenario import build_scenarios
from app.services.analysis.confirmation import confirm_scenario
from app.services.analysis.candles import get_closed_candles

async def main():
    provider = MT5BridgeProvider(
        settings.mt5_bridge_url,
        settings.mt5_bridge_timeout_seconds,
    )

    try:
        symbol = "EURUSDm"

        snapshot = await build_analysis_snapshot(
            provider=provider,
            symbol=symbol,
            count=300,
        )

        context = build_multi_timeframe_context(snapshot)
        bias = build_market_bias(context)
        levels = build_key_levels(context)

        analysis = build_scenarios(
            context=context,
            bias=bias,
            levels=levels,
        )

        candles = await provider.get_candles(
        symbol=symbol,
        timeframe="M5",
        count=10,
        )

        closed_candles = get_closed_candles(
            candles,
            timeframe="M5",
        )

        if not closed_candles:
            raise RuntimeError("No closed M5 candles available")

        latest = closed_candles[-1]

        print("=" * 60)
        print("CONFIRMATION TEST")
        print("=" * 60)

        print(f"SYMBOL : {symbol}")

        print()
        print("=== RAW M5 CANDLES ===")

        for candle in closed_candles[-3:]:
            print(
                f"{candle.time_utc} | "
                f"O={candle.open} "
                f"H={candle.high} "
                f"L={candle.low} "
                f"C={candle.close}"
            )

        print()
        print("=== LATEST CANDLE USED ===")
        print(f"TIME   : {latest.time_utc}")
        print(f"OPEN   : {latest.open}")
        print(f"HIGH   : {latest.high}")
        print(f"LOW    : {latest.low}")
        print(f"CLOSE  : {latest.close}")

        print()
        print("=== SCENARIO CONFIRMATION ===")

        for scenario in analysis.scenarios:
            result = confirm_scenario(
                context=context,
                scenario=scenario,
                latest_open=latest.open,
                latest_high=latest.high,
                latest_low=latest.low,
                latest_close=latest.close,
            )

            print()
            print(f"[{scenario.name}]")
            print(f"DIRECTION   : {scenario.direction}")
            print(f"CONFIRMED   : {result.confirmed}")
            print(f"TYPE        : {result.confirmation_type}")
            print(f"ENTRY PRICE : {result.entry_price}")
            print(f"STOP PRICE  : {result.stop_price}")

            print("REASONS:")
            for reason in result.reasons:
                print(f"  - {reason}")

        print()
        print("=" * 60)
        print("=== SIMULATED CONFIRMATION TEST ===")
        print("=" * 60)

        for scenario in analysis.scenarios:
            if scenario.direction == "bearish" and scenario.trigger_reference is not None:
                trigger = scenario.trigger_reference

                result = confirm_scenario(
                    context=context,
                    scenario=scenario,
                    latest_open=trigger + 0.00010,
                    latest_high=trigger + 0.00020,
                    latest_low=trigger - 0.00005,
                    latest_close=trigger - 0.00005,
                )

                print()
                print("[BEARISH BREAK]")
                print(f"TRIGGER     : {trigger}")
                print(f"CONFIRMED   : {result.confirmed}")
                print(f"TYPE        : {result.confirmation_type}")
                print(f"ENTRY PRICE : {result.entry_price}")
                print(f"STOP PRICE  : {result.stop_price}")

            elif scenario.direction == "bullish" and scenario.trigger_reference is not None:
                trigger = scenario.trigger_reference

                result = confirm_scenario(
                    context=context,
                    scenario=scenario,
                    latest_open=trigger - 0.00005,
                    latest_high=trigger + 0.00020,
                    latest_low=trigger - 0.00010,
                    latest_close=trigger + 0.00010,
                )

                print()
                print("[BULLISH REJECTION]")
                print(f"SUPPORT     : {trigger}")
                print(f"CONFIRMED   : {result.confirmed}")
                print(f"TYPE        : {result.confirmation_type}")
                print(f"ENTRY PRICE : {result.entry_price}")
                print(f"STOP PRICE  : {result.stop_price}")

            elif scenario.direction == "neutral":
                result = confirm_scenario(
                    context=context,
                    scenario=scenario,
                    latest_open=latest.open,
                    latest_high=latest.high,
                    latest_low=latest.low,
                    latest_close=latest.close,
                )

                print()
                print("[RANGE / NEUTRAL]")
                print(f"CONFIRMED   : {result.confirmed}")
                print(f"TYPE        : {result.confirmation_type}")

    finally:
        await provider.aclose()



def test_confirmation_live():
    """Integration test — requires MT5 bridge at URL from settings."""
    async def _run():
        provider = MT5BridgeProvider(
            settings.mt5_bridge_url,
            settings.mt5_bridge_timeout_seconds,
        )
        symbol = "EURUSDm"
        try:
            snapshot = await build_analysis_snapshot(provider=provider, symbol=symbol, count=300)
        finally:
            await provider.aclose()

        context = build_multi_timeframe_context(snapshot)
        bias = build_market_bias(context)
        levels = build_key_levels(context)
        analysis = build_scenarios(context=context, bias=bias, levels=levels)
        assert len(analysis.scenarios) > 0, "Expected at least one scenario"

        for scenario in analysis.scenarios:
            result = confirm_scenario(
                context=context,
                scenario=scenario,
                latest_open=levels.current_price,
                latest_high=levels.current_price * 1.001,
                latest_low=levels.current_price * 0.999,
                latest_close=levels.current_price,
            )
            assert result.confirmed in (True, False)

    asyncio.run(_run())


if __name__ == "__main__":
    asyncio.run(main())
