from dataclasses import dataclass, field

from app.services.analysis.bias import MarketBias
from app.services.analysis.confirmation import ConfirmationResult
from app.services.analysis.context import MultiTimeframeContext
from app.services.analysis.levels import KeyLevels
from app.services.analysis.risk import RiskPlan
from app.services.analysis.scenario import Scenario
from app.services.analysis.stop import StopPlan


def calculate_rr(
    direction: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
) -> float:
    """
    Calculate Risk-to-Reward ratio for LONG and SHORT setups.

    LONG:  (target_price - entry_price) / (entry_price - stop_price)
    SHORT: (entry_price - target_price) / (stop_price - entry_price)
    """
    if direction in ("bullish", "long"):
        risk = entry_price - stop_price
        reward = target_price - entry_price
    elif direction in ("bearish", "short"):
        risk = stop_price - entry_price
        reward = entry_price - target_price
    else:
        raise ValueError(f"Invalid direction for R:R calculation: {direction!r}")

    if risk <= 0:
        raise ValueError("Invalid stop price: risk distance must be greater than zero")

    if reward <= 0:
        raise ValueError("Invalid target price: reward distance must be greater than zero")

    return reward / risk


@dataclass
class TradePlan:
    symbol: str
    scenario_name: str
    direction: str
    status: str

    entry_price: float | None = None
    stop_price: float | None = None
    stop_distance: float | None = None
    target_price: float | None = None
    rr_ratio: float | None = None

    risk_percent: float | None = None
    risk_amount: float | None = None
    volume: float | None = None
    estimated_loss: float | None = None

    confirmation_type: str | None = None
    stop_method: str | None = None

    market_bias: str | None = None
    htf_bias: str | None = None
    intraday_bias: str | None = None
    entry_bias: str | None = None

    conflicts: list[str] = field(default_factory=list)

    technical_context: dict = field(default_factory=dict)
    levels_context: dict = field(default_factory=dict)

    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _build_technical_context(
    context: MultiTimeframeContext,
) -> dict:
    result = {}

    for timeframe, data in context.timeframes.items():
        result[timeframe] = {
            "price": data.price,
            "trend": data.trend,
            "structure": data.structure,
            "ema_alignment": data.ema_alignment,
            "ema20": data.ema20,
            "ema50": data.ema50,
            "ema200": data.ema200,
            "rsi14": data.rsi14,
            "macd": data.macd,
            "macd_signal": data.macd_signal,
            "macd_hist": data.macd_hist,
            "atr14": data.atr14,
            "reasons": list(data.reasons),
            "swings": [
                {
                    "time_utc": swing.time_utc,
                    "type": swing.type,
                    "label": swing.label,
                    "price": swing.price,
                }
                for swing in data.swings
            ],
        }

    return result


def _build_levels_context(
    levels: KeyLevels,
) -> dict:
    return {
        "current_price": levels.current_price,
        "supports": [
            {
                "price": zone.price,
                "low": zone.low,
                "high": zone.high,
                "level_type": zone.level_type,
                "timeframes": list(zone.timeframes),
                "touches": zone.touches,
            }
            for zone in levels.supports
        ],
        "resistances": [
            {
                "price": zone.price,
                "low": zone.low,
                "high": zone.high,
                "level_type": zone.level_type,
                "timeframes": list(zone.timeframes),
                "touches": zone.touches,
            }
            for zone in levels.resistances
        ],
    }


