"""Deterministic ICT/SMC detector tests (technical/smc.py) - fixed OHLC fixtures,
no network, no market data, no LLM.

Run inside the backend container:
    python test_smc_detection.py
"""

from datetime import datetime, timedelta, timezone

from app.services.ai.desk import detect_fvg_order_blocks
from app.services.chart.overlays import build_chart_overlays
from app.services.technical.smc import SMCConfig, analyze, normalize_candles, point_from_digits

T0 = datetime(2026, 11, 24, 0, 0, tzinfo=timezone.utc)


def t(i: int, minutes: int = 5) -> str:
    return (T0 + timedelta(minutes=minutes * i)).isoformat()


def bars(rows, minutes: int = 5):
    return [{"time_utc": t(i, minutes), "open": o, "high": h, "low": lo, "close": c}
            for i, (o, h, lo, c) in enumerate(rows)]


def zigzag(anchors, steps=4, d=0.2, wick=0.05, scale=1.0, minutes=5):
    """Candles walking through turning points. A peak candle's HIGH (trough
    candle's LOW) equals the anchor exactly and is the unique extreme, so
    swing prices are known in advance. Closes turn at anchor -/+ d."""
    a = [x * scale for x in anchors]
    d, wick = d * scale, wick * scale
    rows, prev = [], a[0]
    for i in range(1, len(a)):
        last = i == len(a) - 1
        peak = not last and a[i] > a[i - 1]
        target = a[i] if last else (a[i] - d if peak else a[i] + d)
        start = prev
        for k in range(1, steps + 1):
            c = start + (target - start) * k / steps
            o = prev
            h, lo = max(o, c) + wick, min(o, c) - wick
            if k == steps and not last:
                if peak:
                    h = a[i]
                else:
                    lo = a[i]
            rows.append((round(o, 6), round(h, 6), round(lo, 6), round(c, 6)))
            prev = c
    return bars(rows, minutes)


# BOS / CHoCH reference path: down (two bearish breaks), then up through the
# last lower high (CHoCH), then a higher high (BOS).
STRUCTURE = [110, 106, 108, 103, 105, 100, 109, 106, 112]

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name} {detail}")


# ---------------------------------------------------------------- swings / structure
def test_swings_labels_and_confirmation():
    r = analyze(zigzag(STRUCTURE), "M5")
    highs = [(s["price"], s["label"]) for s in r["swings"] if s["type"] == "swing_high"]
    lows = [(s["price"], s["label"]) for s in r["swings"] if s["type"] == "swing_low"]
    check("swing highs at exact peak prices with LH / HH labels", highs == [(108, None), (105, "LH"), (109, "HH")], highs)
    check("swing lows at exact trough prices with LL / HL labels", lows == [(106, None), (103, "LL"), (100, "LL"), (106, "HL")], lows)
    # the final peak (112) is the last candle: fewer than 3 closed candles to its right
    check("unconfirmed swing (no 3 closed candles on the right) is not reported", all(s["price"] != 112 for s in r["swings"]))
    s = next(x for x in r["swings"] if x["price"] == 105)
    check("swing carries its confirmation candle time (3 bars later)", s["confirmed_time"] == t(15 + 3), s)


def test_bos_and_choch_sequence():
    r = analyze(zigzag(STRUCTURE), "M5")
    seq = [(e["kind"], e["direction"], e["level"]) for e in r["events"]]
    check("bearish BOS, bearish BOS, bullish CHoCH, bullish BOS",
          seq == [("BOS", "bearish", 106), ("BOS", "bearish", 103), ("CHoCH", "bullish", 105), ("BOS", "bullish", 109)], seq)
    first = r["events"][0]
    check("first break of the series is marked initial (no prior structure)", first["initial"] and first["prior_trend"] is None)
    choch = r["events"][2]
    check("CHoCH stores broken level, swing origin, break candle and close",
          choch["swing_time"] == t(15) and choch["break_time"] == t(22) and choch["break_close"] > 105
          and choch["prior_trend"] == "bearish", choch)
    check("structure state after the series is bullish", r["trend"] == "bullish")
    # mirror: up, up, CHoCH down, BOS down
    m = analyze(zigzag([100, 104, 102, 107, 105, 110, 101, 104, 98]), "M5")
    seq = [(e["kind"], e["direction"]) for e in m["events"]]
    check("mirrored path: bullish BOS x2, bearish CHoCH, bearish BOS",
          seq == [("BOS", "bullish"), ("BOS", "bullish"), ("CHoCH", "bearish"), ("BOS", "bearish")], seq)


