"""Desk router + token budget tests. Offline: no MT5, no API keys."""
import asyncio
import json
from datetime import datetime, timezone

from test_ai_candle_evidence import FORMING_MARK, FakeProvider, TIMEFRAMES
from app.services.ai.base import AIResponse
from app.services.ai.chat_context import select_chat_context
from app.services.ai.desk import (
    build_desk_brief,
    chat_context_max_chars,
    collapse_patterns,
    context_size,
    dumps,
    killzone,
    pattern_family,
    shrink_to_budget,
)
from app.services.ai.prompt import build_analysis_prompt
from app.services.ai.reasoning import AIReasoningService
from app.services.analysis.pipeline import analyze_symbol


def _ai_context():
    r = asyncio.run(analyze_symbol("XAUUSDm", FakeProvider(), ai_service=None, run_ai=False))
    return r.ai_context


def test_alias_collapse_one_evidence_per_family():
    out = collapse_patterns(
        [
            {"name": "pin_bar", "direction": "bullish", "strength": "moderate", "reasons": ["a"], "confirmation": "x"},
            {"name": "hammer", "direction": "bullish", "strength": "weak", "reasons": ["b"], "confirmation": "y"},
            {"name": "engulfing", "direction": "bullish", "strength": "strong", "reasons": ["c"], "confirmation": "z"},
            {"name": "bullish_engulfing", "direction": "bullish", "strength": "moderate", "reasons": ["d"], "confirmation": "w"},
        ]
    )
    fams = {(c["family"], c["dir"]): c for c in out}
    assert len(out) == 2
    assert set(fams[("rejection", "bullish")]["names"]) == {"pin_bar", "hammer"}
    assert fams[("rejection", "bullish")]["strength"] == "moderate"
    assert fams[("displacement", "bullish")]["strength"] == "strong"


def test_families():
    assert pattern_family("morning_doji_star") == "reversal_multi"
    assert pattern_family("dragonfly_doji") == "rejection"
    assert pattern_family("long_legged_doji") == "indecision"
    assert pattern_family("inverted_hammer") == "rejection"
    assert pattern_family("three_black_crows") == "continuation_multi"
    assert pattern_family("matching_low") == "equal_level"


def test_killzone_dst_without_tzdata():
    # 2026-10-06 is EDT (UTC-4): 13:00Z -> 09:00 NY -> NY AM
    assert killzone("2026-10-06T13:00:00+00:00")["active"] == "NY AM"
    # 2026-01-15 is EST (UTC-5): 13:00Z -> 08:00 NY -> before NY AM
    assert killzone("2026-01-15T13:00:00+00:00")["active"] is None
    assert killzone("2026-01-15T07:30:00+00:00")["active"] == "London Open"


def test_desk_brief_routes_pin_bar_and_stays_closed_only():
    brief = build_desk_brief(_ai_context())
    assert brief["reads"], "pin bar fixture must produce reads"
    block = brief["reads"][0]
    assert block["candle"] and len(block["candle"]) == 5
    rej = [p for p in block["patterns"] if p["family"] == "rejection"][0]
    assert rej["dir"] == "bullish"
    assert set(rej["names"]) >= {"pin_bar", "hammer"}  # merged, one evidence
    assert rej["route"]["desk"] and rej["route"]["needs"]
    assert len({b["tf"] for b in brief["reads"]}) == len(brief["reads"])
    assert str(FORMING_MARK) not in dumps(brief)
    assert brief["entry_gate"]["can_enter_now"] in (True, False)
    assert "SNR" in brief["desks"]


def test_chat_context_fits_budget_and_is_much_smaller_than_full():
    full = _ai_context()
    full_size = context_size(full)
    for q in (
        "coba analisis dan kasih gw setup buat entry",
        "yakin ngga sell",
        "Why bearish?",
        "berapa risk amount?",
    ):
        ctx = select_chat_context(full, q)
        size = context_size(shrink_to_budget(ctx, chat_context_max_chars()))
        assert size <= chat_context_max_chars(), (q, size)
        assert size < full_size / 3
        for key in ("symbol", "trade_plan", "desk"):
            assert key in ctx


