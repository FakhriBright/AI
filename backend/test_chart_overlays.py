"""Unit tests for chart overlays and chat-to-chart commands (no network, no LLM).

Run inside the backend container:
    python test_chart_overlays.py
"""

from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from app.schemas.chart import ChartOverlay
from app.services.chart.chat_commands import build_chat_chart_command, detect_intents
from app.services.chart.overlays import build_chart_overlays

T0 = datetime(2026, 11, 24, 0, 0, tzinfo=timezone.utc)


def t(i: int) -> str:
    return (T0 + timedelta(minutes=5 * i)).isoformat()


def candles(rows):
    return [{"time_utc": t(i), "open": o, "high": h, "low": lo, "close": c, "tick_volume": 1}
            for i, (o, h, lo, c) in enumerate(rows)]


def swing(i, kind, price, label=None):
    return {"time_utc": t(i), "type": kind, "label": label, "price": price}


def ctx(tf_data=None, price=100.0, key_levels=None, trade_plan=None, scenarios=None, bias="bearish"):
    return {
        "symbol": "TESTm",
        "generated_at_utc": t(30),
        "market_bias": {"overall": bias},
        "multi_timeframe": tf_data or {},
        "key_levels": {"current_price": price, **(key_levels or {})},
        "scenarios": scenarios or {},
        "trade_plan": trade_plan or {"status": "waiting"},
    }


def by(payload, layer=None, tf=None):
    return [o for o in payload["overlays"]
            if (layer is None or o["layer"] == layer) and (tf is None or o["timeframe"] == tf)]


BULL_FVG = [
    (100.0, 100.5, 99.5, 100.2),
    (100.2, 100.8, 100.0, 100.6),
    (100.6, 101.0, 100.4, 100.9),   # candle 1 (high 101.0)
    (100.9, 103.0, 100.9, 102.8),   # displacement
    (102.8, 103.5, 102.2, 103.3),   # candle 3 (low 102.2) -> gap 101.0..102.2
    (103.3, 103.8, 102.6, 103.5),
]


def test_bullish_fvg_fresh_with_exact_candle_times():
    p = build_chart_overlays(ctx({"M5": {"candles": candles(BULL_FVG), "atr14": 1.0, "swings": []}}, price=103.5))
    fvg = by(p, "fvg", "M5")
    assert len(fvg) == 1, fvg
    z = fvg[0]
    assert z["name"] == "Bullish FVG" and z["color"] == "bullish" and z["status"] == "active"
    assert (z["price_low"], z["price_high"]) == (101.0, 102.2)
    assert z["time_start"] == t(2) and z["id"] == f"TESTm:M5:fvg:bullish:{t(4)}"
    assert z["source"] == "ai.desk.detect_fvg_order_blocks"


def test_fx_precision_is_kept_exact():
    # 5-digit FX: desk rounds to 3 decimals (1.091/1.091); the chart must keep the real gap.
    rows = [
        (1.09000, 1.09020, 1.08990, 1.09010),
        (1.09010, 1.09030, 1.09000, 1.09020),
        (1.09020, 1.09055, 1.09015, 1.09050),   # candle 1 high 1.09055
        (1.09050, 1.09120, 1.09050, 1.09115),
        (1.09115, 1.09130, 1.09098, 1.09125),   # candle 3 low 1.09098 -> gap 1.09055..1.09098
        (1.09125, 1.09140, 1.09110, 1.09130),
    ]
    p = build_chart_overlays(ctx({"M5": {"candles": candles(rows), "atr14": 0.0003, "swings": []}}, price=1.0913))
    fvg = by(p, "fvg", "M5")
    assert [(z["price_low"], z["price_high"]) for z in fvg] == [(1.09055, 1.09098)], fvg

    sw = [swing(1, "swing_low", 1.09012), swing(3, "swing_high", 1.09188)]
    pd = {o["name"]: o for o in by(build_chart_overlays(ctx({"M5": {"candles": [], "swings": sw}}, price=1.0915)), "premium_discount")}
    assert pd["Equilibrium"]["price"] == (1.09012 + 1.09188) / 2 and pd["Discount"]["price_low"] == 1.09012


