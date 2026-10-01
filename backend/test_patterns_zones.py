from datetime import datetime, timezone
from app.services.market_data.base import Candle
from app.services.technical.candlestick_patterns import detect_patterns
from app.services.analysis.breakout_classifier import classify_breakout

def create_candle(o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        time_utc=datetime.now(timezone.utc),
        open=o,
        high=h,
        low=l,
        close=c,
        tick_volume=100
    )

def test_pin_bar():
    # Bullish pin bar: small body, long lower wick
    c = create_candle(1.050, 1.055, 1.010, 1.052)
    patterns = detect_patterns([c], at_zone=True)
    assert len(patterns) == 1
    assert patterns[0].name == "pin_bar"
    assert patterns[0].direction == "bullish"
    assert patterns[0].strength == "strong"

def test_engulfing():
    c1 = create_candle(1.050, 1.055, 1.045, 1.048) # Bearish
    c2 = create_candle(1.045, 1.060, 1.040, 1.055) # Bullish, engulfing body
    patterns = detect_patterns([c1, c2], at_zone=False)
    assert len(patterns) == 1
    assert patterns[0].name == "engulfing"
    assert patterns[0].direction == "bullish"
    assert patterns[0].strength == "moderate"

def test_breakout_classifier():
    c1 = create_candle(1.040, 1.045, 1.035, 1.042)
    c2 = create_candle(1.045, 1.060, 1.042, 1.055)
    # Resistance at 1.050
    # c1 is below, c2 breaks and closes above
    res = classify_breakout([c1, c2], 1.050, "resistance", "bullish")
    assert res.status == "true_breakout"
    assert res.direction == "bullish"

if __name__ == "__main__":
    test_pin_bar()
    test_engulfing()
    test_breakout_classifier()
    print("test_patterns_zones.py passed!")
