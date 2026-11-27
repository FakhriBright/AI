"""Deterministic ICT/SMC detector (single source for chart, desk brief, chat).

Runs on ONE timeframe's CLOSED candles (the forming bar must not be passed in;
the pipeline passes `evidence_candles`, which are closed only). Prices are the
exact candle prices; nothing is rounded or estimated here.

Rules (all thresholds in SMCConfig):

Swings ........ technical.structure.find_swings (fractal: `swing_lookback`
                candles on each side). A swing at bar i is CONFIRMED only once
                bar i + lookback has closed; before that it is not used.
HH/HL/LH/LL ... technical.structure.label_swings (vs previous same-type swing).
BOS / CHoCH ... a CLOSE beyond the most recent confirmed, still unbroken swing
                high (bullish) / swing low (bearish). A wick beyond it is not a
                break (see sweeps). CHoCH = the first break against the current
                structure direction (bearish -> bullish break, or vice versa);
                every other break is a BOS. The very first break of the series
                has no prior direction and is a BOS marked `initial`.
FVG ........... 3-candle imbalance: bullish if low(c3) > high(c1) (zone
                high(c1)..low(c3)), bearish if high(c3) < low(c1) (zone
                high(c3)..low(c1)). Gap must be >= max(fvg_min_gap_atr * ATR,
                1 point). Lifecycle from later CLOSED candles: fresh -> partial
                (price entered the gap, fill_pct) -> filled (opposite edge
                reached = mitigated) or invalidated (a close beyond the far
                edge). Zone starts at c1, is confirmed at c3.
Order block ... only where a BOS/CHoCH happened: the last opposing candle
                (bearish candle for a bullish break) at or before the origin of
                the leg (lowest low between the broken swing and the break bar,
                for a bullish break), searched back up to `ob_search_back`
                candles. The leg must contain a displacement candle (body >=
                ob_displacement_body_mult x average body of the previous
                `ob_body_window` candles) in the break direction. Zone = FULL
                candle range (low..high, wick to wick) of the OB candle.
                Lifecycle after the break bar: fresh -> mitigated (price trades
                back into the zone) or invalidated (close beyond the far edge).
Liquidity ..... BSL = confirmed swing highs, SSL = confirmed swing lows. A pool
                is "taken" at the first later candle trading beyond it.
                That candle is a SWEEP if it closed back inside (wick only),
                otherwise a BREAKOUT (close beyond) - never both.
                EQH/EQL: consecutive same-type swings within
                max(eq_tolerance_atr x ATR, eq_min_points x point) - volatility
                based, so the same rule works for XAU (3 digits) and FX (5).
Dealing range . last confirmed swing high + last confirmed swing low;
                equilibrium = 50 %; premium above 55 %, discount below 45 %
                (45-55 % = equilibrium band). Price outside the range -> no
                premium/discount read (`outside_range`).

Not supported (never emitted): IFVG, BPR, trend channels, breaker / mitigation
blocks, volume imbalance, liquidity voids.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from app.services.technical.structure import find_swings

UNSUPPORTED = ("IFVG", "BPR", "trend_channel", "breaker_block", "mitigation_block", "volume_imbalance")


@dataclass(frozen=True)
class SMCConfig:
    swing_lookback: int = 3
    atr_period: int = 14
    fvg_min_gap_atr: float = 0.10
    ob_displacement_body_mult: float = 1.5
    ob_body_window: int = 14
    ob_search_back: int = 10
    eq_tolerance_atr: float = 0.10
    eq_min_points: int = 2
    # Relevance limits (what is handed to chart / desk; detection itself is complete)
    keep_events: int = 4
    keep_live_zones_per_side: int = 3
    keep_old_zones_per_side: int = 1
    keep_live_obs_per_side: int = 2
    keep_sweeps: int = 3
    keep_equal_levels_per_side: int = 2
    keep_swings: int = 12


@dataclass
class Bar:
    index: int
    time: Any
    open: float
    high: float
    low: float
    close: float


@dataclass
class Swing:
    index: int
    time: Any
    price: float
    type: str  # swing_high | swing_low
    label: str | None
    confirmed_index: int  # bar whose close confirms the swing


# ---------------------------------------------------------------------------
# input hygiene
# ---------------------------------------------------------------------------
def _get(candle: Any, key: str) -> Any:
    if isinstance(candle, dict):
        return candle.get(key)
    return getattr(candle, key, None)


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _time_key(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return value
    return value


def iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def normalize_candles(candles: list[Any]) -> list[Bar]:
    """Sorted by time, duplicates collapsed (last one wins), invalid OHLC dropped."""
    by_time: dict[Any, tuple[Any, float, float, float, float]] = {}
    for candle in candles or []:
        t = _get(candle, "time_utc")
        o, h, lo, c = (_num(_get(candle, k)) for k in ("open", "high", "low", "close"))
        if t is None or None in (o, h, lo, c):
            continue
        if min(o, h, lo, c) <= 0 or h < lo or h < max(o, c) or lo > min(o, c):
            continue
        by_time[_time_key(t)] = (t, o, h, lo, c)
    ordered = [by_time[k] for k in sorted(by_time, key=lambda k: (isinstance(k, str), k))]
    return [Bar(i, t, o, h, lo, c) for i, (t, o, h, lo, c) in enumerate(ordered)]


def rolling_atr(bars: list[Bar], period: int) -> list[float | None]:
    """Simple average true range of the `period` bars ending at each bar."""
    trs: list[float] = []
    out: list[float | None] = []
    for i, bar in enumerate(bars):
        prev_close = bars[i - 1].close if i else bar.close
        trs.append(max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close)))
        window = trs[-period:]
        out.append(sum(window) / len(window) if len(window) >= min(period, 2) else None)
    return out


def confirmed_swings(bars: list[Bar], lookback: int) -> list[Swing]:
    if len(bars) < 2 * lookback + 1:
        return []
    raw = find_swings(
        highs=[b.high for b in bars],
        lows=[b.low for b in bars],
        times=list(range(len(bars))),
        lookback=lookback,
    )
    return [
        Swing(index=s.time_utc, time=bars[s.time_utc].time, price=s.price, type=s.type,
              label=s.label, confirmed_index=s.time_utc + lookback)
        for s in raw
    ]


# ---------------------------------------------------------------------------
# detectors
# ---------------------------------------------------------------------------
def structure_events(bars: list[Bar], swings: list[Swing]) -> tuple[list[dict[str, Any]], str | None]:
    events: list[dict[str, Any]] = []
    trend: str | None = None
    pending = sorted(swings, key=lambda s: s.confirmed_index)
    k = 0
    active_high: Swing | None = None
    active_low: Swing | None = None
    for j, bar in enumerate(bars):
        # Only swings confirmed by an EARLIER closed bar can be broken by bar j.
        while k < len(pending) and pending[k].confirmed_index < j:
            s = pending[k]
            if s.type == "swing_high":
                active_high = s
            else:
                active_low = s
            k += 1
        broken = None
        if active_high is not None and bar.close > active_high.price:
            broken, direction, active_high = active_high, "bullish", None
        elif active_low is not None and bar.close < active_low.price:
            broken, direction, active_low = active_low, "bearish", None
        if broken is None:
            continue
        opposite = "bearish" if direction == "bullish" else "bullish"
        kind = "CHoCH" if trend == opposite else "BOS"
        events.append({
            "kind": kind,
            "direction": direction,
            "level": broken.price,
            "swing_index": broken.index,
            "swing_time": iso(broken.time),
            "swing_label": broken.label,
            "break_index": j,
            "break_time": iso(bar.time),
            "break_close": bar.close,
            "initial": trend is None,
            "prior_trend": trend,
        })
        trend = direction
    return events, trend


def detect_fvgs(bars: list[Bar], atr: list[float | None], cfg: SMCConfig, point: float | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(2, len(bars)):
        c1, c2, c3 = bars[i - 2], bars[i - 1], bars[i]
        if c3.low > c1.high:
            direction, lower, upper = "bullish", c1.high, c3.low
        elif c3.high < c1.low:
            direction, lower, upper = "bearish", c3.high, c1.low
        else:
            continue
        gap = upper - lower
        min_gap = max((atr[i] or 0.0) * cfg.fvg_min_gap_atr, point or 0.0)
        if gap <= 0 or gap < min_gap:
            continue
        state, end, fill = "fresh", None, 0.0
        for later in bars[i + 1:]:
            if direction == "bullish":
                if later.close < lower:
                    state, end = "invalidated", later
                    break
                if later.low <= lower:
                    state, end, fill = "filled", later, 1.0
                    break
                if later.low < upper:
                    state, fill = "partial", max(fill, (upper - later.low) / gap)
            else:
                if later.close > upper:
                    state, end = "invalidated", later
                    break
                if later.high >= upper:
                    state, end, fill = "filled", later, 1.0
                    break
                if later.high > lower:
                    state, fill = "partial", max(fill, (later.high - lower) / gap)
        out.append({
            "direction": direction,
            "low": lower,
            "high": upper,
            "start_index": c1.index,
            "start_time": iso(c1.time),
            "displacement_time": iso(c2.time),
            "formed_index": c3.index,
            "formed_time": iso(c3.time),
            "state": state,
            "fill_pct": round(fill * 100, 1) if state != "invalidated" else None,
            "end_time": iso(end.time) if end else None,
            "gap": gap,
            "min_gap": min_gap,
        })
    return out


def detect_order_blocks(bars: list[Bar], events: list[dict[str, Any]], cfg: SMCConfig) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for ev in events:
        j, bullish = ev["break_index"], ev["direction"] == "bullish"
        leg = bars[ev["swing_index"]:j + 1]
        if not leg:
            continue
        origin = min(leg, key=lambda b: b.low).index if bullish else max(leg, key=lambda b: b.high).index
        ob = None
        for idx in range(origin, max(-1, origin - cfg.ob_search_back - 1), -1):
            b = bars[idx]
            if (bullish and b.close < b.open) or (not bullish and b.close > b.open):
                ob = b
                break
        if ob is None or ob.index in seen:
            continue
        displacement = None
        for idx in range(ob.index + 1, j + 1):
            b = bars[idx]
            body = abs(b.close - b.open)
            history = bars[max(0, idx - cfg.ob_body_window):idx]
            avg = sum(abs(h.close - h.open) for h in history) / len(history) if history else 0.0
            in_dir = b.close > b.open if bullish else b.close < b.open
            if in_dir and avg > 0 and body >= cfg.ob_displacement_body_mult * avg:
                displacement = b
                break
        if displacement is None:
            continue
        seen.add(ob.index)
        state, end = "fresh", None
        for later in bars[j + 1:]:
            if bullish:
                if later.close < ob.low:
                    state, end = "invalidated", later
                    break
                if later.low <= ob.high:
                    state, end = "mitigated", later
                    break
            else:
                if later.close > ob.high:
                    state, end = "invalidated", later
                    break
                if later.high >= ob.low:
                    state, end = "mitigated", later
                    break
        out.append({
            "direction": ev["direction"],
            "low": ob.low,
            "high": ob.high,
            "definition": "full_candle_range",
            "ob_index": ob.index,
            "ob_time": iso(ob.time),
            "displacement_time": iso(displacement.time),
            "break_kind": ev["kind"],
            "break_time": ev["break_time"],
            "broken_level": ev["level"],
            "state": state,
            "end_time": iso(end.time) if end else None,
        })
    return out


def liquidity(bars: list[Bar], swings: list[Swing], atr: list[float | None], cfg: SMCConfig,
              point: float | None) -> dict[str, list[dict[str, Any]]]:
    pools: list[dict[str, Any]] = []
    sweeps: list[dict[str, Any]] = []
    for s in swings:
        high_side = s.type == "swing_high"
        taken = None
        for later in bars[s.confirmed_index + 1:]:
            if (high_side and later.high > s.price) or (not high_side and later.low < s.price):
                taken = later
                break
        pool = {
            "side": "BSL" if high_side else "SSL",
            "price": s.price,
            "swing_index": s.index,
            "swing_time": iso(s.time),
            "swing_label": s.label,
            "state": "resting" if taken is None else "taken",
            "taken_time": iso(taken.time) if taken else None,
        }
        if taken is not None:
            closed_back = taken.close < s.price if high_side else taken.close > s.price
            pool["taken_by"] = "sweep" if closed_back else "breakout"
            if closed_back:
                sweeps.append({
                    "side": pool["side"],
                    "level": s.price,
                    "swing_time": iso(s.time),
                    "swing_label": s.label,
                    "sweep_index": taken.index,
                    "sweep_time": iso(taken.time),
                    "extreme": taken.high if high_side else taken.low,
                    "close": taken.close,
                    "closed_back_inside": True,
                })
        pools.append(pool)

    # One sweep per candle and side: a candle that runs several swing levels at
    # once is ONE stop hunt. Headline level = the outermost one it swept.
    merged: dict[tuple[str, int], dict[str, Any]] = {}
    for sw in sweeps:
        key = (sw["side"], sw["sweep_index"])
        if key not in merged:
            merged[key] = {**sw, "levels": [sw["level"]], "swing_times": [sw["swing_time"]]}
            continue
        m = merged[key]
        m["levels"].append(sw["level"])
        m["swing_times"].append(sw["swing_time"])
        outer = sw["level"] > m["level"] if sw["side"] == "BSL" else sw["level"] < m["level"]
        if outer:
            m.update(level=sw["level"], swing_time=sw["swing_time"], swing_label=sw["swing_label"])
    sweeps = sorted(merged.values(), key=lambda s: s["sweep_index"])
    equal: list[dict[str, Any]] = []
    for kind, name in (("swing_high", "EQH"), ("swing_low", "EQL")):
        same = [s for s in swings if s.type == kind]
        for a, b in zip(same, same[1:]):
            tol = max((atr[b.index] or 0.0) * cfg.eq_tolerance_atr, (point or 0.0) * cfg.eq_min_points)
            if tol <= 0 or abs(a.price - b.price) > tol:
                continue
            edge = max(a.price, b.price) if kind == "swing_high" else min(a.price, b.price)
            taken = next(
                (x for x in bars[b.confirmed_index + 1:]
                 if (kind == "swing_high" and x.high > edge) or (kind == "swing_low" and x.low < edge)),
                None,
            )
            equal.append({
                "kind": name,
                "price": (a.price + b.price) / 2,
                "points": [{"time": iso(a.time), "price": a.price}, {"time": iso(b.time), "price": b.price}],
                "tolerance": tol,
                "state": "resting" if taken is None else "taken",
                "taken_time": iso(taken.time) if taken else None,
            })
    return {"pools": pools, "sweeps": sweeps, "equal_levels": equal}


def dealing_range(swings: list[Swing], price: float | None) -> dict[str, Any] | None:
    hi = next((s for s in reversed(swings) if s.type == "swing_high"), None)
    lo = next((s for s in reversed(swings) if s.type == "swing_low"), None)
    if hi is None or lo is None or hi.price <= lo.price:
        return None
    span = hi.price - lo.price
    pos = (price - lo.price) / span if price is not None else None
    if pos is None:
        state = None
    elif pos > 1 or pos < 0:
        state = "outside_range"
    else:
        state = "premium" if pos > 0.55 else "discount" if pos < 0.45 else "equilibrium"
    return {
        "high": hi.price, "high_time": iso(hi.time), "high_label": hi.label,
        "low": lo.price, "low_time": iso(lo.time), "low_label": lo.label,
        "equilibrium": (hi.price + lo.price) / 2,
        "premium_from": lo.price + 0.55 * span,
        "discount_to": lo.price + 0.45 * span,
        "position": pos,
        "state": state,
    }


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def _keep_zones(zones: list[dict[str, Any]], live_states: set[str], live_n: int, old_n: int) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for direction in ("bullish", "bearish"):
        same = [z for z in zones if z["direction"] == direction]
        kept += [z for z in same if z["state"] in live_states][-live_n:]
        kept += [z for z in same if z["state"] not in live_states][-old_n:]
    return kept


def analyze(
    candles: list[Any],
    timeframe: str,
    current_price: float | None = None,
    point: float | None = None,
    config: SMCConfig | None = None,
) -> dict[str, Any]:
    """Full SMC read of one timeframe from its CLOSED candles (JSON-safe dict)."""
    cfg = config or SMCConfig()
    bars = normalize_candles(candles)
    result: dict[str, Any] = {
        "timeframe": timeframe,
        "candles_used": len(bars),
        "last_closed_time": iso(bars[-1].time) if bars else None,
        "config": asdict(cfg),
        "point": point,
        "unsupported": list(UNSUPPORTED),
        "swings": [], "events": [], "trend": None, "fvgs": [], "order_blocks": [],
        "liquidity": {"pools": [], "sweeps": [], "equal_levels": []}, "dealing_range": None,
    }
    if len(bars) < 3:
        return result
    atr = rolling_atr(bars, cfg.atr_period)
    swings = confirmed_swings(bars, cfg.swing_lookback)
    events, trend = structure_events(bars, swings)
    fvgs = detect_fvgs(bars, atr, cfg, point)
    obs = detect_order_blocks(bars, events, cfg)
    liq = liquidity(bars, swings, atr, cfg, point)
    price = current_price if current_price is not None else bars[-1].close

    resting = [p for p in liq["pools"] if p["state"] == "resting"]
    nearest_bsl = min((p for p in resting if p["side"] == "BSL" and p["price"] > price), key=lambda p: p["price"], default=None)
    nearest_ssl = max((p for p in resting if p["side"] == "SSL" and p["price"] < price), key=lambda p: p["price"], default=None)

    result.update({
        "atr": atr[-1],
        "swings": [
            {"index": s.index, "time": iso(s.time), "price": s.price, "type": s.type,
             "label": s.label, "confirmed_time": iso(bars[s.confirmed_index].time)}
            for s in swings[-cfg.keep_swings:]
        ],
        "events": events[-cfg.keep_events:],
        "trend": trend,
        "fvgs": _keep_zones(fvgs, {"fresh", "partial"}, cfg.keep_live_zones_per_side, cfg.keep_old_zones_per_side),
        "order_blocks": _keep_zones(obs, {"fresh"}, cfg.keep_live_obs_per_side, cfg.keep_old_zones_per_side),
        "liquidity": {
            "pools": [p for p in (nearest_bsl, nearest_ssl) if p],
            "sweeps": liq["sweeps"][-cfg.keep_sweeps:],
            "equal_levels": (
                [e for e in liq["equal_levels"] if e["kind"] == "EQH"][-cfg.keep_equal_levels_per_side:]
                + [e for e in liq["equal_levels"] if e["kind"] == "EQL"][-cfg.keep_equal_levels_per_side:]
            ),
        },
        "dealing_range": dealing_range(swings, price),
        "counts": {"fvg": len(fvgs), "order_blocks": len(obs), "events": len(events),
                   "sweeps": len(liq["sweeps"]), "swings": len(swings)},
    })
    return result


def point_from_digits(digits: int | None) -> float | None:
    return 10.0 ** -digits if isinstance(digits, int) and 0 <= digits <= 10 else None