def test_analysis_prompt_is_routed_and_compact():
    full = _ai_context()
    prompt = build_analysis_prompt(full)
    assert "STRUCTURED MARKET CONTEXT" in prompt
    assert "DESK BRIEF" in prompt
    # forming candle may only appear inside trade_plan's live-check text
    body = prompt.split("STRUCTURED MARKET CONTEXT\n", 1)[1]
    ctx = json.loads(body)
    ctx["trade_plan"].pop("reasons", None)
    ctx["trade_plan"].pop("warnings", None)
    assert str(FORMING_MARK) not in dumps(ctx)
    assert "live_check_note" in body
    # old monolithic prompt + full context was ~55k chars here
    assert len(prompt) < 22000
    minimal = build_analysis_prompt(full, minimal=True)
    assert len(minimal) < len(prompt) * 0.8


class Provider413:
    """First call -> 413 (like Groq), second call succeeds."""

    class E(Exception):
        status_code = 413

    def __init__(self):
        self.calls = []

    async def analyze(self, payload):
        self.calls.append(payload)
        if len(self.calls) == 1:
            raise self.E("too large")
        return AIResponse(provider="mock", model="m", analysis="ok")


def test_chat_retries_smaller_after_413():
    full = _ai_context()
    ctx = select_chat_context(full, "kasih setup entry")
    p = Provider413()
    resp = asyncio.run(AIReasoningService(p).chat(ctx, "kasih setup entry"))
    assert resp.analysis == "ok" and len(p.calls) == 2
    assert len(p.calls[1]["analysis_prompt"]) < len(p.calls[0]["analysis_prompt"])


def test_chat_system_instruction_has_no_fixed_template():
    from app.services.ai.reasoning import CHAT_SYSTEM_INSTRUCTION as S

    assert "Belum ada entry saat ini" not in S
    assert "can_enter_now" in S and "desk.setups" in S


def _setup_ctx():
    return {
        "key_levels": {
            "current_price": 100.0,
            "supports": [{"price": 98.5}, {"price": 95.0}, {"price": 90.0}],
            "resistances": [{"price": 99.4}, {"price": 105.0}],
        },
        "scenarios": {
            "current_price": 100.0,
            "intraday_scenarios": [
                {"name": "bearish_continuation", "direction": "bearish",
                 "trigger_reference": 99.0, "invalidation_reference": 104.0,
                 "conviction": "low", "trigger_confirmed": False},
                {"name": "bullish_reversal", "direction": "bullish",
                 "trigger_reference": 99.0, "invalidation_reference": 98.0,
                 "conviction": "low", "trigger_confirmed": False},
            ],
        },
    }


def test_setup_target_skips_noise_levels_and_rr_math_is_precomputed():
    from app.services.ai.desk import build_setups

    by = {s["scenario"]: s for s in build_setups(_setup_ctx())}
    bear, bull = by["bearish_continuation"], by["bullish_reversal"]

    # no ATR in this fixture: ATR checks are skipped and flagged
    assert "atr_tidak_tersedia" in bear["ref"]["flags"]
    # bearish: risk@ref=5, min gap=2.5 -> 98.5 skipped (noise), target=95
    assert bear["ref"]["target"] == 95.0
    assert bear["ref"]["rr"] == 0.8          # (99-95)/5
    assert "rr_di_bawah_1" in bear["ref"]["flags"]
    # market entry 100: risk=104-100=4, reward=100-95=5
    now = bear["now"]
    assert (now["risk"], now["reward"], now["rr"]) == (4.0, 5.0, 1.25)
    assert bear["mode"] == "intraday"

    # bullish: risk@ref=1, min gap=0.5 -> 99.4 skipped, target=105
    assert bull["ref"]["target"] == 105.0
    assert bull["ref"]["rr"] == 6.0
    assert "rr_tidak_wajar_tinggi" in bull["ref"]["flags"]   # RR 6 is suspicious
    nowb = bull["now"]
    assert (nowb["risk"], nowb["reward"], nowb["rr"]) == (2.0, 5.0, 2.5)


def test_setup_now_invalid_when_price_beyond_stop_or_target():
    from app.services.ai.desk import build_setups

    ctx = _setup_ctx()
    ctx["key_levels"]["current_price"] = 104.5   # above bearish stop 104
    ctx["scenarios"]["current_price"] = 104.5
    bear = [s for s in build_setups(ctx) if s["dir"] == "bearish"][0]
    assert bear["now"]["verdict"] == "reject"
    assert "melewati stop" in bear["now"]["note"] and "rr" not in bear["now"]


