from dataclasses import dataclass
from time import monotonic
from typing import Any

from app.services.ai.cache import (
    get_cached_analysis,
    make_analysis_fingerprint,
    store_cached_analysis,
)
from app.services.ai.metrics import metrics_collector
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
    ai_cached: bool = False


@dataclass
class DeterministicContext:
    """Deterministic pipeline output without AI call.

    Cached and reused by chat endpoint so that every chat message does not
    re-run 7-timeframe data fetch + indicator computation + scenario analysis.
    """
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


# ---------------------------------------------------------------
# Deterministic context cache
#
# Chat messages arrive frequently.  Each one was previously running the
# full deterministic pipeline (7 × MT5 candle fetch, indicators, bias,
# levels, scenarios, confirmation, stop, risk, trade plan).
#
# The cache stores the latest DeterministicContext *per symbol* with a
# time-to-live (TTL).  Within the TTL window every chat message reuses
# the same context — zero additional MT5 / pipeline cost.
#
# The full-analysis endpoint (and the 30-second auto-refresh) always
# runs the pipeline fresh and refreshes this cache as a side-effect.
# ---------------------------------------------------------------

_DETERMINISTIC_CACHE_TTL_SECONDS = 25  # < auto-refresh interval (30 s)

_DeterministicCacheKey = tuple[str, float | None, int]


@dataclass
class _CachedDeterministic:
    ctx: DeterministicContext
    timestamp: float  # monotonic clock


_deterministic_cache: dict[_DeterministicCacheKey, _CachedDeterministic] = {}


def _store_deterministic(
    symbol: str,
    risk_percent: float | None,
    count: int,
    ctx: DeterministicContext,
) -> None:
    key = (symbol, risk_percent, count)
    _deterministic_cache[key] = _CachedDeterministic(
        ctx=ctx,
        timestamp=monotonic(),
    )


def _get_deterministic(
    symbol: str,
    risk_percent: float | None,
    count: int,
) -> DeterministicContext | None:
    key = (symbol, risk_percent, count)
    entry = _deterministic_cache.get(key)
    if entry is None:
        return None
    age = monotonic() - entry.timestamp
    if age > _DETERMINISTIC_CACHE_TTL_SECONDS:
        _deterministic_cache.pop(key, None)
        return None
    return entry.ctx


def _select_scenario(
    scenario_analysis: ScenarioAnalysis,
    bias: MarketBias,
) -> Scenario:
    """Choose the strongest evidence-backed candidate, not just overall bias.

    Confluence/conviction and actual trigger state lead. HTF alignment is a
    tie-breaker/penalty, so a valid counter-trend scalp can still win when its
    evidence is materially stronger, without hiding the conflict from the AI.
    """
    scenarios = scenario_analysis.scenarios
    if not scenarios:
        raise ValueError("Cannot select a scenario from an empty candidate set")

    conviction_rank = {"high": 3, "medium": 2, "low": 1}
    invalid_status = {"invalidated", "rejected"}

    def rank(scenario: Scenario) -> tuple[float, ...]:
        direction = scenario.direction
        score = float(scenario.confluence_score or 0)
        score += conviction_rank.get(scenario.conviction, 0) * 4
        if scenario.trigger_confirmed:
            score += 22
        if scenario.breakout_status in {"true_breakout", "pullback_valid"}:
            score += 8
        if scenario.near_trigger:
            score += 3
        if scenario.status in invalid_status:
            score -= 100
        if scenario.trigger_reference is None:
            score -= 8

        # Higher-timeframe alignment is important but not an absolute veto.
        if bias.htf.direction in {"bullish", "bearish"}:
            score += 7 if direction == bias.htf.direction else -7
        if bias.intraday.direction in {"bullish", "bearish"}:
            score += 3 if direction == bias.intraday.direction else -3

        distance = scenario.trigger_distance_atr
        proximity = -(float(distance) if distance is not None else 99.0)
        return (
            score,
            1.0 if scenario.trigger_confirmed else 0.0,
            float(scenario.confluence_score or 0),
            proximity,
        )

    return max(scenarios, key=rank)


def _provider_identity(ai_service: AIReasoningService) -> tuple[str, str]:
    provider = ai_service.provider
    provider_name = getattr(
        provider,
        "provider",
        type(provider).__name__,
    )
    model = getattr(provider, "model", "")
    return str(provider_name), str(model)