def test_wick_beyond_swing_is_sweep_not_bos():
    base = zigzag([100, 105, 101])  # swing high exactly 105 (bar 3)
    sweep = base + [{"time_utc": t(len(base)), "open": 101.0, "high": 105.6, "low": 100.9, "close": 104.9}]
    r = analyze(sweep, "M5")
    check("wick above swing high, close back below -> no BOS", not any(e["direction"] == "bullish" for e in r["events"]), r["events"])
    sw = r["liquidity"]["sweeps"]
    check("-> BSL sweep with swept level, sweep candle, extreme and close",
          sw and sw[-1]["side"] == "BSL" and sw[-1]["level"] == 105 and sw[-1]["sweep_time"] == t(len(base))
          and sw[-1]["extreme"] == 105.6 and sw[-1]["close"] == 104.9, sw)

    brk = base + [{"time_utc": t(len(base)), "open": 101.0, "high": 106.0, "low": 100.9, "close": 105.8}]
    r = analyze(brk, "M5")
    check("close above swing high -> BOS, not a sweep",
          [e["kind"] for e in r["events"]][-1:] == ["BOS"] and not r["liquidity"]["sweeps"], (r["events"], r["liquidity"]["sweeps"]))


def test_swing_confirmed_on_same_bar_cannot_be_broken_by_that_bar():
    # A swing is only usable after its confirmation candle has CLOSED.
    rows = zigzag([100, 105, 104.5], steps=4)  # 3 closed candles after the peak would be needed
    r = analyze(rows[:7], "M5")  # peak at bar 3, only bars 4..6 after it
    check("swing confirmed exactly at the last bar yields no break on that bar", r["events"] == [], r["events"])


# ---------------------------------------------------------------- FVG
BULL = [
    (100.0, 101.0, 99.5, 100.8),   # c1 high 101.0
    (100.8, 103.0, 100.7, 102.9),  # displacement
    (102.9, 103.5, 102.0, 103.3),  # c3 low 102.0 -> gap 101.0..102.0
]
BEAR = [
    (103.0, 103.5, 102.0, 102.2),  # c1 low 102.0
    (102.2, 102.3, 100.0, 100.1),  # displacement
    (100.1, 101.0, 99.6, 99.8),    # c3 high 101.0 -> gap 101.0..102.0
]


def _fvg(rows, direction):
    return [z for z in analyze(bars(rows), "M5")["fvgs"] if z["direction"] == direction]


def test_fvg_bullish_and_bearish_geometry():
    z = _fvg(BULL + [(103.3, 104.0, 103.1, 103.8)], "bullish")
    check("bullish FVG = high(c1)..low(c3), starts at c1, confirmed at c3",
          len(z) == 1 and (z[0]["low"], z[0]["high"]) == (101.0, 102.0)
          and z[0]["start_time"] == t(0) and z[0]["formed_time"] == t(2) and z[0]["state"] == "fresh", z)
    z = _fvg(BEAR + [(99.8, 100.0, 99.0, 99.2)], "bearish")
    check("bearish FVG = high(c3)..low(c1)", len(z) == 1 and (z[0]["low"], z[0]["high"]) == (101.0, 102.0) and z[0]["state"] == "fresh", z)