def test_fvg_mitigated_when_later_candle_trades_into_it():
    rows = BULL_FVG + [(103.5, 103.6, 101.5, 102.0)]
    p = build_chart_overlays(ctx({"M5": {"candles": candles(rows), "atr14": 1.0, "swings": []}}, price=102.0))
    assert by(p, "fvg")[0]["status"] == "mitigated"


def test_bearish_fvg_and_bearish_order_block():
    rows = [
        (100.0, 100.4, 99.6, 100.1),
        (100.1, 100.5, 99.9, 100.2),
        (100.2, 100.6, 100.0, 100.4),   # bullish base candle, low 100.0
        (100.4, 100.4, 97.5, 97.6),     # bearish displacement
        (97.6, 99.0, 97.0, 97.2),       # high 99.0 < 100.0 -> bearish FVG 99.0..100.0
        (97.2, 97.8, 96.8, 97.0),
    ]
    p = build_chart_overlays(ctx({"M15": {"candles": candles(rows), "atr14": 1.0, "swings": []}}, price=97.0))
    fvg = by(p, "fvg", "M15")
    assert [(z["name"], z["price_low"], z["price_high"]) for z in fvg] == [("Bearish FVG", 99.0, 100.0)], fvg
    ob = by(p, "order_blocks", "M15")
    assert ob and ob[0]["name"] == "Bearish Order Block" and (ob[0]["price_low"], ob[0]["price_high"]) == (100.0, 100.6)
    assert ob[0]["time_start"] == t(2)


def test_swings_and_bos_vs_choch():
    sw = [swing(1, "swing_low", 99.0, "HL"), swing(3, "swing_high", 101.0, "HH")]
    rows = [(100, 100.5, 99.5, 100.2)] * 5 + [(100.5, 101.8, 100.4, 101.5)]
    bos = build_chart_overlays(ctx({"M5": {"candles": candles(rows), "swings": sw, "trend": "bullish"}}, price=101.5))
    markers = [o for o in by(bos, "structure") if o["kind"] == "marker"]
    assert {(m["name"], m["color"]) for m in markers} == {("HL", "bullish"), ("HH", "bullish")}
    brk = [o for o in by(bos, "structure") if o["kind"] == "hline"]
    assert len(brk) == 1 and brk[0]["name"] == "BOS ↑" and brk[0]["status"] == "confirmed" and brk[0]["price"] == 101.0
    assert brk[0]["time_start"] == t(3) and brk[0]["time_end"] == t(5)

    choch = build_chart_overlays(ctx({"M5": {"candles": candles(rows), "swings": sw, "trend": "bearish"}}, price=101.5))
    brk = [o for o in by(choch, "structure") if o["kind"] == "hline"]
    assert brk[0]["name"].startswith("CHoCH / MSS (candidate)") and brk[0]["status"] == "candidate"


def test_no_break_inside_range():
    sw = [swing(1, "swing_low", 99.0, "HL"), swing(3, "swing_high", 101.0, "HH")]
    rows = [(100, 100.5, 99.5, 100.2)] * 6
    p = build_chart_overlays(ctx({"M5": {"candles": candles(rows), "swings": sw, "trend": "bullish"}}))
    assert not [o for o in by(p, "structure") if o["kind"] == "hline"]


def test_liquidity_bsl_ssl_sweep_and_eqh():
    sw = [swing(1, "swing_high", 101.0, None), swing(2, "swing_low", 99.0, None),
          swing(3, "swing_high", 101.1, "HH"), swing(4, "swing_low", 98.0, "LL")]
    rows = [(100, 100.5, 99.5, 100.2)] * 5 + [(100.5, 101.4, 100.3, 100.8)]  # wick above 101.1, close back below
    p = build_chart_overlays(ctx({"M5": {"candles": candles(rows), "swings": sw, "trend": "mixed"}}, price=100.8))
    liq = {o["name"]: o for o in by(p, "liquidity")}
    assert liq["Buy-side Liquidity (BSL)"]["price"] == 101.1 and liq["Buy-side Liquidity (BSL)"]["status"] == "active"
    assert liq["Sell-side Liquidity (SSL)"]["price"] == 98.0
    assert liq["BSL sweep"]["price"] == 101.4 and liq["BSL sweep"]["shape"] == "circle"
    eqh = liq["EQH (buy-side liquidity)"]
    assert eqh["kind"] == "trendline" and abs(eqh["price"] - 101.05) < 1e-9
    assert "EQL (sell-side liquidity)" not in liq  # 99.0 vs 98.0 is beyond the 0.20 tolerance


