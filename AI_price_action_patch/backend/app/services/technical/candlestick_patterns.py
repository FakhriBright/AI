"""Deterministic candlestick pattern recognition on CLOSED OHLC candles.

Patterns are observations, not trade signals. Context, location and follow-through
must be evaluated separately by the scenario engine.

Supports SMC/ICT/SNR context:
  - Pin bar / Hammer / Shooting star as liquidity-sweep / rejection confirmations
  - Engulfing as displacement / order-flow shift signal
  - Inside bar as consolidation before BOS/CHoCH
  - Doji variants as indecision at POI (Point of Interest)
  - Multi-candle patterns (Star families, Harami, Soldiers/Crows) for HTF confirmation
"""
from typing import Literal
from pydantic import BaseModel
from app.services.market_data.base import Candle

Direction = Literal["bullish", "bearish", "neutral"]
Strength = Literal["weak", "moderate", "strong"]

class PatternResult(BaseModel):
    name: str
    direction: Direction
    strength: Strength
    reasons: list[str]
    impact: str = "Context clue only; wait for follow-through."
    confirmation: str = "Require a subsequent closed candle or structure confirmation."


def _body(c: Candle) -> float:
    return abs(c.close - c.open)

def _rng(c: Candle) -> float:
    return max(0.0, c.high - c.low)

def _bull(c: Candle) -> bool: return c.close > c.open
def _bear(c: Candle) -> bool: return c.close < c.open
def _mid(c: Candle) -> float: return (c.open + c.close) / 2

def _add(out, name, direction, strength, reason, confirmation=None):
    out.append(PatternResult(
        name=name,
        direction=direction,
        strength=strength,
        reasons=[reason],
        impact=(
            "Potential bullish rejection/reversal; not a standalone buy." if direction == "bullish"
            else "Potential bearish rejection/reversal; not a standalone sell." if direction == "bearish"
            else "Indecision/compression; wait for range resolution."
        ),
        confirmation=confirmation or (
            "Wait for bullish structure break or a follow-through close above the pattern high." if direction == "bullish"
            else "Wait for bearish structure break or a follow-through close below the pattern low." if direction == "bearish"
            else "Wait for a decisive close outside the pattern range."
        )
    ))


