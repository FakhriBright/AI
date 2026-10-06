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
    assert len(minimal) < len(prompt) * 0.7


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

    # bearish: risk@ref=5, min gap=2.5 -> 98.5 skipped (noise), target=95
    assert bear["target_ref"] == 95.0
    assert bear["rr_at_ref"] == 0.8          # (99-95)/5
    # market entry 100: risk=104-100=4, reward=100-95=5
    assert (bear["now_risk"], bear["now_reward"], bear["now_rr"]) == (4.0, 5.0, 1.25)

    # bullish: risk@ref=1, min gap=0.5 -> 99.4 skipped, target=105
    assert bull["target_ref"] == 105.0
    assert bull["rr_at_ref"] == 6.0
    # market entry 100: risk=100-98=2, reward=105-100=5
    assert (bull["now_risk"], bull["now_reward"], bull["now_rr"]) == (2.0, 5.0, 2.5)


def test_setup_now_invalid_when_price_beyond_stop_or_target():
    from app.services.ai.desk import build_setups

    ctx = _setup_ctx()
    ctx["key_levels"]["current_price"] = 104.5   # above bearish stop 104
    ctx["scenarios"]["current_price"] = 104.5
    bear = [s for s in build_setups(ctx) if s["dir"] == "bearish"][0]
    assert "now_rr" not in bear and "stop_ref" in bear["now_note"]


def test_setup_patterns_only_support_same_direction():
    from app.services.ai.desk import build_setups

    reads = [{"tf": "H1", "patterns": [
        {"dir": "bearish", "family": "displacement", "names": ["bearish_engulfing"]},
        {"dir": "bullish", "family": "reversal_multi", "names": ["morning_star"]},
        {"dir": "neutral", "family": "indecision", "names": ["doji"]},
    ]}]
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

    for needle in ("DILARANG: tabel", "JANGAN menghitung ulang", "now_rr",
                   "discount mendukung BUY", "in_killzone", "jangan \"pip\""):
        assert needle in S, needle


if __name__ == "__main__":
    full = _ai_context()
    ctx = select_chat_context(full, "coba analisis dan kasih gw setup buat entry")
    print("full ai_context chars:", context_size(full))
    print("chat context chars   :", context_size(ctx))
    print(json.dumps(ctx["desk"], indent=1, ensure_ascii=False)[:3800])
