from dataclasses import dataclass
from typing import Any

from app.services.ai.reasoning import AIReasoningService
from app.services.ai.serializer import build_ai_context
from app.services.analysis.bias import MarketBias, build_market_bias
from app.services.analysis.builder import build_analysis_snapshot
from app.services.analysis.confirmation import ConfirmationResult, confirm_scenario
from app.services.analysis.context import (
    MultiTimeframeContext,
    build_multi_timeframe_context,
)
from app.services.analysis.levels import KeyLevels, build_key_levels
from app.services.analysis.risk import RiskRequest, RiskPlan, calculate_risk
from app.services.analysis.scenario import Scenario, ScenarioAnalysis, build_scenarios
from app.services.analysis.stop import StopPlan, StopRequest, calculate_stop
from app.services.analysis.trade_plan import TradePlan, build_trade_plan
from app.services.analysis.snapshot import AnalysisSnapshot
from app.services.ai.base import AIResponse
from app.services.market_data.base import Candle, MarketDataProvider


@dataclass
class AnalysisPipelineResult:
    snapshot: AnalysisSnapshot
    context: MultiTimeframeContext
    bias: MarketBias
    levels: KeyLevels
    scenarios: ScenarioAnalysis
    selected_scenario: Scenario
    latest_candle: Candle
    confirmation: ConfirmationResult
    stop_plan: StopPlan | None
    trade_plan: TradePlan
    ai_context: dict[str, Any]
    ai_response: AIResponse


def _select_scenario(
    scenario_analysis: ScenarioAnalysis,
    bias: MarketBias,
) -> Scenario:
    scenarios = scenario_analysis.scenarios

    scenario_by_name = {
        scenario.name: scenario
        for scenario in scenarios
    }

    if bias.overall == "bullish":
        return scenario_by_name.get(
            "bullish_reversal",
            scenarios[0],
        )

    if bias.overall == "bearish":
        return scenario_by_name.get(
            "bearish_continuation",
            scenarios[0],
        )

    return scenario_by_name.get(
        "range_or_no_clear_setup",
        scenarios[0],
    )


async def analyze_symbol(
    symbol: str,
    provider: MarketDataProvider,
    ai_service: AIReasoningService,
    risk_percent: float | None = None,
    count: int = 300,
) -> AnalysisPipelineResult:
    snapshot = await build_analysis_snapshot(
        provider=provider,
        symbol=symbol,
        count=count,
    )

    context = build_multi_timeframe_context(snapshot)

    bias = build_market_bias(context)

    levels = build_key_levels(context)

    scenario_analysis = build_scenarios(
        context=context,
        bias=bias,
        levels=levels,
    )

    if not scenario_analysis.scenarios:
        raise RuntimeError(
            f"No scenarios generated for {symbol}"
        )

    selected_scenario = _select_scenario(
        scenario_analysis=scenario_analysis,
        bias=bias,
    )

    candles = await provider.get_candles(
        symbol=symbol,
        timeframe="M1",
        count=2,
    )

    if not candles:
        raise RuntimeError(
            f"No M1 candles returned for {symbol}"
        )

    latest_candle = candles[-1]

    confirmation = confirm_scenario(
        context=context,
        scenario=selected_scenario,
        latest_open=latest_candle.open,
        latest_high=latest_candle.high,
        latest_low=latest_candle.low,
        latest_close=latest_candle.close,
    )
    selected_scenario.trigger_confirmed = confirmation.confirmed

    stop_plan: StopPlan | None = None

    if (
        confirmation.confirmed
        and confirmation.entry_price is not None
        and confirmation.stop_price is None
        and selected_scenario.direction == "bullish"
    ):
        if selected_scenario.trigger_reference is not None:
            stop_plan = calculate_stop(
                StopRequest(
                    direction=selected_scenario.direction,
                    entry_price=confirmation.entry_price,
                    trigger_reference=selected_scenario.trigger_reference,
                    invalidation_reference=(
                        selected_scenario.invalidation_reference
                    ),
                    atr_reference=selected_scenario.atr_reference,
                )
            )

    elif (
        confirmation.confirmed
        and confirmation.entry_price is not None
        and confirmation.stop_price is not None
    ):
        stop_plan = calculate_stop(
            StopRequest(
                direction=selected_scenario.direction,
                entry_price=confirmation.entry_price,
                trigger_reference=(
                    selected_scenario.trigger_reference
                    if selected_scenario.trigger_reference is not None
                    else confirmation.stop_price
                ),
                invalidation_reference=confirmation.stop_price,
                atr_reference=selected_scenario.atr_reference,
            )
        )

    risk_plan: RiskPlan | None = None
    risk_error: str | None = None

    if (
        confirmation.confirmed
        and stop_plan is not None
        and risk_percent is not None
    ):
        try:
            account = await provider.account_info()

            if account.equity > 0:
                symbol_info = await provider.symbol_info(symbol)

                risk_plan = calculate_risk(
                    RiskRequest(
                        symbol=symbol,
                        account_equity=account.equity,
                        risk_percent=risk_percent,
                        entry_price=stop_plan.entry_price,
                        stop_price=stop_plan.stop_price,
                    ),
                    tick_size=symbol_info.tick_size,
                    tick_value=symbol_info.tick_value,
                    volume_min=symbol_info.volume_min,
                    volume_max=symbol_info.volume_max,
                    volume_step=symbol_info.volume_step,
                )

        except Exception as exc:
            risk_plan = None
            risk_error = str(exc)


    trade_plan = build_trade_plan(
        symbol=symbol,
        scenario=selected_scenario,
        confirmation=confirmation,
        stop_plan=stop_plan,
        risk_plan=risk_plan,
        bias=bias,
        context=context,
        levels=levels,
        risk_error=risk_error,
    )

    ai_context = build_ai_context(
        context=context,
        bias=bias,
        levels=levels,
        scenarios=scenario_analysis,
        trade_plan=trade_plan,
    )

    try:
        ai_response = await ai_service.analyze(ai_context)
    except Exception as exc:
        ai_response = AIResponse(
            provider="gemini",
            model="gemini-3.6-flash",
            analysis=f"AI analysis unavailable: {exc}",
            raw={
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )

    return AnalysisPipelineResult(
        snapshot=snapshot,
        context=context,
        bias=bias,
        levels=levels,
        scenarios=scenario_analysis,
        selected_scenario=selected_scenario,
        latest_candle=latest_candle,
        confirmation=confirmation,
        stop_plan=stop_plan,
        trade_plan=trade_plan,
        ai_context=ai_context,
        ai_response=ai_response,
    )
