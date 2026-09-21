import asyncio
import json

from app.services.ai.factory import get_ai_provider
from app.services.ai.reasoning import AIReasoningService
from app.services.ai.serializer import build_ai_context
from app.services.analysis.bias import build_market_bias
from app.services.analysis.builder import build_analysis_snapshot
from app.services.analysis.confirmation import confirm_scenario
from app.services.analysis.context import build_multi_timeframe_context
from app.services.analysis.levels import build_key_levels
from app.services.analysis.scenario import build_scenarios
from app.services.analysis.stop import StopRequest, calculate_stop
from app.services.analysis.trade_plan import build_trade_plan
from app.services.market_data.factory import get_market_data_provider


async def analyze_symbol(symbol: str):

    provider = get_market_data_provider()

    snapshot = await build_analysis_snapshot(
        provider=provider,
        symbol=symbol,
        count=300,
    )

    context = build_multi_timeframe_context(snapshot)

    bias = build_market_bias(context)

    levels = build_key_levels(context)

    scenario_analysis = build_scenarios(
        context=context,
        bias=bias,
        levels=levels,
    )

    # Use the first directional scenario for confirmation testing.
    scenario = next(
        (
            item
            for item in scenario_analysis.scenarios
            if item.direction in {"bullish", "bearish"}
        ),
        scenario_analysis.scenarios[0],
    )

    m1 = snapshot.timeframes["M1"]

    latest_candle = None

    # Retrieve the latest M1 candle directly from the provider
    candles = await provider.get_candles(
        symbol=symbol,
        timeframe="M1",
        count=2,
    )

    if not candles:
        raise RuntimeError(f"No M1 candles returned for {symbol}")

    latest_candle = candles[-1]

    confirmation = confirm_scenario(
        context=context,
        scenario=scenario,
        latest_open=latest_candle.open,
        latest_high=latest_candle.high,
        latest_low=latest_candle.low,
        latest_close=latest_candle.close,
    )

    stop_plan = None

    if (
        confirmation.confirmed
        and confirmation.entry_price is not None
        and confirmation.stop_price is None
        and scenario.direction == "bullish"
    ):
        if scenario.trigger_reference is not None:
            stop_plan = calculate_stop(
                StopRequest(
                    direction=scenario.direction,
                    entry_price=confirmation.entry_price,
                    trigger_reference=scenario.trigger_reference,
                    invalidation_reference=scenario.invalidation_reference,
                    atr_reference=scenario.atr_reference,
                )
            )

    elif (
        confirmation.confirmed
        and confirmation.entry_price is not None
        and confirmation.stop_price is not None
    ):
        stop_plan = calculate_stop(
            StopRequest(
                direction=scenario.direction,
                entry_price=confirmation.entry_price,
                trigger_reference=(
                    scenario.trigger_reference
                    if scenario.trigger_reference is not None
                    else confirmation.stop_price
                ),
                invalidation_reference=confirmation.stop_price,
                atr_reference=scenario.atr_reference,
            )
        )

    trade_plan = build_trade_plan(
        symbol=symbol,
        scenario=scenario,
        confirmation=confirmation,
        stop_plan=stop_plan,
        risk_plan=None,
        bias=bias,
        context=context,
        levels=levels,
    )

    ai_context = build_ai_context(
        context=context,
        bias=bias,
        levels=levels,
        scenarios=scenario_analysis,
        trade_plan=trade_plan,
    )

    ai = AIReasoningService(
        provider=get_ai_provider()
    )

    response = await ai.analyze(ai_context)

    print()
    print("=" * 70)
    print(f"AI REASONING TEST: {symbol}")
    print("=" * 70)

    print(response.analysis)

    print()
    print("Provider :", response.provider)
    print("Model    :", response.model)
    print("Scenario :", scenario.name)
    print("Confirm  :", confirmation.confirmed)
    print("Status   :", trade_plan.status)

    serialized = json.dumps(
        ai_context,
        ensure_ascii=False,
    )

    print("Context  :", len(serialized), "characters")

    return response


async def main():

    for symbol in ["EURUSDm", "XAUUSDm"]:
        await analyze_symbol(symbol)


if __name__ == "__main__":
    asyncio.run(main())