def test_trendline_active_and_broken():
    sw = [swing(1, "swing_low", 99.0), swing(2, "swing_high", 101.0), swing(3, "swing_low", 99.5)]
    # line rises 0.5 per 2 bars -> projected 100.5 at bar 7
    up = [(100, 100.5, 99.5, 100.2)] * 7 + [(100.6, 101.0, 100.6, 100.9)]
    p = build_chart_overlays(ctx({"M5": {"candles": candles(up), "swings": sw}}))
    tl = by(p, "trendline")
    assert len(tl) == 1 and tl[0]["name"] == "Bullish trendline" and tl[0]["status"] == "active"
    assert [pt["price"] for pt in tl[0]["points"]] == [99.0, 99.5]

    down = up[:-1] + [(100.6, 100.6, 99.9, 100.0)]
    p = build_chart_overlays(ctx({"M5": {"candles": candles(down), "swings": sw}}))
    assert by(p, "trendline")[0]["status"] == "broken"


def test_premium_discount_and_outside_range():
    sw = [swing(1, "swing_low", 98.0), swing(3, "swing_high", 102.0)]
    p = build_chart_overlays(ctx({"H1": {"candles": [], "swings": sw}}, price=101.5))
    pd = {o["name"]: o for o in by(p, "premium_discount", "H1")}
    assert (pd["Premium"]["price_low"], pd["Premium"]["price_high"]) == (100.2, 102.0)
    assert (pd["Discount"]["price_low"], pd["Discount"]["price_high"]) == (98.0, 99.8)
    assert pd["Equilibrium"]["price"] == 100.0 and pd["Premium"]["meta"]["state"] == "premium"
    assert pd["Premium"]["time_start"] == t(1)

    outside = build_chart_overlays(ctx({"H1": {"candles": [], "swings": sw}}, price=103.0))
    assert not by(outside, "premium_discount")


def test_support_resistance_from_key_levels():
    levels = {
        "supports": [{"price": 99.0, "low": 98.9, "high": 99.1, "timeframes": ["M5", "H1"], "touches": 3}],
        "resistances": [{"price": 101.0, "low": 101.0, "high": 101.0, "timeframes": ["M15"], "touches": 1}],
    }
    p = build_chart_overlays(ctx(key_levels=levels))
    sr = {o["name"]: o for o in by(p, "sr")}
    sup = sr["Support (3x M5,H1)"]
    assert sup["kind"] == "zone" and sup["timeframe"] == "H1" and (sup["price_low"], sup["price_high"]) == (98.9, 99.1)
    res = sr["Resistance (1x M15)"]
    assert res["kind"] == "hline" and res["timeframe"] == "M15" and res["price"] == 101.0


SCENARIOS = {"intraday_scenarios": [{
    "name": "bearish_continuation", "trigger_reference": 99.5, "invalidation_reference": 101.5,
    "trigger_confirmed": False, "trigger_distance_atr": 0.5, "breakout_status": "awaiting",
}]}


def test_trade_plan_waiting_never_draws_a_position():
    plan = {"status": "waiting", "scenario_name": "bearish_continuation", "direction": "sell",
            "entry_price": None, "stop_price": None}
    p = build_chart_overlays(ctx(trade_plan=plan, scenarios=SCENARIOS))
    tp = by(p, "trade_plan")
    assert [o["kind"] for o in tp] == ["label"], tp
    assert tp[0]["status"] == "waiting" and tp[0]["price"] == 99.5 and tp[0]["meta"]["blockers"]