def build_trade_plan(
    symbol: str,
    scenario: Scenario,
    confirmation: ConfirmationResult,
    stop_plan: StopPlan | None = None,
    risk_plan: RiskPlan | None = None,
    bias: MarketBias | None = None,
    context: MultiTimeframeContext | None = None,
    levels: KeyLevels | None = None,
    risk_error: str | None = None,
) -> TradePlan:

    reasons = list(confirmation.reasons)
    warnings: list[str] = []

    market_bias = None
    htf_bias = None
    intraday_bias = None
    entry_bias = None
    conflicts: list[str] = []

    if bias is not None:
        market_bias = bias.overall
        htf_bias = bias.htf.direction
        intraday_bias = bias.intraday.direction
        entry_bias = bias.entry.direction
        conflicts = list(bias.conflicts)

        if conflicts:
            warnings.extend(conflicts)

    technical_context = (
        _build_technical_context(context)
        if context is not None
        else {}
    )

    levels_context = (
        _build_levels_context(levels)
        if levels is not None
        else {}
    )

    # --------------------------------------------------------
    # Scenario not confirmed
    # --------------------------------------------------------

    if not confirmation.confirmed:
        warnings.append("Scenario is not confirmed")

        return TradePlan(
            symbol=symbol,
            scenario_name=scenario.name,
            direction=scenario.direction,
            status="waiting",
            confirmation_type=confirmation.confirmation_type,
            market_bias=market_bias,
            htf_bias=htf_bias,
            intraday_bias=intraday_bias,
            entry_bias=entry_bias,
            conflicts=conflicts,
            technical_context=technical_context,
            levels_context=levels_context,
            reasons=reasons,
            warnings=warnings,
        )

    # --------------------------------------------------------
    # Confirmation exists but stop is unavailable
    # --------------------------------------------------------

    if stop_plan is None:
        warnings.append("Confirmed scenario has no stop plan")

        return TradePlan(
            symbol=symbol,
            scenario_name=scenario.name,
            direction=scenario.direction,
            status="confirmed_needs_stop",
            entry_price=confirmation.entry_price,
            confirmation_type=confirmation.confirmation_type,
            market_bias=market_bias,
            htf_bias=htf_bias,
            intraday_bias=intraday_bias,
            entry_bias=entry_bias,
            conflicts=conflicts,
            technical_context=technical_context,
            levels_context=levels_context,
            reasons=reasons,
            warnings=warnings,
        )

    # --------------------------------------------------------
    # Stop exists but risk calculation unavailable
    # --------------------------------------------------------

    if risk_plan is None:
        warnings.append("Stop exists but risk calculation is unavailable")

        if risk_error:
            warnings.append(f"Risk calculation error: {risk_error}")

        return TradePlan(
            symbol=symbol,
            scenario_name=scenario.name,
            direction=scenario.direction,
            status="confirmed_needs_risk",
            entry_price=stop_plan.entry_price,
            stop_price=stop_plan.stop_price,
            stop_distance=stop_plan.stop_distance,
            confirmation_type=confirmation.confirmation_type,
            stop_method=stop_plan.method,
            market_bias=market_bias,
            htf_bias=htf_bias,
            intraday_bias=intraday_bias,
            entry_bias=entry_bias,
            conflicts=conflicts,
            technical_context=technical_context,
            levels_context=levels_context,
            reasons=reasons + stop_plan.reasons,
            warnings=warnings,
        )

    # --------------------------------------------------------
    # Complete trade plan
    # --------------------------------------------------------

    target_price: float | None = None
    rr_ratio: float | None = None

    if stop_plan is not None and levels is not None:
        if scenario.direction == "bullish" and levels.resistances:
            target_price = levels.resistances[0].price
        elif scenario.direction == "bearish" and levels.supports:
            target_price = levels.supports[0].price

        if target_price is not None:
            try:
                rr_ratio = calculate_rr(
                    direction=scenario.direction,
                    entry_price=stop_plan.entry_price,
                    stop_price=stop_plan.stop_price,
                    target_price=target_price,
                )
            except ValueError:
                rr_ratio = None

    return TradePlan(
        symbol=symbol,
        scenario_name=scenario.name,
        direction=scenario.direction,
        status="ready_for_manual_review",

        entry_price=stop_plan.entry_price,
        stop_price=stop_plan.stop_price,
        stop_distance=stop_plan.stop_distance,
        target_price=target_price,
        rr_ratio=rr_ratio,

        risk_percent=risk_plan.risk_percent,
        risk_amount=risk_plan.risk_amount,
        volume=risk_plan.volume,
        estimated_loss=risk_plan.estimated_loss,

        confirmation_type=confirmation.confirmation_type,
        stop_method=stop_plan.method,

        market_bias=market_bias,
        htf_bias=htf_bias,
        intraday_bias=intraday_bias,
        entry_bias=entry_bias,
        conflicts=conflicts,

        technical_context=technical_context,
        levels_context=levels_context,

        reasons=reasons,
        warnings=warnings,
    )
