import math
from dataclasses import dataclass, field, replace
from typing import Literal, Any

from app.services.analysis.context import MultiTimeframeContext
from app.services.analysis.bias import MarketBias
from app.services.analysis.levels import KeyLevels, LevelZone
from app.services.analysis.breakout_classifier import (
    classify_breakout,
    classify_support_rejection,
)
from app.services.technical.candlestick_patterns import detect_patterns


@dataclass
class Scenario:
    name: str
    direction: str
    status: str  # e.g., conditional, active, invalidated
    trigger: str
    invalidation: str

    breakout_status: str = "awaiting"
    conviction: str = "low"
    confluence_score: int = 0

    trigger_reference: float | None = None
    invalidation_reference: float | None = None

    trigger_distance: float | None = None
    invalidation_distance: float | None = None
    atr_reference: float | None = None

    trigger_distance_atr: float | None = None
    invalidation_distance_atr: float | None = None

    near_trigger: bool = False
    trigger_confirmed: bool = False

    rationale: list[str] = field(default_factory=list)


@dataclass
class ScenarioAnalysis:
    symbol: str
    current_price: float
    intraday_scenarios: list[Scenario] = field(default_factory=list)
    scalp_scenarios: list[Scenario] = field(default_factory=list)
    
    @property
    def scenarios(self) -> list[Scenario]:
        return self.intraday_scenarios + self.scalp_scenarios


def _get_entry_atr(context: MultiTimeframeContext, timeframes=("M5", "M15")) -> float | None:
    for timeframe in timeframes:
        data = context.timeframes.get(timeframe)
        if data is not None and data.atr14 is not None:
            return data.atr14
    return None

def _distance_ratio(distance: float | None, atr: float | None) -> float | None:
    if distance is None or atr is None or atr <= 0:
        return None
    return distance / atr

def _is_near_level(distance: float | None, atr: float | None) -> bool:
    if distance is None or atr is None or atr <= 0:
        return False
    return distance <= atr * 0.25

def _score_confluence(
    context: MultiTimeframeContext,
    direction: str,
    breakout_status: str,
    patterns: list[Any],
    is_fresh_zone: bool,
    has_timeframe_conflict: bool,
) -> tuple[int, str]:
    score = 0
    
    # 1. Structure (HH/HL or LH/LL) -> check M15 trend
    entry_trend = context.timeframes["M15"].trend if "M15" in context.timeframes else "mixed"
    if entry_trend == direction:
        score += 25
        
    # 2. EMA alignment (proxy for trend)
    htf_trend = context.timeframes["H4"].trend if "H4" in context.timeframes else "mixed"
    if htf_trend == direction:
        score += 15
        
    # 3. Breakout classifier
    if breakout_status in ["true_breakout", "pullback_valid"]:
        score += 25
        
    # 4. Pattern strength
    dir_patterns = [p for p in patterns if p.direction == direction]
    if dir_patterns:
        highest_strength = "weak"
        for p in dir_patterns:
            if p.strength == "strong":
                highest_strength = "strong"
                break
            elif p.strength == "moderate":
                highest_strength = "moderate"
        
        if highest_strength == "strong":
            score += 20
        elif highest_strength == "moderate":
            score += 10
            
    # 5. Zone type
    if is_fresh_zone:
        score += 10
        
    # 6. Timeframe conflict
    if has_timeframe_conflict:
        score -= 20
        
    score = max(0, min(100, score))
    
    if score >= 65:
        conviction = "high"
    elif score >= 35:
        conviction = "medium"
    else:
        conviction = "low"
        
    return score, conviction

