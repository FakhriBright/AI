from typing import Literal
from pydantic import BaseModel
from app.services.market_data.base import Candle
from app.services.technical.candlestick_patterns import detect_patterns

BreakoutStatus = Literal[
    "true_breakout", 
    "false_breakout", 
    "pullback_valid", 
    "pullback_failed", 
    "awaiting"
]

class BreakoutClassification(BaseModel):
    status: BreakoutStatus
    direction: Literal["bullish", "bearish", "neutral"]
    reasons: list[str]


def classify_breakout(
    candles: list[Candle], 
    level: float, 
    level_type: Literal["support", "resistance", "zone"] = "resistance",
    expected_breakout_dir: Literal["bullish", "bearish"] = "bullish"
) -> BreakoutClassification:
    """
    Classify the interaction between recent price action and a specific price level.
    """
    if not candles:
        return BreakoutClassification(status="awaiting", direction="neutral", reasons=["No candles provided"])

    current = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else None

    # Determine if level was touched
    touched_current = current.low <= level <= current.high
    touched_prev = prev and (prev.low <= level <= prev.high)
    
    if not touched_current and not touched_prev:
        # Check if we are already way past it
        if expected_breakout_dir == "bullish" and current.low > level:
            # We are above resistance, but didn't touch it recently. Could be a past breakout.
            return BreakoutClassification(
                status="true_breakout", 
                direction="bullish", 
                reasons=["Price is currently trading cleanly above the level without touching it"]
            )
        elif expected_breakout_dir == "bearish" and current.high < level:
            return BreakoutClassification(
                status="true_breakout", 
                direction="bearish", 
                reasons=["Price is currently trading cleanly below the level without touching it"]
            )
            
        return BreakoutClassification(status="awaiting", direction="neutral", reasons=["Level not yet reached"])

    # True breakout condition: body closes outside level and previous was either touching or inside
    if expected_breakout_dir == "bullish":
        if current.close > level:
            # Price closed above with its body
            if prev and prev.close > level and prev.open > level:
                 # Already broke out before, this is just continuation
                 return BreakoutClassification(
                     status="true_breakout", 
                     direction="bullish", 
                     reasons=["Price broke and continues to hold above level cleanly"]
                 )
            elif prev and prev.high > level > prev.close:
                 # Previous was false breakout or just touched, now breaking out
                 return BreakoutClassification(
                     status="true_breakout", 
                     direction="bullish", 
                     reasons=["Strong body close above resistance"]
                 )
            
            # Let's check if it's a pullback
            # If we were previously way above and now touched it but closed above
            if prev and prev.low >= level:
                patterns = detect_patterns(candles, at_zone=True)
                bullish_patterns = [p for p in patterns if p.direction == "bullish"]
                if bullish_patterns:
                    return BreakoutClassification(
                        status="pullback_valid",
                        direction="bullish",
                        reasons=[f"Price retested level from above and formed {bullish_patterns[0].name}"]
                    )
                else:
                    return BreakoutClassification(
                        status="true_breakout", # Still holding above
                        direction="bullish",
                        reasons=["Retest held above level"]
                    )
                    
            return BreakoutClassification(
                status="true_breakout",
                direction="bullish",
                reasons=["Body closed above level"]
            )
            
        elif current.high > level >= current.close:
            # Wick went above, but closed below/at
            if prev and prev.close > level:
                # We were above, now we closed below. Pullback failed!
                return BreakoutClassification(
                    status="pullback_failed",
                    direction="bearish",
                    reasons=["Price broke above previously, but has now closed back below the level"]
                )
            else:
                return BreakoutClassification(
                    status="false_breakout",
                    direction="bearish",
                    reasons=["Wick pierced level but body closed below (stop hunt / trap)"]
                )
    
    elif expected_breakout_dir == "bearish":
        if current.close < level:
            # Body closed below
            if prev and prev.close < level and prev.open < level:
                return BreakoutClassification(
                     status="true_breakout", 
                     direction="bearish", 
                     reasons=["Price broke and continues to hold below level cleanly"]
                 )
                 
            # Pullback logic
            if prev and prev.high <= level:
                patterns = detect_patterns(candles, at_zone=True)
                bearish_patterns = [p for p in patterns if p.direction == "bearish"]
                if bearish_patterns:
                    return BreakoutClassification(
                        status="pullback_valid",
                        direction="bearish",
                        reasons=[f"Price retested level from below and formed {bearish_patterns[0].name}"]
                    )
                else:
                    return BreakoutClassification(
                        status="true_breakout",
                        direction="bearish",
                        reasons=["Retest held below level"]
                    )
                    
            return BreakoutClassification(
                status="true_breakout",
                direction="bearish",
                reasons=["Body closed below level"]
            )
            
        elif current.low < level <= current.close:
            # Wick went below, but closed above
            if prev and prev.close < level:
                return BreakoutClassification(
                    status="pullback_failed",
                    direction="bullish",
                    reasons=["Price broke below previously, but has now closed back above the level"]
                )
            else:
                return BreakoutClassification(
                    status="false_breakout",
                    direction="bullish",
                    reasons=["Wick pierced level but body closed above (stop hunt / trap)"]
                )

    return BreakoutClassification(status="awaiting", direction="neutral", reasons=["No clear breakout direction established"])