def test_fvg_partial_fill_full_mitigation_and_invalidation():
    z = _fvg(BULL + [(103.3, 103.4, 101.6, 102.5)], "bullish")[0]
    check("price enters bullish gap to 101.6 -> partial, 40% filled", z["state"] == "partial" and z["fill_pct"] == 40.0 and z["end_time"] is None, z)
    z = _fvg(BULL + [(103.3, 103.4, 101.6, 102.5), (102.5, 102.6, 100.9, 101.4)], "bullish")[0]
    check("low reaches the far edge -> filled (mitigated), ends at that candle", z["state"] == "filled" and z["end_time"] == t(4), z)
    z = _fvg(BULL + [(103.3, 103.4, 100.2, 100.5)], "bullish")[0]
    check("close below the far edge -> invalidated", z["state"] == "invalidated" and z["end_time"] == t(3), z)
    z = _fvg(BEAR + [(99.8, 101.5, 99.7, 100.6)], "bearish")[0]
    check("bearish gap partially filled to 101.5 -> 50%", z["state"] == "partial" and z["fill_pct"] == 50.0, z)
    z = _fvg(BEAR + [(99.8, 102.4, 99.7, 102.3)], "bearish")[0]
    check("bearish gap: close above far edge -> invalidated", z["state"] == "invalidated", z)
    o = build_chart_overlays({"symbol": "TESTm", "multi_timeframe": {"M5": {"candles": bars(BULL + [(103.3, 103.4, 101.6, 102.5), (102.5, 102.6, 100.9, 101.4)])}},
                              "key_levels": {"current_price": 101.4}})["overlays"]
    f = next(x for x in o if x["layer"] == "fvg")
    check("overlay: filled FVG -> status mitigated with time_end at the mitigating candle",
          f["status"] == "mitigated" and f["time_end"] == t(4) and f["meta"]["state"] == "filled", f)


def test_fvg_minimum_gap_and_incomplete_data():
    tiny = [(100.0, 101.0, 99.5, 100.8), (100.8, 101.3, 100.7, 101.2), (101.2, 101.6, 101.01, 101.5)]  # gap 0.01
    check("gap below 0.1 x ATR is not an FVG", _fvg(tiny, "bullish") == [])
    check("two candles cannot form an FVG", analyze(bars(BULL[:2]), "M5")["fvgs"] == [])
    pt = point_from_digits(2)
    sub_point = [(100.0, 101.0, 99.5, 100.8), (100.8, 101.3, 100.7, 101.2), (101.2, 101.6, 101.005, 101.5)]  # gap 0.005
    r = analyze(bars(sub_point), "M5", point=pt, config=SMCConfig(fvg_min_gap_atr=0.0))
    check("gap smaller than one point (0.01) is not an FVG even without the ATR filter", r["fvgs"] == [], r["fvgs"])
    r = analyze(bars(tiny), "M5", point=pt, config=SMCConfig(fvg_min_gap_atr=0.0))
    check("a gap of exactly one point is kept when the ATR filter is off", len(r["fvgs"]) == 1, r["fvgs"])


# ---------------------------------------------------------------- order blocks
def test_order_blocks_require_a_structure_break():
    r = analyze(zigzag(STRUCTURE), "M5")
    obs = {(z["direction"], z["break_kind"]): z for z in r["order_blocks"]}
    bull = obs.get(("bullish", "CHoCH"))
    check("bullish OB = last bearish candle at the leg origin before the CHoCH (full range)",
          bull is not None and bull["ob_time"] == t(19) and bull["low"] == 100 and bull["definition"] == "full_candle_range", r["order_blocks"])
    bear = obs.get(("bearish", "BOS"))
    check("bearish OB = last bullish candle at the leg origin before the BOS",
          bear is not None and bear["high"] in (108, 105) and bear["direction"] == "bearish", r["order_blocks"])
    check("OBs carry break time / broken level / displacement candle",
          all(z["break_time"] and z["broken_level"] and z["displacement_time"] for z in r["order_blocks"]))

    # opposing candle followed by a big candle, but NO swing is broken -> no OB
    plain = bars([(100.0, 100.4, 99.6, 100.1), (100.1, 100.5, 99.9, 100.2), (100.2, 100.6, 100.0, 100.4),
                  (100.4, 100.4, 97.5, 97.6), (97.6, 99.0, 97.0, 97.2), (97.2, 97.8, 96.8, 97.0)])
    check("an opposing candle + displacement without BOS/CHoCH is not an order block", analyze(plain, "M5")["order_blocks"] == [])