def test_trade_plan_ready_draws_position():
    plan = {"status": "ready_for_manual_review", "scenario_name": "bearish_continuation", "direction": "sell",
            "entry_price": 100.0, "stop_price": 101.0, "target_price": 98.0, "rr_ratio": 2.0}
    p = build_chart_overlays(ctx(trade_plan=plan, scenarios=SCENARIOS))
    tp = by(p, "trade_plan")
    assert len(tp) == 1 and tp[0]["kind"] == "position"
    assert (tp[0]["entry"], tp[0]["stop"], tp[0]["target"], tp[0]["rr"]) == (100.0, 101.0, 98.0, 2.0)


def test_schema_rejects_bad_geometry():
    base = dict(id="x", symbol="S", timeframe="M5", layer="fvg", name="n", color="bullish", source="s")
    for bad in (
        dict(kind="zone", price_low=2.0, price_high=1.0),
        dict(kind="hline"),
        dict(kind="hline", price=float("nan")),
        dict(kind="trendline", points=[{"price": 1.0}]),
        dict(kind="position", entry=1.0),
        dict(kind="hline", price=1.0, timeframe="M7"),
    ):
        try:
            ChartOverlay(**{**base, **bad})
            raise AssertionError(f"accepted {bad}")
        except ValidationError:
            pass


def test_overlay_ids_are_stable_across_rebuilds():
    data = {"M5": {"candles": candles(BULL_FVG), "atr14": 1.0, "swings": []}}
    a = [o["id"] for o in build_chart_overlays(ctx(data, price=103.5))["overlays"]]
    b = [o["id"] for o in build_chart_overlays(ctx(data, price=103.5))["overlays"]]
    assert a == b and len(a) == len(set(a))


# --------------------------------------------------------------------------
# chat-to-chart
# --------------------------------------------------------------------------

def _chat_context():
    levels = {"resistances": [{"price": 101.0, "low": 100.9, "high": 101.1, "timeframes": ["M15"], "touches": 2}],
              "supports": [{"price": 99.0, "low": 98.9, "high": 99.1, "timeframes": ["M15"], "touches": 2}]}
    sw = [swing(1, "swing_high", 101.2, "LH"), swing(2, "swing_low", 98.5, "LL")]
    rows = [(100, 100.5, 99.5, 100.2)] * 6
    plan = {"status": "waiting", "scenario_name": "bearish_continuation", "direction": "sell"}
    return ctx({"M15": {"candles": candles(rows), "swings": sw, "trend": "bearish"}},
               price=100.0, key_levels=levels, trade_plan=plan, scenarios=SCENARIOS)


def _ops(cmd):
    return {op["op"]: op for op in cmd["operations"]}


def test_intents():
    from app.services.chart.chat_commands import _TF_TOKEN
    assert _TF_TOKEN.findall("H1 06:00, M15 FVG, M1, HTF (H4 & D1), M150") == ["H1", "M15", "M1", "H4", "D1"]
    assert detect_intents("Tunjukkan liquidity yang sedang diincar market.") == ["liquidity"]
    assert "invalidation" in detect_intents("Apa invalidasi setup ini?")
    assert {"pullback", "setup"} <= set(detect_intents("Tunggu pullback dulu atau langsung sell?"))
    assert detect_intents("hapus gambar di chart")[0] == "clear"


def test_liquidity_question_highlights_liquidity_only_from_engine():
    c = _chat_context(); p = build_chart_overlays(c)
    cmd = build_chat_chart_command("Tunjukkan liquidity yang sedang diincar market.", "Penjelasan.", p, c)
    ids = _ops(cmd)["highlight"]["ids"]
    known = {o["id"]: o for o in p["overlays"]}
    assert ids and all(known[i]["layer"] == "liquidity" for i in ids)
    assert "create" not in _ops(cmd)