def _xau_ctx(price=4133.945, resistances=(4134.379, 4138.864, 4145.0)):
    """The exact shape of the case that produced a bogus 20R setup."""
    return {
        "key_levels": {
            "current_price": price,
            "supports": [{"price": 4131.238}, {"price": 4125.104}, {"price": 4120.0}],
            "resistances": [{"price": r} for r in resistances],
        },
        "scenarios": {
            "current_price": price,
            "intraday_scenarios": [
                {"name": "bearish_continuation", "direction": "bearish",
                 "trigger_reference": 4131.238, "invalidation_reference": 4134.379,
                 "atr_reference": 2.0, "conviction": "medium",
                 "trigger_confirmed": False},
            ],
        },
    }


def test_tight_scenario_stop_is_replaced_not_sold_as_20R():
    from app.services.ai.desk import build_setups

    setup = build_setups(_xau_ctx())[0]
    now = setup["now"]
    # raw scenario stop is only 0.434 from price (0.22 ATR) -> naive RR ~20
    assert now["raw_stop"] == 4134.379
    assert now["stop_src"] == "struktur+buffer"
    assert now["stop"] == 4139.364                # next resistance 4138.864 + 0.25*ATR(2.0)
    assert now["stop_atr"] == 2.71                # 5.419 / 2.0
    assert now["rr"] == 1.63                      # 8.841 / 5.419
    assert now["rr"] < 5
    assert now["verdict"] == "ok"                 # final numbers are healthy
    assert "terlalu rapat" in now["stop_note"] and "2.71 ATR" in now["stop_note"]
    assert "flags" not in now                     # replacement is info, not a warning
    # pending view uses the real trigger with a healthy stop
    ref = setup["ref"]
    assert (ref["entry"], ref["stop"], ref["target"]) == (4131.238, 4134.379, 4125.104)
    assert ref["rr"] == 1.95 and ref["verdict"] == "ok"


def test_tight_stop_without_structure_falls_back_to_atr_stop():
    from app.services.ai.desk import build_setups

    now = build_setups(_xau_ctx(resistances=(4134.379,)))[0]["now"]
    assert now["stop_src"] == "atr"
    assert now["stop"] == 4135.945                # entry + 1.0 ATR
    assert now["stop_atr"] == 1.0


def test_target_too_close_and_wide_stop_are_flagged():
    from app.services.ai.desk import _plan_view

    lv = {"supports": [], "resistances": []}
    close = _plan_view("bearish", 100.0, 101.5, 99.0, 2.0, lv, 100.0)
    assert any(f.startswith("target_terlalu_dekat") for f in close["flags"])
    wide = _plan_view("bearish", 100.0, 108.0, 92.0, 2.0, lv, 100.0)
    assert any(f.startswith("stop_terlalu_lebar") for f in wide["flags"])
    assert wide["verdict"] == "reject"
    nt = _plan_view("bullish", 100.0, 98.0, None, 2.0, lv, 100.0)
    assert nt["verdict"] == "reject" and "tidak_ada_target_layak" in nt["flags"]


def test_replacement_stop_is_never_absurdly_far_and_unrealistic_target_rejected():
    """Regression: a 'replaced' stop was once 10.7 ATR (22 points) away."""
    from app.services.ai.desk import build_setups

    ctx = {
        "key_levels": {
            "current_price": 4195.669,
            "supports": [{"price": 4194.878}, {"price": 4173.9}, {"price": 4150.0}],
            "resistances": [{"price": 4219.41}, {"price": 4240.0}],
        },
        "scenarios": {"current_price": 4195.669, "intraday_scenarios": [
            {"name": "bullish_reversal", "direction": "bullish",
             "trigger_reference": 4194.878, "invalidation_reference": 4194.3,
             "atr_reference": 2.0, "conviction": "low", "trigger_confirmed": False}]},
    }
    setup = build_setups(ctx)[0]
    for view in (setup["ref"], setup["now"]):
        assert view["stop_atr"] <= 1.0           # ATR stop, not a far level
        assert view["stop_src"] == "atr"
        assert "level struktur terlalu jauh" in view["stop_note"]
        assert any(f.startswith("target_terlalu_jauh") for f in view["flags"])
        assert view["verdict"] == "reject"       # 12 ATR target is not a plan
    assert setup["ref"]["order"] == "buy_limit"  # entry below price -> limit
    assert "kembali di atasnya" in setup["confirm_rule"]


