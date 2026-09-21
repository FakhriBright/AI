from dataclasses import dataclass
from typing import Literal


TrendDirection = Literal["bullish", "bearish", "mixed", "neutral"]


@dataclass
class TrendAnalysis:
    direction: TrendDirection

    price: float

    ema20: float
    ema50: float
    ema200: float

    structure: str

    price_vs_ema20: str
    price_vs_ema50: str
    price_vs_ema200: str

    ema_alignment: str

    reasons: list[str]


def _price_position(price: float, ema: float) -> str:
    if price > ema:
        return "above"
    if price < ema:
        return "below"
    return "at"


def analyze_trend(
    price: float,
    ema20: float,
    ema50: float,
    ema200: float,
    structure: str,
) -> TrendAnalysis:

    price_vs_ema20 = _price_position(price, ema20)
    price_vs_ema50 = _price_position(price, ema50)
    price_vs_ema200 = _price_position(price, ema200)

    if ema20 > ema50 > ema200:
        ema_alignment = "bullish_alignment"
    elif ema20 < ema50 < ema200:
        ema_alignment = "bearish_alignment"
    else:
        ema_alignment = "mixed_alignment"

    reasons = []

    if price > ema200:
        reasons.append("price_above_ema200")
    elif price < ema200:
        reasons.append("price_below_ema200")

    if ema_alignment == "bullish_alignment":
        reasons.append("ema20_above_ema50_above_ema200")
    elif ema_alignment == "bearish_alignment":
        reasons.append("ema20_below_ema50_below_ema200")

    if structure == "bullish":
        reasons.append("market_structure_bullish")
    elif structure == "bearish":
        reasons.append("market_structure_bearish")

    if ema_alignment == "bullish_alignment":
        if structure == "bearish":
            direction: TrendDirection = "mixed"
        else:
            direction = "bullish"

    elif ema_alignment == "bearish_alignment":
        if structure == "bullish":
            direction = "mixed"
        else:
            direction = "bearish"

    else:
        if structure == "bullish":
            direction = "bullish"
        elif structure == "bearish":
            direction = "bearish"
        else:
            direction = "neutral"

    return TrendAnalysis(
        direction=direction,
        price=price,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        structure=structure,
        price_vs_ema20=price_vs_ema20,
        price_vs_ema50=price_vs_ema50,
        price_vs_ema200=price_vs_ema200,
        ema_alignment=ema_alignment,
        reasons=reasons,
    )