def build_scenarios(
    context: MultiTimeframeContext,
    bias: MarketBias,
    levels: KeyLevels,
) -> ScenarioAnalysis:
    current_price = levels.current_price

    # A support candidate must be at/below current price and resistance
    # candidates must be at/above it; absolute-nearest can otherwise select a
    # level on the wrong side of price and invert the setup geometry.
    nearest_support = next(
        (zone for zone in levels.supports if zone.price < current_price),
        None,
    )
    nearest_resistance = next(
        (zone for zone in levels.resistances if zone.price > current_price),
        None,
    )
    
    support_price = nearest_support.price if nearest_support else None
    resistance_price = nearest_resistance.price if nearest_resistance else None
    
    atr_intraday = _get_entry_atr(context, ("H1", "M15"))
    atr_scalp = _get_entry_atr(context, ("M5", "M15", "M1"))
    
    candles_m15 = getattr(context.timeframes.get("M15"), "candles", [])

    intraday_scenarios = []
    scalp_scenarios = []
    
    has_conflict = len(bias.conflicts) > 0
    
    # --- Bearish Continuation ---
    bearish_reasons = []
    if bias.htf.direction == "bearish": bearish_reasons.append("htf_bias_bearish")
    if bias.intraday.direction == "bearish": bearish_reasons.append("intraday_bias_bearish")
    
    b_out = classify_breakout(candles_m15, support_price, "support", "bearish") if support_price and candles_m15 else None
    breakout_status_b = b_out.status if b_out else "awaiting"
    patterns_b = detect_patterns(candles_m15, at_zone=True) if candles_m15 else []
    
    # A fresh demand zone at support is opposing evidence for a bearish
    # breakdown, not a bullish confluence bonus.
    is_fresh_b = False
            
    score_b, conv_b = _score_confluence(context, "bearish", breakout_status_b, patterns_b, is_fresh_b, has_conflict)
    
    intraday_scenarios.append(Scenario(
        name="bearish_continuation",
        direction="bearish",
        status="active" if conv_b == "high" and breakout_status_b in ["true_breakout", "pullback_valid"] else "conditional",
        trigger=f"break_and_hold_below_support_{support_price}" if support_price else "break_below_nearest_support",
        invalidation=f"price_reclaims_above_nearest_resistance_{resistance_price}" if resistance_price else "price_reclaims_nearest_resistance",
        breakout_status=breakout_status_b,
        conviction=conv_b,
        confluence_score=score_b,
        trigger_reference=support_price,
        invalidation_reference=resistance_price,
        trigger_distance=abs(current_price - support_price) if support_price else None,
        invalidation_distance=abs(resistance_price - current_price) if resistance_price else None,
        atr_reference=atr_intraday,
        trigger_distance_atr=_distance_ratio(abs(current_price - support_price) if support_price else None, atr_intraday),
        invalidation_distance_atr=_distance_ratio(abs(resistance_price - current_price) if resistance_price else None, atr_intraday),
        near_trigger=_is_near_level(abs(current_price - support_price) if support_price else None, atr_intraday),
        trigger_confirmed=(breakout_status_b in ["true_breakout", "pullback_valid"]),
        rationale=bearish_reasons + (b_out.reasons if b_out else [])
    ))
    
    # --- Bullish Reversal ---
    bullish_reasons = []
    if bias.htf.direction == "bullish": bullish_reasons.append("htf_bias_bullish")
    if bias.intraday.direction == "bullish": bullish_reasons.append("intraday_bias_bullish")
    
    b_out2 = classify_support_rejection(candles_m15, support_price) if support_price is not None and candles_m15 else None
    breakout_status_bu = b_out2.status if b_out2 else "awaiting"
    
    # A bullish support-rejection setup is supported by demand, not supply.
    is_fresh_bu = any(
        support_price is not None
        and abs(dz.price - support_price) < 0.001
        and dz.is_fresh
        for dz in levels.demand_zones
    )

    score_bu, conv_bu = _score_confluence(context, "bullish", breakout_status_bu, patterns_b, is_fresh_bu, has_conflict)
    
    bullish_inv_ref = support_price - (atr_intraday * 0.25) if support_price and atr_intraday else None

    intraday_scenarios.append(Scenario(
        name="bullish_reversal",
        direction="bullish",
        status="active" if conv_bu == "high" and breakout_status_bu in ["true_breakout", "pullback_valid"] else "conditional",
        trigger=f"hold_and_reject_from_support_{support_price}" if support_price else "bullish_rejection_from_support",
        invalidation=f"break_below_support_buffer_{bullish_inv_ref}" if bullish_inv_ref else "break_below_nearest_support",
        breakout_status=breakout_status_bu,
        conviction=conv_bu,
        confluence_score=score_bu,
        trigger_reference=support_price,
        invalidation_reference=bullish_inv_ref,
        trigger_distance=abs(current_price - support_price) if support_price else None,
        invalidation_distance=abs(current_price - bullish_inv_ref) if bullish_inv_ref else None,
        atr_reference=atr_intraday,
        trigger_distance_atr=_distance_ratio(abs(current_price - support_price) if support_price else None, atr_intraday),
        invalidation_distance_atr=_distance_ratio(abs(current_price - bullish_inv_ref) if bullish_inv_ref else None, atr_intraday),
        near_trigger=_is_near_level(abs(current_price - support_price) if support_price else None, atr_intraday),
        trigger_confirmed=(breakout_status_bu in ["true_breakout", "pullback_valid"]),
        rationale=bullish_reasons + (b_out2.reasons if b_out2 else [])
    ))

    # --- Scalp Scenarios ---
    scalp_dir = bias.entry.direction
    if scalp_dir != "mixed":
        rel_to_htf = "aligned_with_htf" if scalp_dir == bias.htf.direction else f"counter_trend_bounce_within_htf_{bias.htf.direction}"
        
        sd_price = None
        sd_fresh = False
        if scalp_dir == "bullish" and levels.demand_zones:
            sd_price = levels.demand_zones[0].price
            sd_fresh = levels.demand_zones[0].is_fresh
        elif scalp_dir == "bearish" and levels.supply_zones:
            sd_price = levels.supply_zones[0].price
            sd_fresh = levels.supply_zones[0].is_fresh
            
        b_out_scalp = classify_breakout(candles_m15, sd_price, "zone", scalp_dir) if sd_price and candles_m15 else None
        b_status_scalp = b_out_scalp.status if b_out_scalp else "awaiting"
        
        score_scalp, conv_scalp = _score_confluence(context, scalp_dir, b_status_scalp, patterns_b, sd_fresh, False)
        
        scalp_scenarios.append(Scenario(
            name=f"scalp_{scalp_dir}_{rel_to_htf}",
            direction=scalp_dir,
            status="active" if conv_scalp == "high" and b_status_scalp in ["true_breakout", "pullback_valid"] else "conditional",
            trigger=f"bounce_at_zone_{sd_price}" if sd_price else "momentum_continuation",
            invalidation=f"break_zone_{sd_price}" if sd_price else "momentum_loss",
            breakout_status=b_status_scalp,
            conviction=conv_scalp,
            confluence_score=score_scalp,
            trigger_reference=sd_price,
            invalidation_reference=None,
            trigger_distance=abs(current_price - sd_price) if sd_price else None,
            invalidation_distance=None,
            atr_reference=atr_scalp,
            trigger_distance_atr=_distance_ratio(abs(current_price - sd_price) if sd_price else None, atr_scalp),
            invalidation_distance_atr=None,
            near_trigger=_is_near_level(abs(current_price - sd_price) if sd_price else None, atr_scalp),
            trigger_confirmed=(b_status_scalp in ["true_breakout", "pullback_valid"]),
            rationale=[f"entry_bias_{scalp_dir}", rel_to_htf] + (b_out_scalp.reasons if b_out_scalp else [])
        ))

    # Evaluate additional nearby support levels as distinct candidates. A single
    # nearest-level scenario can have poor RR while a valid second level offers
    # a better conditional setup; preserve both for ranking instead of hiding it.
    base_bearish = intraday_scenarios[0]
    base_bullish = intraday_scenarios[1]
    extra_supports = [
        zone for zone in levels.supports
        if zone.price < current_price
        and (support_price is None or abs(zone.price - support_price) > 1e-9)
    ][:2]

    for index, zone in enumerate(extra_supports, start=2):
        level = zone.price
        bearish_result = classify_breakout(
            candles_m15, level, "support", "bearish"
        ) if candles_m15 else None
        bearish_status = bearish_result.status if bearish_result else "awaiting"
        bearish_score, bearish_conviction = _score_confluence(
            context, "bearish", bearish_status, patterns_b, zone.is_fresh, has_conflict
        )
        intraday_scenarios.append(replace(
            base_bearish,
            name=f"bearish_continuation_support_{index}",
            status="active" if bearish_conviction == "high" and bearish_status in {"true_breakout", "pullback_valid"} else "conditional",
            trigger=f"break_and_hold_below_support_{level}",
            invalidation=f"price_reclaims_above_nearest_resistance_{resistance_price}" if resistance_price else "price_reclaims_nearest_resistance",
            breakout_status=bearish_status,
            conviction=bearish_conviction,
            confluence_score=bearish_score,
            trigger_reference=level,
            trigger_distance=abs(current_price - level),
            trigger_distance_atr=_distance_ratio(abs(current_price - level), atr_intraday),
            near_trigger=_is_near_level(abs(current_price - level), atr_intraday),
            trigger_confirmed=(bearish_status in {"true_breakout", "pullback_valid"}),
            rationale=bearish_reasons + (bearish_result.reasons if bearish_result else []) + ["alternative_support_candidate"],
        ))

        bullish_result = classify_support_rejection(
            candles_m15, level
        ) if candles_m15 else None
        bullish_status = bullish_result.status if bullish_result else "awaiting"
        bullish_score, bullish_conviction = _score_confluence(
            context, "bullish", bullish_status, patterns_b, zone.is_fresh, has_conflict
        )
        bullish_invalidation = level - (atr_intraday * 0.25) if atr_intraday else None
        intraday_scenarios.append(replace(
            base_bullish,
            name=f"bullish_reversal_support_{index}",
            status="active" if bullish_conviction == "high" and bullish_status in {"true_breakout", "pullback_valid"} else "conditional",
            trigger=f"hold_and_reject_from_support_{level}",
            invalidation=f"break_below_support_buffer_{bullish_invalidation}" if bullish_invalidation else f"break_below_support_{level}",
            breakout_status=bullish_status,
            conviction=bullish_conviction,
            confluence_score=bullish_score,
            trigger_reference=level,
            invalidation_reference=bullish_invalidation,
            trigger_distance=abs(current_price - level),
            invalidation_distance=abs(current_price - bullish_invalidation) if bullish_invalidation is not None else None,
            trigger_distance_atr=_distance_ratio(abs(current_price - level), atr_intraday),
            invalidation_distance_atr=_distance_ratio(abs(current_price - bullish_invalidation) if bullish_invalidation is not None else None, atr_intraday),
            near_trigger=_is_near_level(abs(current_price - level), atr_intraday),
            trigger_confirmed=(bullish_status in {"true_breakout", "pullback_valid"}),
            rationale=bullish_reasons + (bullish_result.reasons if bullish_result else []) + ["alternative_support_candidate"],
        ))

    return ScenarioAnalysis(
        symbol=context.symbol,
        current_price=current_price,
        intraday_scenarios=intraday_scenarios,
        scalp_scenarios=scalp_scenarios,
    )


def print_scenarios(analysis: ScenarioAnalysis) -> None:
    print("\n=== SCENARIO ANALYSIS ===")
    print(f"SYMBOL : {analysis.symbol}")
    print(f"PRICE  : {analysis.current_price}")

    for scenario in analysis.scenarios:
        print(f"\n[{scenario.name.upper()}]")
        print(f"DIRECTION   : {scenario.direction}")
        print(f"STATUS      : {scenario.status}")
        print(f"CONVICTION  : {scenario.conviction} ({scenario.confluence_score})")
        print(f"BREAKOUT    : {scenario.breakout_status}")
        print(f"TRIGGER     : {scenario.trigger}")
        print(f"INVALIDATION: {scenario.invalidation}")
        print(f"TRIGGER REF : {scenario.trigger_reference}")
        if scenario.rationale:
            print("RATIONALE:")
            for reason in scenario.rationale:
                print(f"  - {reason}")
