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


if __name__ == "__main__":
    full = _ai_context()
    ctx = select_chat_context(full, "coba analisis dan kasih gw setup buat entry")
    print("full ai_context chars:", context_size(full))
    print("chat context chars   :", context_size(ctx))
    print(json.dumps(ctx["desk"], indent=1, ensure_ascii=False)[:3800])