def test_order_type_geometry():
    from app.services.ai.desk import _order_type

    assert _order_type("bullish", 99.0, 100.0, 2.0) == "buy_limit"
    assert _order_type("bullish", 101.0, 100.0, 2.0) == "buy_stop"
    assert _order_type("bearish", 101.0, 100.0, 2.0) == "sell_limit"
    assert _order_type("bearish", 99.0, 100.0, 2.0) == "sell_stop"
    assert _order_type("bearish", 100.1, 100.0, 2.0) == "market"


def test_pattern_relevance_far_pattern_is_not_evidence():
    from app.services.ai.desk import pattern_relevance, build_setups

    candle = {"open": 4132, "high": 4133, "low": 4130, "close": 4131}
    far = pattern_relevance({"at": "resistance", "price": 4170.0}, candle, 4133.945, 2.0)
    assert far[0] == "far"
    near = pattern_relevance({"at": "support", "price": 4133.0}, candle, 4133.945, 2.0)
    assert near[0] == "near"

    reads = [{"tf": "H4", "rel": "far", "patterns": [
        {"dir": "bearish", "family": "rejection", "names": ["tweezer_top"]}]}]
    setup = build_setups(_xau_ctx(), reads)[0]
    assert "patterns_for" not in setup           # far pattern never supports a setup


def test_brief_has_snapshot_and_mode_labelled_blockers():
    ctx = _xau_ctx()
    ctx["scenarios"]["scalp_scenarios"] = [
        {"name": "scalp_bearish", "direction": "bearish", "trigger_reference": 4132.409,
         "invalidation_reference": 4134.9, "trigger_confirmed": False,
         "breakout_status": "awaiting"}]
    ctx["generated_at_utc"] = "2026-10-09T06:00:00+00:00"
    ctx["multi_timeframe"] = {"M15": {"atr14": 2.0, "candles": [], "patterns": []}}
    brief = build_desk_brief(ctx)
    assert brief["snapshot"]["price"] == 4133.945
    assert brief["snapshot"]["time_utc"] == "2026-10-09T06:00:00+00:00"
    joined = " ".join(brief["entry_gate"]["blockers"])
    assert "[scalp]" in joined and "[intraday]" in joined   # triggers never mixed
    assert {s["mode"] for s in brief["setups"]} == {"intraday", "scalp"}


def test_setup_patterns_only_support_same_direction():
    from app.services.ai.desk import build_setups

    reads = [{"tf": "H1", "patterns": [
        {"dir": "bearish", "family": "displacement", "names": ["bearish_engulfing"]},
        {"dir": "bullish", "family": "reversal_multi", "names": ["morning_star"]},
        {"dir": "neutral", "family": "indecision", "names": ["doji"]},
    ]}]
    reads = [{**r, "rel": "near"} for r in reads]
    by = {s["dir"]: s for s in build_setups(_setup_ctx(), reads)}
    assert by["bearish"]["patterns_for"] == ["H1 displacement [bearish_engulfing]"]
    assert by["bearish"]["patterns_against"] == ["H1 reversal_multi [morning_star]"]
    assert by["bullish"]["patterns_for"] == ["H1 reversal_multi [morning_star]"]
    assert "doji" not in dumps(by)


def test_ict_discount_favors_buy_and_killzone_flag():
    from app.services.ai.desk import premium_discount

    sw = [{"type": "swing_low", "price": 90.0}, {"type": "swing_high", "price": 110.0}]
    assert premium_discount(sw, 95.0)["favors"] == "buy"
    assert premium_discount(sw, 105.0)["favors"] == "sell"
    assert premium_discount(sw, 100.0)["favors"] == "netral"
    assert premium_discount(sw, 115.0)["state"] == "outside_range"
    assert premium_discount(sw, 115.0)["favors"] == "netral"
    # 22:00 NY is not a killzone
    kz = killzone("2026-10-07T02:00:00+00:00")  # EDT -> 22:00 NY
    assert kz["ny_time"] == "22:00" and kz["in_killzone"] is False


def test_chat_instruction_matches_frontend_renderer():
    from app.services.ai.reasoning import CHAT_SYSTEM_INSTRUCTION as S

    for needle in ("DILARANG: tabel", "JANGAN menghitung ulang", "verdict",
                   "discount mendukung BUY", "in_killzone", "jangan \"pip\""):
        assert needle in S, needle


if __name__ == "__main__":
    full = _ai_context()
    ctx = select_chat_context(full, "coba analisis dan kasih gw setup buat entry")
    print("full ai_context chars:", context_size(full))
    print("chat context chars   :", context_size(ctx))
    print(json.dumps(ctx["desk"], indent=1, ensure_ascii=False)[:3800])
