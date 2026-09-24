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
from app.services.analysis.trade_plan import build_trade_plan


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

    if not closed_candles:
        raise RuntimeError(f"No closed M5 candles available for {symbol}")

    latest = closed_candles[-1]

    print()
    print("=" * 60)
    print(f"TRADE PLAN CONTEXT TEST : {symbol}")
    print("=" * 60)

    print(f"MARKET BIAS  : {bias.overall}")
    print(f"HTF BIAS     : {bias.htf.direction}")
    print(f"INTRADAY     : {bias.intraday.direction}")
    print(f"ENTRY BIAS   : {bias.entry.direction}")

    print()
    print("=== TIMEFRAME CONTEXT ===")

    timeframes = [
        "M1",
        "M5",
        "M15",
        "M30",
        "H1",
        "H4",
        "D1",
    ]

    for timeframe in timeframes:
        data = context.timeframes[timeframe]

        print()
        print(f"[{timeframe}]")
        print(f"PRICE        : {data.price}")
        print(f"TREND        : {data.trend}")
        print(f"STRUCTURE    : {data.structure}")
        print(f"EMA ALIGN    : {data.ema_alignment}")
        print(f"RSI14        : {data.rsi14}")
        print(f"MACD         : {data.macd}")
        print(f"MACD SIGNAL  : {data.macd_signal}")
        print(f"MACD HIST    : {data.macd_hist}")
        print(f"ATR14        : {data.atr14}")

    print()
    print("=== LEVEL CONTEXT ===")
    print(f"SUPPORTS     : {len(levels.supports)}")
    print(f"RESISTANCES  : {len(levels.resistances)}")

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

        if scenario.trigger_reference is None:
            continue

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

    print()
    print("=== TRADE PLAN ===")

    print(f"SCENARIO     : {selected_plan.scenario_name}")
    print(f"DIRECTION    : {selected_plan.direction}")
    print(f"STATUS       : {selected_plan.status}")
    print(f"MARKET BIAS  : {selected_plan.market_bias}")
    print(f"HTF BIAS     : {selected_plan.htf_bias}")
    print(f"INTRADAY     : {selected_plan.intraday_bias}")
    print(f"ENTRY BIAS   : {selected_plan.entry_bias}")
    print(f"ENTRY        : {selected_plan.entry_price}")
    print(f"STOP         : {selected_plan.stop_price}")
    print(f"RISK %       : {selected_plan.risk_percent}")
    print(f"VOLUME       : {selected_plan.volume}")

    print()
    print("CONTEXT KEYS:")
    print(
        f"Technical TFs : "
        f"{list(selected_plan.technical_context.keys())}"
    )

    print(
        f"Support zones : "
        f"{len(selected_plan.levels_context.get('supports', []))}"
    )

    print(
        f"Resistance zones : "
        f"{len(selected_plan.levels_context.get('resistances', []))}"
    )

    print()
    print("=== VALIDATION ===")

    expected_timeframes = {
        "M1",
        "M5",
        "M15",
        "M30",
        "H1",
        "H4",
        "D1",
    }

    actual_timeframes = set(
        selected_plan.technical_context.keys()
    )

    if actual_timeframes == expected_timeframes:
        print("MTF CONTEXT  : PASS")
    else:
        print("MTF CONTEXT  : FAIL")

    if "supports" in selected_plan.levels_context:
        print("LEVEL CONTEXT: PASS")
    else:
        print("LEVEL CONTEXT: FAIL")

    if selected_plan.market_bias is not None:
        print("BIAS CONTEXT  : PASS")
    else:
        print("BIAS CONTEXT  : FAIL")


async def main():

    provider = MT5BridgeProvider(
        "http://172.16.204.62:8765"
    )

    try:

        symbols = [
            "EURUSDm",
            "XAUUSDm",
        ]

        for symbol in symbols:
            await test_symbol(
                provider=provider,
                symbol=symbol,
            )

    finally:
        await provider.aclose()


asyncio.run(main())
