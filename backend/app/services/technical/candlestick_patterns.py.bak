from typing import Literal
from pydantic import BaseModel
from app.services.market_data.base import Candle


class PatternResult(BaseModel):
    name: str
    direction: Literal["bullish", "bearish", "neutral"]
    strength: Literal["weak", "moderate", "strong"]
    reasons: list[str]


def detect_patterns(candles: list[Candle], at_zone: bool = False) -> list[PatternResult]:
    """
    Detect candlestick patterns from the last 1-3 closed candles.
    `at_zone` indicates whether the current price action is happening right at a key S/R or SD zone.
    """
    if not candles:
        return []

    results = []
    # Use the last closed candle as the primary focus
    current = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else None
    
    body = abs(current.close - current.open)
    range_total = current.high - current.low
    
    if range_total == 0:
        return results

    upper_wick = current.high - max(current.open, current.close)
    lower_wick = min(current.open, current.close) - current.low

    # 1. Pin bar / Rejection candle
    if body <= 0.35 * range_total:
        if lower_wick >= 2 * body and lower_wick > upper_wick:
            results.append(PatternResult(
                name="pin_bar",
                direction="bullish",
                strength="strong" if at_zone else "moderate",
                reasons=["Small body with dominant lower wick indicating buying rejection"]
            ))
        elif upper_wick >= 2 * body and upper_wick > lower_wick:
            results.append(PatternResult(
                name="pin_bar",
                direction="bearish",
                strength="strong" if at_zone else "moderate",
                reasons=["Small body with dominant upper wick indicating selling rejection"]
            ))

    # 2. Doji
    if body <= 0.10 * range_total:
        wick_ratio = upper_wick / lower_wick if lower_wick > 0 else (upper_wick / 0.0001)
        if 0.5 <= wick_ratio <= 2.0:
            results.append(PatternResult(
                name="doji",
                direction="neutral",
                strength="moderate",
                reasons=["Body is extremely small and wicks are relatively balanced (momentum warning)"]
            ))

    if prev:
        prev_body = abs(prev.close - prev.open)
        # 3. Engulfing
        # Current body completely covers previous body, opposite color
        is_current_bullish = current.close > current.open
        is_prev_bearish = prev.close < prev.open
        is_current_bearish = current.close < current.open
        is_prev_bullish = prev.close > prev.open
        
        if is_current_bullish and is_prev_bearish and current.close > prev.open and current.open < prev.close:
            results.append(PatternResult(
                name="engulfing",
                direction="bullish",
                strength="strong" if at_zone else "moderate",
                reasons=["Bullish candle completely engulfed the previous bearish body"]
            ))
        elif is_current_bearish and is_prev_bullish and current.close < prev.open and current.open > prev.close:
            results.append(PatternResult(
                name="engulfing",
                direction="bearish",
                strength="strong" if at_zone else "moderate",
                reasons=["Bearish candle completely engulfed the previous bullish body"]
            ))

        # 4. Inside bar
        if current.high <= prev.high and current.low >= prev.low:
            results.append(PatternResult(
                name="inside_bar",
                direction="neutral",
                strength="moderate",
                reasons=["Price action is completely contained within the previous candle (awaiting breakout)"]
            ))

    return results