def test_order_block_mitigation_and_invalidation():
    rows = zigzag(STRUCTURE)
    r = analyze(rows, "M5")
    bull = next(z for z in r["order_blocks"] if z["direction"] == "bullish" and z["break_kind"] == "CHoCH")
    check("bullish OB untouched after the break -> fresh", bull["state"] == "fresh", bull)
    back = rows + [{"time_utc": t(len(rows)), "open": 111.0, "high": 111.2, "low": 101.0, "close": 101.5}]
    bull = next(z for z in analyze(back, "M5")["order_blocks"] if z["ob_time"] == t(19))
    check("price trades back into the OB -> mitigated", bull["state"] == "mitigated" and bull["end_time"] == t(len(rows)), bull)
    through = rows + [{"time_utc": t(len(rows)), "open": 111.0, "high": 111.2, "low": 98.0, "close": 98.5}]
    bull = next(z for z in analyze(through, "M5")["order_blocks"] if z["ob_time"] == t(19))
    check("close below the OB -> invalidated", bull["state"] == "invalidated", bull)


# ---------------------------------------------------------------- liquidity
def test_equal_highs_lows_use_instrument_volatility():
    eq = [100, 101.0, 99.0, 101.03, 98.0, 100.0]
    for scale, name in ((1.0, "base"), (35.0, "XAU-like (x35)"), (0.0109, "EURUSD-like")):
        r = analyze(zigzag(eq, scale=scale), "M5")
        kinds = [e["kind"] for e in r["liquidity"]["equal_levels"]]
        check(f"{name}: highs 0.03% apart are EQH; lows 1% apart are not EQL", kinds == ["EQH"], (kinds, r["liquidity"]["equal_levels"]))
    r = analyze(zigzag([100, 101.0, 99.0, 101.5, 98.0, 100.0], scale=35.0), "M5")
    check("XAU-like: highs 17.5 apart (0.5 x ATR) are not equal", r["liquidity"]["equal_levels"] == [], r["liquidity"]["equal_levels"])
    eqh = analyze(zigzag(eq, scale=35.0), "M5")["liquidity"]["equal_levels"][0]
    check("EQH keeps both source swings, level = their mean",
          [p["price"] for p in eqh["points"]] == [3535.0, 3536.05] and abs(eqh["price"] - 3535.525) < 1e-9, eqh)


def test_pools_and_sweep_states():
    rows = zigzag([100, 101.0, 99.0, 101.03, 98.0, 100.0])
    rows += [{"time_utc": t(len(rows)), "open": 100.0, "high": 101.4, "low": 99.9, "close": 100.8}]
    r = analyze(rows, "M5", current_price=100.8)
    sw = r["liquidity"]["sweeps"][-1]
    check("latest candle sweeps the 101.03 high and closes back inside", sw["side"] == "BSL" and sw["level"] == 101.03 and sw["closed_back_inside"], sw)
    pools = {p["side"]: p for p in r["liquidity"]["pools"]}
    check("swept highs are no longer resting BSL", "BSL" not in pools, pools)
    check("nearest resting SSL below price is the 98.0 low", pools["SSL"]["price"] == 98.0 and pools["SSL"]["state"] == "resting", pools)


def test_one_candle_sweeping_two_levels_is_one_sweep():
    rows = zigzag([100, 101.0, 99.0, 100.6, 98.5, 99.5])  # resting highs 101.0 and 100.6 (LH)
    rows += [{"time_utc": t(len(rows)), "open": 99.5, "high": 101.3, "low": 99.4, "close": 100.0}]
    sw = [s for s in analyze(rows, "M5")["liquidity"]["sweeps"] if s["sweep_time"] == t(len(rows) - 1)]
    check("one candle running two highs = ONE sweep, headline = outermost level, all levels kept",
          len(sw) == 1 and sw[0]["level"] == 101.0 and sorted(sw[0]["levels"]) == [100.6, 101.0], sw)
    ids = [o["id"] for o in build_chart_overlays(_ctx({"M5": rows}, price=100.0))["overlays"]]
    check("-> no duplicate sweep ids in the overlay payload", len(ids) == len(set(ids)))