def detect_patterns(candles: list[Candle], at_zone: bool = False) -> list[PatternResult]:
    """Detect common 1-3 candle patterns. Pass only completed candles, oldest first."""
    if not candles:
        return []
    out: list[PatternResult] = []
    c = candles[-1]
    p = candles[-2] if len(candles) > 1 else None
    pp = candles[-3] if len(candles) > 2 else None

    r = _rng(c)
    if r <= 0:
        return out

    b = _body(c)
    uw = c.high - max(c.open, c.close)
    lw = min(c.open, c.close) - c.low
    small = b <= .30 * r
    loc = " at a supplied key zone" if at_zone else ""

    # Single-candle rejection — bullish (lower wick)
    if small and lw >= 2 * max(b, r * .01) and uw <= .35 * r:
        _add(out, "pin_bar", "bullish", "strong" if at_zone else "moderate",
             f"Small body with long lower wick{loc}; lower-shadow liquidity sweep")
        _add(out, "hammer", "bullish", "strong" if at_zone else "moderate",
             f"Hammer: small body, long lower wick{loc}; demand absorption")

    # Single-candle rejection — bearish (upper wick)
    if small and uw >= 2 * max(b, r * .01) and lw <= .35 * r:
        _add(out, "pin_bar", "bearish", "strong" if at_zone else "moderate",
             f"Long upper wick rejection{loc}; upper-shadow liquidity sweep")
        _add(out, "shooting_star", "bearish", "strong" if at_zone else "moderate",
             f"Shooting star: long upper wick{loc}; supply absorption")
        _add(out, "inverted_hammer", "bullish", "moderate",
             f"Inverted hammer: upper wick in potential reversal zone{loc}")

    # Doji variants — body <= 5% of range
    if b <= .05 * r:
        if uw <= .10 * r and lw >= .65 * r:
            _add(out, "dragonfly_doji", "bullish", "moderate",
                 "Dragonfly doji: long lower shadow; bullish rejection")
        elif lw <= .10 * r and uw >= .65 * r:
            _add(out, "gravestone_doji", "bearish", "moderate",
                 "Gravestone doji: long upper shadow; bearish rejection")
        elif .35 * r <= uw <= .65 * r and .35 * r <= lw <= .65 * r:
            _add(out, "long_legged_doji", "neutral", "moderate",
                 "Long-legged doji: balanced two-sided shadows; strong indecision")
        else:
            _add(out, "doji", "neutral", "weak",
                 "Doji: open ≈ close; indecision")

    if b <= .08 * r and uw <= .08 * r and lw <= .08 * r:
        _add(out, "four_price_doji", "neutral", "weak",
             "Four-price doji: OHLC compressed to nearly one price")

    if b >= .88 * r:
        dir_ = "bullish" if _bull(c) else "bearish" if _bear(c) else "neutral"
        _add(out, "marubozu", dir_, "strong",
             f"Marubozu: body dominates range; strong {dir_} displacement")

    if .10 * r < b <= .35 * r and uw >= .20 * r and lw >= .20 * r:
        _add(out, "spinning_top", "neutral", "weak",
             "Spinning top: small body, balanced wicks; indecision")

    if p:
        pr = _rng(p)
        pb = _body(p)

        if c.high <= p.high and c.low >= p.low:
            _add(out, "inside_bar", "neutral", "moderate",
                 "Inside bar: consolidation within mother bar; watch for BOS/CHoCH",
                 "Wait for a closed breakout; wick-only breach is not confirmation.")

        if _bull(c) and _bear(p) and c.open <= p.close and c.close >= p.open and b >= pb:
            _add(out, "bullish_engulfing", "bullish", "strong" if at_zone else "moderate",
                 f"Bullish engulfing{loc}; potential demand OB")
            _add(out, "engulfing", "bullish", "strong" if at_zone else "moderate",
                 f"Bullish engulfing body{loc}")

        if _bear(c) and _bull(p) and c.open >= p.close and c.close <= p.open and b >= pb:
            _add(out, "bearish_engulfing", "bearish", "strong" if at_zone else "moderate",
                 f"Bearish engulfing{loc}; potential supply OB")
            _add(out, "engulfing", "bearish", "strong" if at_zone else "moderate",
                 f"Bearish engulfing body{loc}")

        if pb > 0 and b < pb * .60 and min(c.open, c.close) >= min(p.open, p.close) and max(c.open, c.close) <= max(p.open, p.close):
            name = "bullish_harami" if _bear(p) else "bearish_harami" if _bull(p) else "harami"
            dir_ = "bullish" if _bear(p) else "bearish" if _bull(p) else "neutral"
            _add(out, name, dir_, "moderate",
                 "Harami: small body inside prior; momentum pause")

        if _bull(c) and _bear(p) and c.open < p.low and c.close > _mid(p) and c.close < p.open:
            _add(out, "piercing_line", "bullish", "moderate",
                 "Piercing line: bullish close > midpoint of prior bearish body")
        if _bear(c) and _bull(p) and c.open > p.high and c.close < _mid(p) and c.close > p.open:
            _add(out, "dark_cloud_cover", "bearish", "moderate",
                 "Dark cloud cover: bearish close < midpoint of prior bullish body")

        if abs(c.low - p.low) <= .10 * max(pr, r) and _bear(p) and _bull(c):
            _add(out, "matching_low", "bullish", "weak",
                 "Matching lows: potential double-bottom / SNR demand")
        if abs(c.high - p.high) <= .10 * max(pr, r) and _bull(p) and _bear(c):
            _add(out, "matching_high", "bearish", "weak",
                 "Matching highs: potential double-top / SNR supply")

        if abs(c.low - p.low) <= .08 * max(pr, r):
            _add(out, "tweezer_bottom", "bullish", "moderate",
                 "Tweezer bottom: equal lows; double-test of demand / SNR support")
        if abs(c.high - p.high) <= .08 * max(pr, r):
            _add(out, "tweezer_top", "bearish", "moderate",
                 "Tweezer top: equal highs; double-test of supply / SNR resistance")

        if _bull(c) and _bear(p) and c.open >= p.open and c.close >= p.close and abs(c.open - p.open) <= .10 * max(pr, r):
            _add(out, "bullish_kicker", "bullish", "moderate",
                 "Bullish kicker: sharp upward shift; FX gap may be absent")
        if _bear(c) and _bull(p) and c.open <= p.open and c.close <= p.close and abs(c.open - p.open) <= .10 * max(pr, r):
            _add(out, "bearish_kicker", "bearish", "moderate",
                 "Bearish kicker: sharp downward shift; FX gap may be absent")

        if _bull(c) and _bear(p) and abs(c.open - p.close) <= .08 * max(pr, r) and c.close > p.high:
            _add(out, "bullish_belt_hold", "bullish", "moderate",
                 "Bullish belt hold: opens near prior close, drives above prior high")
        if _bear(c) and _bull(p) and abs(c.open - p.close) <= .08 * max(pr, r) and c.close < p.low:
            _add(out, "bearish_belt_hold", "bearish", "moderate",
                 "Bearish belt hold: opens near prior close, drives below prior low")

    if pp and p:
        mid_small = _body(p) <= .35 * max(_rng(p), 1e-12)

        if _bear(pp) and mid_small and _bull(c) and c.close > _mid(pp):
            _add(out, "morning_star", "bullish", "strong" if at_zone else "moderate",
                 "Morning star: bearish → pause → bullish recovery; HTF reversal signal")
        if _bull(pp) and mid_small and _bear(c) and c.close < _mid(pp):
            _add(out, "evening_star", "bearish", "strong" if at_zone else "moderate",
                 "Evening star: bullish → pause → bearish recovery; HTF reversal signal")
        if _bear(pp) and mid_small and _bull(c) and _body(p) <= .10 * max(_rng(p), 1e-12):
            _add(out, "morning_doji_star", "bullish", "moderate",
                 "Morning doji star: doji middle strengthens reversal")
        if _bull(pp) and mid_small and _bear(c) and _body(p) <= .10 * max(_rng(p), 1e-12):
            _add(out, "evening_doji_star", "bearish", "moderate",
                 "Evening doji star: doji middle strengthens reversal")

        if _bear(pp) and _bull(p) and _bull(c) and p.open < pp.close and p.close > pp.open and c.close > p.close:
            _add(out, "three_inside_up", "bullish", "moderate",
                 "Three inside up: harami confirmed by bullish close; CHoCH signal")

        if _bull(pp) and _bear(p) and _bear(c) and p.open > pp.close and p.close < pp.open and c.close < pp.close:
            _add(out, "three_inside_down", "bearish", "moderate",
                 "Three inside down: harami confirmed by bearish close; CHoCH signal")

        if _bull(pp) and _bull(p) and _bull(c) and pp.close < p.close < c.close and pp.open < p.open < c.open:
            _add(out, "three_white_soldiers", "bullish", "moderate",
                 "Three white soldiers: three rising bullish bodies; strong order flow; beware overextension")
        if _bear(pp) and _bear(p) and _bear(c) and pp.close > p.close > c.close and pp.open > p.open > c.open:
            _add(out, "three_black_crows", "bearish", "moderate",
                 "Three black crows: three falling bearish bodies; strong order flow; beware overextension")

    # Deduplicate: keep first occurrence per (name, direction) pair
    seen: set = set()
    unique: list[PatternResult] = []
    for item in out:
        key = (item.name, item.direction)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique
