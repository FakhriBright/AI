import asyncio

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.services.analysis.builder import build_analysis_snapshot
from app.services.analysis.context import build_multi_timeframe_context
from app.services.analysis.bias import build_market_bias
from app.services.analysis.levels import build_key_levels
from app.services.analysis.scenario import build_scenarios
from app.services.analysis.confirmation import confirm_scenario
from app.services.analysis.candles import get_closed_candles
from app.services.analysis.stop import StopRequest, calculate_stop
from app.services.analysis.risk import RiskRequest, calculate_risk


async def main():
    provider = MT5BridgeProvider("http://172.16.204.62:8765")

    try:
        symbol = "EURUSDm"

        # ----------------------------------------------------
        # 1. MARKET ANALYSIS
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # 2. CLOSED M5 CANDLE
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # 3. PIPELINE HEADER
        # ----------------------------------------------------

        print("=" * 60)
        print("TRADE PIPELINE INTEGRATION TEST")
        print("=" * 60)

        print(f"SYMBOL        : {symbol}")
        print(f"M5 TIME       : {latest.time_utc}")
        print(f"M5 CLOSE      : {latest.close}")
        print(f"MARKET BIAS   : {bias.overall}")

        # ----------------------------------------------------
        # 4. CONFIRMATION
        # ----------------------------------------------------

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
            print("-" * 60)
            print(f"SCENARIO      : {scenario.name}")
            print(f"DIRECTION     : {scenario.direction}")
            print(f"CONFIRMED     : {result.confirmed}")
            print(f"CONFIRM TYPE  : {result.confirmation_type}")

            if not result.confirmed:
                print("PIPELINE      : STOPPED")
                print("REASON        : Scenario not confirmed")
                continue

            # ------------------------------------------------
            # 5. STOP PLACEMENT
            # ------------------------------------------------

            atr_reference = (
                context.timeframes["M5"].atr14
                or context.timeframes["M15"].atr14
            )

            stop_plan = calculate_stop(
                StopRequest(
                    direction=scenario.direction,
                    entry_price=result.entry_price,
                    trigger_reference=scenario.trigger_reference,
                    invalidation_reference=scenario.invalidation_reference,
                    atr_reference=atr_reference,
                )
            )

            print(f"ENTRY PRICE   : {stop_plan.entry_price}")
            print(f"STOP PRICE    : {stop_plan.stop_price}")
            print(f"STOP DISTANCE : {stop_plan.stop_distance}")
            print(f"STOP METHOD   : {stop_plan.method}")

            # ------------------------------------------------
            # 6. RISK ENGINE
            # ------------------------------------------------

            info = await provider.symbol_info(symbol)

            risk_request = RiskRequest(
                symbol=symbol,
                account_equity=1000.0,
                risk_percent=1.0,
                entry_price=stop_plan.entry_price,
                stop_price=stop_plan.stop_price,
            )

            risk_plan = calculate_risk(
                request=risk_request,
                tick_size=info.tick_size,
                tick_value=info.tick_value,
                volume_min=info.volume_min,
                volume_max=info.volume_max,
                volume_step=info.volume_step,
            )

            print(f"RISK AMOUNT  : {risk_plan.risk_amount}")
            print(f"RAW VOLUME    : {risk_plan.raw_volume}")
            print(f"NORMALIZED LOT: {risk_plan.volume}")
            print(f"EST. LOSS     : {risk_plan.estimated_loss}")

            print("PIPELINE      : COMPLETE")

    finally:
        await provider.aclose()


asyncio.run(main())