# ---------------------------------------------------------------- premium / discount
def test_dealing_range_premium_discount_equilibrium():
    rows = zigzag([100, 98.0, 102.0, 101.5])
    for price, state in ((101.5, "premium"), (98.5, "discount"), (100.1, "equilibrium"), (103.0, "outside_range")):
        dr = analyze(rows, "H1", current_price=price)["dealing_range"]
        check(f"price {price} -> {state}", dr["state"] == state, dr)
    dr = analyze(rows, "H1", current_price=101.5)["dealing_range"]
    check("range = last swing high/low with source times, EQ 50%",
          (dr["high"], dr["low"], dr["equilibrium"]) == (102.0, 98.0, 100.0)
          and dr["high_time"] == t(7) and dr["low_time"] == t(3), dr)
    check("premium from 55%, discount up to 45%", (dr["premium_from"], dr["discount_to"]) == (100.2, 99.8), dr)


# ---------------------------------------------------------------- data hygiene / precision
def test_empty_short_duplicate_and_invalid_candles():
    for name, data in (("empty", []), ("one candle", bars(BULL[:1])), ("None", None)):
        r = analyze(data, "M5")
        check(f"{name}: no crash, nothing detected",
              r["swings"] == [] and r["events"] == [] and r["fvgs"] == [] and r["order_blocks"] == [] and r["dealing_range"] is None)
    dup = bars(BULL)
    dup.insert(1, dict(dup[1]))  # same timestamp twice
    check("duplicate timestamps collapse to one candle", len(normalize_candles(dup)) == 3)
    bad = bars(BULL) + [{"time_utc": t(9), "open": 1, "high": 0.5, "low": 2, "close": 1}, {"time_utc": t(10), "open": None, "high": 1, "low": 1, "close": 1}]
    check("invalid OHLC rows are dropped", len(normalize_candles(bad)) == 3)
    shuffled = list(reversed(bars(BULL)))
    check("unsorted input is ordered by time", [b.time for b in normalize_candles(shuffled)] == [t(0), t(1), t(2)])


def test_precision_xau_3_digits_and_fx_5_digits():
    xau = [(3570.111, 3575.123, 3569.871, 3574.902), (3574.902, 3580.555, 3574.600, 3580.300), (3580.300, 3582.010, 3576.457, 3581.111)]
    z = analyze(bars(xau), "M5", point=point_from_digits(3))["fvgs"][0]
    check("XAUUSDm (3 digits): FVG edges are the exact candle prices", (z["low"], z["high"]) == (3575.123, 3576.457), z)
    fx = [(1.09020, 1.09031, 1.09015, 1.09028), (1.09028, 1.09120, 1.09025, 1.09115), (1.09115, 1.09130, 1.09055, 1.09125)]
    z = analyze(bars(fx), "M5", point=point_from_digits(5))["fvgs"][0]
    check("EURUSDm (5 digits): 2.4-pip gap kept exact (not rounded away)", (z["low"], z["high"]) == (1.09031, 1.09055), z)
    ev = detect_fvg_order_blocks(bars(fx), current_price=1.0912, atr=0.0005)["fvg"][0]
    check("desk brief quotes the same 5-digit edges", (ev["low"], ev["high"]) == (1.09031, 1.09055), ev)


# ---------------------------------------------------------------- overlays: coordinates, refresh, MTF, single source
def _ctx(tf_candles, price, smc=None):
    c = {"symbol": "TESTm", "generated_at_utc": t(40), "multi_timeframe": {tf: {"candles": rows} for tf, rows in tf_candles.items()},
         "key_levels": {"current_price": price}, "trade_plan": {"status": "waiting"}}
    if smc is not None:
        c["smc"] = smc
    return c