def test_invalidation_creates_line_at_engine_price():
    c = _chat_context(); p = build_chart_overlays(c)
    cmd = build_chat_chart_command("Apa invalidasi setup ini?", "Invalidasi di 101.5.", p, c)
    created = _ops(cmd)["create"]["overlays"]
    assert len(created) == 1 and created[0]["kind"] == "hline" and created[0]["price"] == 101.5
    assert created[0]["name"].startswith("INVALIDATION") and created[0]["id"] == "TESTm:MTF:chat:invalidation:bearish_continuation"


def test_invalidation_when_plan_scenario_has_none_uses_engine_scenarios_and_says_so():
    c = _chat_context()
    c["trade_plan"]["scenario_name"] = "scalp_x"
    c["scenarios"] = {
        "intraday_scenarios": [
            {"name": "bearish_continuation", "invalidation_reference": 101.5, "trigger_reference": 99.5},
            {"name": "bullish_reversal", "invalidation_reference": 98.2, "trigger_reference": 99.5},
        ],
        "scalp_scenarios": [{"name": "scalp_x", "invalidation_reference": None, "trigger_reference": 99.8}],
    }
    p = build_chart_overlays(c)
    cmd = build_chat_chart_command("Apa invalidasi setup ini?", "Invalidasi bullish di 98.20.", p, c)
    lines = _ops(cmd)["create"]["overlays"]
    assert [(o["price"], o["meta"]["scenario"]) for o in lines] == [(98.2, "bullish_reversal"), (101.5, "bearish_continuation")]
    assert cmd["notes"] == ["Engine tidak memberi level invalidasi untuk scalp_x."]


def test_bearish_question_does_not_highlight_quoted_bullish_objects():
    c = _chat_context(); p = build_chart_overlays(c)
    cmd = build_chat_chart_command("Kenapa sekarang bearish?", "Support 99.00 masih ada, tapi struktur LL 98.50.", p, c)
    names = {o["id"]: (o["name"], o["color"]) for o in p["overlays"]}
    ids = _ops(cmd)["highlight"]["ids"]
    assert ids and all(names[i][1] != "bullish" for i in ids), [names[i] for i in ids]
    assert names[ids[0]][0] == "LL"  # the quoted bearish swing leads


def test_pullback_sell_draws_arrow_to_nearest_supply_and_no_position():
    c = _chat_context(); p = build_chart_overlays(c)
    cmd = build_chat_chart_command("Tunggu pullback dulu atau langsung sell?", "Tunggu.", p, c)
    created = _ops(cmd)["create"]["overlays"]
    arrow = next(o for o in created if o["kind"] == "arrow")
    assert arrow["name"] == "WAIT FOR CONFIRMATION" and arrow["status"] == "waiting"
    assert [pt["price"] for pt in arrow["points"]] == [100.0, 100.9]  # current price -> resistance zone low
    assert not any(o["kind"] == "position" for o in created)
    assert cmd["entry_allowed"] is False and cmd["blockers"]
    ids = _ops(cmd)["highlight"]["ids"]
    assert ids[0] == arrow["meta"]["zone_id"] and "TESTm:MTF:plan:waiting" in ids
    assert "TESTm:M15:sr:supports:99.0" not in ids  # sell question: support is not the focus


def test_quoted_prices_are_matched_to_engine_objects():
    c = _chat_context(); p = build_chart_overlays(c)
    cmd = build_chat_chart_command("Ringkas.", "Resistance terdekat di 101.00, support 99.00.", p, c)
    ids = _ops(cmd)["highlight"]["ids"]
    names = {o["id"]: o["name"] for o in p["overlays"]}
    assert any(names[i].startswith("Resistance") for i in ids) and any(names[i].startswith("Support") for i in ids)


def test_unrelated_numbers_create_nothing():
    c = _chat_context(); p = build_chart_overlays(c)
    cmd = build_chat_chart_command("Halo", "Angka 55.55 tidak ada di engine.", p, c)
    assert cmd["operations"] == []


def test_clear_command():
    c = _chat_context(); p = build_chart_overlays(c)
    cmd = build_chat_chart_command("Tolong hapus gambar AI di chart", "Oke.", p, c)
    assert cmd["operations"][0] == {"op": "clear", "scope": "ai"}


def main():
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
