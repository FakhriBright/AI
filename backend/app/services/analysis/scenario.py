from dataclasses import dataclass, field

from app.services.analysis.context import MultiTimeframeContext
from app.services.analysis.bias import MarketBias
from app.services.analysis.levels import KeyLevels


@dataclass
class Scenario:
    name: str
    direction: str
    status: str
    trigger: str
    invalidation: str

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
    scenarios: list[Scenario] = field(default_factory=list)


def _nearest_support(levels: KeyLevels):
    if not levels.supports:
        return None
    return levels.supports[0]


def _nearest_resistance(levels: KeyLevels):
    if not levels.resistances:
        return None
    return levels.resistances[0]


def _get_entry_atr(context: MultiTimeframeContext) -> float | None:
    """
    ATR M5 dipakai sebagai reference volatilitas entry/scalping.
    Kalau M5 tidak tersedia, fallback ke M15.
    """
    for timeframe in ("M5", "M15"):
        data = context.timeframes.get(timeframe)
        if data is not None and data.atr14 is not None:
            return data.atr14

    return None


def _distance_ratio(distance: float | None, atr: float | None) -> float | None:
    if distance is None or atr is None or atr <= 0:
        return None

    return distance / atr


def _is_near_level(distance: float | None, atr: float | None) -> bool:
    """
    Level dianggap dekat apabila jaraknya <= 25% ATR reference.
    Ini hanya klasifikasi konteks, bukan sinyal entry.
    """
    if distance is None or atr is None or atr <= 0:
        return False

    return distance <= atr * 0.25


