import asyncio
import json

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.services.analysis.builder import build_analysis_snapshot
from app.services.analysis.context import build_multi_timeframe_context
from app.services.analysis.bias import build_market_bias
from app.services.analysis.levels import build_key_levels
from app.services.analysis.scenario import build_scenarios
from app.services.analysis.confirmation import confirm_scenario
from app.services.analysis.candles import get_closed_candles
from app.services.analysis.trade_plan import build_trade_plan
from app.services.ai.serializer import build_ai_context


async def test_symbol(provider, symbol):

    snapshot = await build_analysis_snapshot(
        provider=provider,
        symbol=symbol,
        count=300,
    )

    context = build_multi_timeframe_context(snapshot)
    bias = build_market_bias(context)
    levels = build_key_levels(context)

    scenarios = build_scenarios(
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

    latest = closed_candles[-1]

    selected_plan = None

    for scenario in scenarios.scenarios:

        result = confirm_scenario(
            context=context,
            scenario=scenario,
            latest_open=latest.open,
            latest_high=latest.high,
            latest_low=latest.low,
            latest_close=latest.close,
        )

        if not result.confirmed:
            continue

        if result.entry_price is None:
            continue

        atr_reference = (
            context.timeframes["M5"].atr14
            or context.timeframes["M15"].atr14
        )

        from app.services.analysis.stop import (
            StopRequest,
            calculate_stop,
        )

        from app.services.analysis.risk import (
            RiskRequest,
            calculate_risk,
        )

        if scenario.trigger_reference is None:
            continue

        stop_plan = calculate_stop(
            StopRequest(
                direction=scenario.direction,
                entry_price=result.entry_price,
                trigger_reference=scenario.trigger_reference,
                invalidation_reference=scenario.invalidation_reference,
                atr_reference=atr_reference,
            )
        )

        info = await provider.symbol_info(symbol)

        risk_plan = calculate_risk(
            RiskRequest(
                symbol=symbol,
                account_equity=1000.0,
                risk_percent=1.0,
                entry_price=stop_plan.entry_price,
                stop_price=stop_plan.stop_price,
            ),
            tick_size=info.tick_size,
            tick_value=info.tick_value,
            volume_min=info.volume_min,
            volume_max=info.volume_max,
            volume_step=info.volume_step,
        )

        selected_plan = build_trade_plan(
            symbol=symbol,
            scenario=scenario,
            confirmation=result,
            stop_plan=stop_plan,
            risk_plan=risk_plan,
            bias=bias,
            context=context,
            levels=levels,
        )

        break

    if selected_plan is None:

        scenario = scenarios.scenarios[0]

        result = confirm_scenario(
            context=context,
            scenario=scenario,
            latest_open=latest.open,
            latest_high=latest.high,
            latest_low=latest.low,
            latest_close=latest.close,
        )

        selected_plan = build_trade_plan(
            symbol=symbol,
            scenario=scenario,
            confirmation=result,
            bias=bias,
            context=context,
            levels=levels,
        )

    ai_context = build_ai_context(
        context=context,
        bias=bias,
        levels=levels,
        scenarios=scenarios,
        trade_plan=selected_plan,
    )

    print()
    print("=" * 60)
    print(f"AI CONTEXT TEST : {symbol}")
    print("=" * 60)

    print()
    print("TOP LEVEL KEYS:")
    print(list(ai_context.keys()))

    print()
    print("SYMBOL:")
    print(ai_context["symbol"])

    print()
    print("MARKET BIAS:")
    print(
        ai_context["market_bias"]["overall"]
    )

    print()
    print("TIMEFRAMES:")
    print(
        list(
            ai_context["multi_timeframe"]["timeframes"].keys()
        )
    )

    print()
    print("SUPPORT ZONES:")
    print(
        len(
            ai_context["key_levels"]["supports"]
        )
    )

    print()
    print("RESISTANCE ZONES:")
    print(
        len(
            ai_context["key_levels"]["resistances"]
        )
    )

    print()
    print("SCENARIOS:")
    for scenario in ai_context["scenarios"]["scenarios"]:
        print(
            f"- {scenario['name']} | "
            f"{scenario['direction']} | "
            f"{scenario['status']}"
        )

    print()
    print("TRADE PLAN:")
    print(
        f"{ai_context['trade_plan']['scenario_name']} | "
        f"{ai_context['trade_plan']['status']}"
    )

    # Validate JSON serialization.
    json_string = json.dumps(
        ai_context,
        indent=2,
        default=str,
    )

    print()
    print("JSON SERIALIZATION:")
    print(f"{len(json_string)} characters")
    print("PASS")


async def main():

    provider = MT5BridgeProvider(
        "http://172.16.204.62:8765"
    )

    try:

        for symbol in [
            "EURUSDm",
            "XAUUSDm",
        ]:
            await test_symbol(
                provider,
                symbol,
            )

    finally:
        await provider.aclose()


asyncio.run(main())