async def _build_deterministic(
    symbol: str,
    provider: MarketDataProvider,
    risk_percent: float | None = None,
    count: int = 300,
) -> DeterministicContext:
    """Run the full deterministic pipeline (no AI call)."""

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

    # Confirm against the latest CLOSED candle on the timeframe that produced
    # the setup evidence. The previous M1 fetch could use a still-forming bar
    # to confirm an M15 setup, making the entry state inconsistent with the
    # breakout classifier and candle-pattern evidence.
    confirmation_tf = (
        "M5" if selected_scenario.name.startswith("scalp_") else "M15"
    )
    confirmation_data = context.timeframes.get(confirmation_tf)
    confirmation_candles = (
        confirmation_data.evidence_candles if confirmation_data is not None else []
    )
    if not confirmation_candles:
        raise RuntimeError(
            f"No closed {confirmation_tf} candles available for {symbol}"
        )

    latest_candle = confirmation_candles[-1]

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

    det = DeterministicContext(
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
    )

    # Always refresh the deterministic cache for (symbol, risk_percent, count).
    _store_deterministic(symbol, risk_percent, count, det)

    return det


async def get_deterministic_context(
    symbol: str,
    provider: MarketDataProvider,
    risk_percent: float | None = None,
    count: int = 300,
) -> DeterministicContext:
    """Return cached deterministic context if fresh, otherwise rebuild.

    Used by the chat endpoint to avoid re-running the full pipeline on
    every message.  The full-analysis endpoint calls analyze_symbol()
    which always rebuilds and refreshes this cache.
    """
    cached = _get_deterministic(symbol, risk_percent, count)
    if cached is not None:
        return cached

    return await _build_deterministic(
        symbol=symbol,
        provider=provider,
        risk_percent=risk_percent,
        count=count,
    )


async def analyze_symbol(
    symbol: str,
    provider: MarketDataProvider,
    ai_service: AIReasoningService | None,
    risk_percent: float | None = None,
    count: int = 300,
    run_ai: bool = True,
) -> AnalysisPipelineResult:

    det = await _build_deterministic(
        symbol=symbol,
        provider=provider,
        risk_percent=risk_percent,
        count=count,
    )

    ai_cached = False

    if not run_ai:
        ai_response = AIResponse(
            provider="skipped",
            model="skipped",
            analysis="",
            raw={"status": "skipped"},
        )
    else:
        if ai_service is None:
            provider_name, model = "unavailable", "unavailable"
            ai_response = AIResponse(
                provider=provider_name,
                model=model,
                analysis="AI analysis unavailable.",
                raw={"status": "unavailable", "error_type": "provider_initialization"},
            )
            return AnalysisPipelineResult(
                snapshot=det.snapshot,
                context=det.context,
                bias=det.bias,
                levels=det.levels,
                scenarios=det.scenarios,
                selected_scenario=det.selected_scenario,
                latest_candle=det.latest_candle,
                confirmation=det.confirmation,
                stop_plan=det.stop_plan,
                trade_plan=det.trade_plan,
                ai_context=det.ai_context,
                ai_response=ai_response,
                ai_cached=False,
            )

        provider_name, model = _provider_identity(ai_service)
        fingerprint = make_analysis_fingerprint(
            det.ai_context,
            provider_name=provider_name,
            model=model,
        )
        cached = get_cached_analysis(fingerprint)

        if cached is not None:
            ai_response = cached
            ai_cached = True
            raw = dict(ai_response.raw or {})
            raw["cache_hit"] = True
            ai_response.raw = raw
            usage = raw.get("usage", {})
            tokens_saved = usage.get("total_tokens", 2500)
            metrics_collector.record_call(
                feature="Full Analysis",
                provider=provider_name,
                model=model,
                cache_status="HIT",
                prompt_tokens=0,
                completion_tokens=0,
                token_type=usage.get("type", "ACTUAL"),
                tokens_saved=tokens_saved,
            )
        else:
            try:
                ai_response = await ai_service.analyze(det.ai_context)
            except Exception as exc:
                ai_response = AIResponse(
                    provider=provider_name,
                    model=model or "unknown",
                    analysis=f"AI analysis unavailable: {exc}",
                    raw={
                        "status": "error",
                        "error_type": type(exc).__name__,
                    },
                )
            else:
                store_cached_analysis(fingerprint, ai_response)
                raw = ai_response.raw or {}
                usage = raw.get("usage", {})
                p_tok = usage.get("prompt_tokens", 0)
                c_tok = usage.get("completion_tokens", 0)
                t_type = usage.get("type", "ACTUAL")
                metrics_collector.record_call(
                    feature="Full Analysis",
                    provider=provider_name,
                    model=model,
                    cache_status="MISS",
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    token_type=t_type,
                )

    return AnalysisPipelineResult(
        snapshot=det.snapshot,
        context=det.context,
        bias=det.bias,
        levels=det.levels,
        scenarios=det.scenarios,
        selected_scenario=det.selected_scenario,
        latest_candle=det.latest_candle,
        confirmation=det.confirmation,
        stop_plan=det.stop_plan,
        trade_plan=det.trade_plan,
        ai_context=det.ai_context,
        ai_response=ai_response,
        ai_cached=ai_cached,
    )