def build_scenarios(
    context: MultiTimeframeContext,
    bias: MarketBias,
    levels: KeyLevels,
) -> ScenarioAnalysis:

    current_price = levels.current_price

    nearest_support = _nearest_support(levels)
    nearest_resistance = _nearest_resistance(levels)

    support_price = (
        nearest_support.price
        if nearest_support is not None
        else None
    )

    resistance_price = (
        nearest_resistance.price
        if nearest_resistance is not None
        else None
    )

    atr_reference = _get_entry_atr(context)

    support_distance = (
        abs(current_price - support_price)
        if support_price is not None
        else None
    )

    resistance_distance = (
        abs(resistance_price - current_price)
        if resistance_price is not None
        else None
    )

    support_distance_atr = _distance_ratio(
        support_distance,
        atr_reference,
    )

    resistance_distance_atr = _distance_ratio(
        resistance_distance,
        atr_reference,
    )

    # ---------------------------------------------------------
    # BEARISH CONTINUATION
    # ---------------------------------------------------------

    bearish_reasons = []

    if bias.overall == "bearish":
        bearish_reasons.append("overall_bias_bearish")

    if bias.intraday.direction == "bearish":
        bearish_reasons.append("intraday_bias_bearish")

    if bias.entry.direction == "bearish":
        bearish_reasons.append("entry_bias_bearish")

    bearish_trigger = (
        f"break_and_hold_below_support_{support_price}"
        if support_price is not None
        else "break_below_nearest_support"
    )

    bearish_invalidation = (
        f"price_reclaims_above_nearest_resistance_{resistance_price}"
        if resistance_price is not None
        else "price_reclaims_nearest_resistance"
    )

    bearish_scenario = Scenario(
        name="bearish_continuation",
        direction="bearish",
        status="conditional",
        trigger=bearish_trigger,
        invalidation=bearish_invalidation,

        # Ini reference level, BUKAN executable entry.
        trigger_reference=support_price,
        invalidation_reference=resistance_price,

        trigger_distance=support_distance,
        invalidation_distance=resistance_distance,

        atr_reference=atr_reference,

        trigger_distance_atr=support_distance_atr,
        invalidation_distance_atr=resistance_distance_atr,

        near_trigger=_is_near_level(
            support_distance,
            atr_reference,
        ),

        # Belum ada candle/price confirmation engine.
        trigger_confirmed=False,

        rationale=bearish_reasons,
    )

    # ---------------------------------------------------------
    # BULLISH REVERSAL
    # ---------------------------------------------------------

    bullish_reasons = []

    if bias.overall == "bullish":
        bullish_reasons.append("overall_bias_bullish")

    if bias.entry.direction == "bullish":
        bullish_reasons.append("entry_bias_bullish")

    if bias.htf.direction == "bullish":
        bullish_reasons.append("higher_timeframe_bias_bullish")

    bullish_trigger = (
        f"hold_and_reject_from_support_{support_price}"
        if support_price is not None
        else "bullish_rejection_from_support"
    )

    bullish_invalidation_reference = (
        support_price - (atr_reference * 0.25)
        if support_price is not None and atr_reference is not None
        else None
    )

    bullish_invalidation = (
        f"break_below_support_buffer_{bullish_invalidation_reference}"
        if bullish_invalidation_reference is not None
        else "break_below_nearest_support"
    )

    bullish_invalidation_distance = (
        abs(current_price - bullish_invalidation_reference)
        if bullish_invalidation_reference is not None
        else None
    )

    bullish_invalidation_distance_atr = _distance_ratio(
        bullish_invalidation_distance,
        atr_reference,
    )

    bullish_scenario = Scenario(
        name="bullish_reversal",
        direction="bullish",
        status="conditional",
        trigger=bullish_trigger,
        invalidation=bullish_invalidation,

        trigger_reference=support_price,
        invalidation_reference=bullish_invalidation_reference,

        trigger_distance=support_distance,
        invalidation_distance=bullish_invalidation_distance,

        atr_reference=atr_reference,

        trigger_distance_atr=support_distance_atr,
        invalidation_distance_atr=bullish_invalidation_distance_atr,

        near_trigger=_is_near_level(
            support_distance,
            atr_reference,
        ),

        trigger_confirmed=False,

        rationale=bullish_reasons,
    )

    # ---------------------------------------------------------
    # RANGE / NO CLEAR SETUP
    # ---------------------------------------------------------

    range_reasons = []

    if bias.overall == "mixed":
        range_reasons.append("overall_bias_mixed")

    if bias.conflicts:
        range_reasons.append("timeframe_conflict_detected")

    range_trigger = (
        f"price_remains_between_{support_price}_and_{resistance_price}"
        if support_price is not None and resistance_price is not None
        else "price_remains_without_directional_confirmation"
    )

    range_scenario = Scenario(
        name="range_or_no_clear_setup",
        direction="neutral",
        status="conditional",
        trigger=range_trigger,
        invalidation="clear_breakout_with_confirmation",

        trigger_reference=None,
        invalidation_reference=None,

        atr_reference=atr_reference,

        trigger_confirmed=False,

        rationale=range_reasons,
    )

    return ScenarioAnalysis(
        symbol=context.symbol,
        current_price=current_price,
        scenarios=[
            bearish_scenario,
            bullish_scenario,
            range_scenario,
        ],
    )


def print_scenarios(analysis: ScenarioAnalysis) -> None:

    print("\n=== SCENARIO ANALYSIS ===")
    print(f"SYMBOL : {analysis.symbol}")
    print(f"PRICE  : {analysis.current_price}")

    for scenario in analysis.scenarios:

        print(f"\n[{scenario.name.upper()}]")

        print(f"DIRECTION   : {scenario.direction}")
        print(f"STATUS      : {scenario.status}")

        print(f"TRIGGER     : {scenario.trigger}")
        print(f"INVALIDATION: {scenario.invalidation}")

        print(f"TRIGGER REF : {scenario.trigger_reference}")
        print(f"INVALID REF : {scenario.invalidation_reference}")

        print(f"TRIGGER DIST: {scenario.trigger_distance}")
        print(f"INVALID DIST: {scenario.invalidation_distance}")

        print(f"ATR REF     : {scenario.atr_reference}")

        print(
            f"TRIGGER/ATR : {scenario.trigger_distance_atr}"
        )

        print(
            f"INVALID/ATR : {scenario.invalidation_distance_atr}"
        )

        print(f"NEAR TRIGGER: {scenario.near_trigger}")
        print(f"CONFIRMED   : {scenario.trigger_confirmed}")

        if scenario.rationale:
            print("RATIONALE:")

            for reason in scenario.rationale:
                print(f"  - {reason}")
