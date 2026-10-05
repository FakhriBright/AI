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
    # New design: pin_bar and hammer are both emitted for the same wick shape
    c = create_candle(1.050, 1.055, 1.010, 1.052)
    patterns = detect_patterns([c], at_zone=True)
    names = [p.name for p in patterns]
    dirs = {p.name: p.direction for p in patterns}
    strengths = {p.name: p.strength for p in patterns}
    # Must include pin_bar with correct direction and strength
    assert "pin_bar" in names, f"pin_bar not found in {names}"
    assert dirs["pin_bar"] == "bullish"
    assert strengths["pin_bar"] == "strong"
    # hammer is now also emitted for the same shape
    assert "hammer" in names, f"hammer not found in {names}"
    assert dirs["hammer"] == "bullish"
    # All patterns must be bullish (lower-wick candle)
    for p in patterns:
        assert p.direction in ("bullish", "neutral"), f"Unexpected bearish pattern: {p.name}"

def test_engulfing():
    c1 = create_candle(1.050, 1.055, 1.045, 1.048)  # Bearish
    c2 = create_candle(1.045, 1.060, 1.040, 1.055)  # Bullish, engulfing body
    patterns = detect_patterns([c1, c2], at_zone=False)
    names = [p.name for p in patterns]
    dirs = {p.name: p.direction for p in patterns}
    # bullish_engulfing and engulfing are both emitted for the same formation
    assert "bullish_engulfing" in names, f"bullish_engulfing not found in {names}"
    assert dirs["bullish_engulfing"] == "bullish"
    assert "engulfing" in names, f"engulfing not found in {names}"
    assert dirs["engulfing"] == "bullish"
    # All engulfing-family patterns must be bullish
    for p in patterns:
        assert p.direction in ("bullish", "neutral"), f"Unexpected direction for {p.name}: {p.direction}"

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
