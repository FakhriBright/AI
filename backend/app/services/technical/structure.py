from dataclasses import dataclass
from typing import Literal


SwingType = Literal["swing_high", "swing_low"]
StructureLabel = Literal["HH", "LH", "HL", "LL"]


@dataclass
class SwingPoint:
    time_utc: object
    price: float
    type: SwingType
    label: StructureLabel | None = None


def find_swings(
    highs: list[float],
    lows: list[float],
    times: list[object] | None = None,
    lookback: int = 3,
) -> list[SwingPoint]:

    if len(highs) != len(lows):
        raise ValueError("highs and lows must have the same length")

    if times is not None and len(times) != len(highs):
        raise ValueError("times must have the same length as highs/lows")

    swings: list[SwingPoint] = []

    for i in range(lookback, len(highs) - lookback):

        current_high = highs[i]
        current_low = lows[i]

        left_highs = highs[i - lookback:i]
        right_highs = highs[i + 1:i + lookback + 1]

        left_lows = lows[i - lookback:i]
        right_lows = lows[i + 1:i + lookback + 1]

        is_swing_high = (
            current_high >= max(left_highs)
            and current_high >= max(right_highs)
        )

        is_swing_low = (
            current_low <= min(left_lows)
            and current_low <= min(right_lows)
        )

        time_utc = times[i] if times is not None else i

        if is_swing_high:
            swings.append(
                SwingPoint(
                    time_utc=time_utc,
                    price=current_high,
                    type="swing_high",
                )
            )

        if is_swing_low:
            swings.append(
                SwingPoint(
                    time_utc=time_utc,
                    price=current_low,
                    type="swing_low",
                )
            )

    swings.sort(key=lambda swing: swing.time_utc)

    swings = _clean_swings(swings)

    return label_swings(swings)


def _clean_swings(swings: list[SwingPoint]) -> list[SwingPoint]:
    """
    Ensure swing points alternate between highs and lows.

    If consecutive candidates have the same type:
    - keep the more extreme high when both are swing highs
    - keep the more extreme low when both are swing lows
    """

    if not swings:
        return []

    cleaned: list[SwingPoint] = [swings[0]]

    for current in swings[1:]:
        previous = cleaned[-1]

        if current.type != previous.type:
            cleaned.append(current)
            continue

        if current.type == "swing_high":
            if current.price > previous.price:
                cleaned[-1] = current
        else:
            if current.price < previous.price:
                cleaned[-1] = current

    return cleaned


def label_swings(swings: list[SwingPoint]) -> list[SwingPoint]:

    previous_high: float | None = None
    previous_low: float | None = None

    labeled: list[SwingPoint] = []

    for swing in swings:

        if swing.type == "swing_high":

            if previous_high is None:
                label = None
            elif swing.price > previous_high:
                label = "HH"
            elif swing.price < previous_high:
                label = "LH"
            else:
                label = None

            previous_high = swing.price

        else:

            if previous_low is None:
                label = None
            elif swing.price > previous_low:
                label = "HL"
            elif swing.price < previous_low:
                label = "LL"
            else:
                label = None

            previous_low = swing.price

        labeled.append(
            SwingPoint(
                time_utc=swing.time_utc,
                price=swing.price,
                type=swing.type,
                label=label,
            )
        )

    return labeled


def classify_structure(
    swings: list[SwingPoint],
) -> str:

    if not swings:
        return "neutral"

    highs = [
        swing for swing in swings
        if swing.type == "swing_high" and swing.label is not None
    ]

    lows = [
        swing for swing in swings
        if swing.type == "swing_low" and swing.label is not None
    ]

    if not highs or not lows:
        return "neutral"

    latest_high = highs[-1].label
    latest_low = lows[-1].label

    # Bullish structure:
    # Higher High + Higher Low
    if latest_high == "HH" and latest_low == "HL":
        return "bullish"

    # Bearish structure:
    # Lower High + Lower Low
    if latest_high == "LH" and latest_low == "LL":
        return "bearish"

    return "mixed"