def test_overlay_coordinates_and_timestamps():
    p = build_chart_overlays(_ctx({"M5": zigzag(STRUCTURE)}, price=112.0))["overlays"]
    choch = next(o for o in p if ":break:choch:" in o["id"])
    check("CHoCH line from the broken swing (time_start) to the break candle (time_end) at the level",
          choch["price"] == 105 and choch["time_start"] == t(15) and choch["time_end"] == t(22)
          and choch["name"] == "CHoCH ↑" and choch["status"] == "confirmed", choch)
    hh = next(o for o in p if o["layer"] == "structure" and o["kind"] == "marker" and o["name"] == "HH")
    check("HH marker sits on the swing candle at the swing price", hh["price"] == 109 and hh["time_start"] == t(23) and hh["position"] == "above", hh)
    ob = next(o for o in p if o["layer"] == "order_blocks" and o["color"] == "bullish")
    check("bullish OB zone starts at the OB candle with exact range", ob["time_start"] == t(19) and ob["price_low"] == 100, ob)


def test_no_duplicates_and_stable_ids_on_refresh():
    rows = zigzag(STRUCTURE)
    a = build_chart_overlays(_ctx({"M5": rows}, price=112.0))["overlays"]
    b = build_chart_overlays(_ctx({"M5": rows}, price=112.0))["overlays"]
    ids = [o["id"] for o in a]
    check("no duplicate ids in one payload", len(ids) == len(set(ids)))
    check("same data -> same ids (refresh does not create new objects)", ids == [o["id"] for o in b])
    grown = rows + [{"time_utc": t(len(rows)), "open": 112.0, "high": 112.3, "low": 111.6, "close": 112.1}]
    c = {o["id"] for o in build_chart_overlays(_ctx({"M5": grown}, price=112.1))["overlays"]}
    kept = {i for i in ids if ":swing:" in i or ":break:" in i}
    check("a new closed candle keeps existing structure ids", kept <= c, kept - c)


def test_mtf_source_tagging():
    p = build_chart_overlays(_ctx({"M5": zigzag(STRUCTURE), "H1": zigzag(STRUCTURE, minutes=60)}, price=112.0))["overlays"]
    for tf in ("M5", "H1"):
        mine = [o for o in p if o["timeframe"] == tf and o["layer"] in ("structure", "fvg", "order_blocks", "liquidity")]
        check(f"{tf}: objects tagged with their source timeframe and id", mine and all(o["id"].startswith(f"TESTm:{tf}:") for o in mine))
    h1_choch = next(o for o in p if o["timeframe"] == "H1" and ":break:choch:" in o["id"])
    check("H1 objects use H1 candle times", h1_choch["time_end"] == t(22, 60), h1_choch)


def test_overlays_use_the_engine_read_verbatim():
    rows = zigzag(STRUCTURE)
    engine = {"M5": analyze(rows, "M5", current_price=112.0)}
    engine["M5"]["fvgs"] = [{**engine["M5"]["fvgs"][0], "low": 104.0, "high": 104.5}] if engine["M5"]["fvgs"] else []
    p = build_chart_overlays(_ctx({"M5": rows}, price=112.0, smc=engine))["overlays"]
    fvg = [o for o in p if o["layer"] == "fvg"]
    check("chart draws the pipeline's SMC read (no second detection)",
          not engine["M5"]["fvgs"] or [(o["price_low"], o["price_high"]) for o in fvg] == [(104.0, 104.5)], fvg)
    ev = detect_fvg_order_blocks(rows, current_price=112.0, atr=1.0, smc=engine["M5"])
    check("desk brief reads the same engine read", [(z["low"], z["high"]) for z in ev["fvg"]] == [(z["low"], z["high"]) for z in engine["M5"]["fvgs"]])
    check("unsupported concepts are declared, never emitted",
          {"IFVG", "BPR", "trend_channel"} <= set(engine["M5"]["unsupported"])
          and not any(k in o["name"] for o in p for k in ("IFVG", "BPR", "channel")))


def main():
    tests = [fn for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    for fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            check(fn.__name__, False, repr(exc))
    print(f"\n{passed}/{passed + failed} passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
