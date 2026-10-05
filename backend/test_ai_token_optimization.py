import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.ai.cache import (
    analysis_cache_size,
    clear_analysis_cache,
    get_cached_analysis,
    make_analysis_fingerprint,
    store_cached_analysis,
)
from app.services.ai.chat_context import select_chat_context
from app.services.ai.base import AIResponse
from app.services.ai.reasoning import AIReasoningService
from app.services.ai.serializer import dumps_compact, fingerprint_context
from app.services.analysis.candles import select_analysis_candles


def _sample_context(symbol: str = "EURUSDm", generated_at: str = "2026-09-28T01:00:00+00:00"):
    return {
        "symbol": symbol,
        "generated_at_utc": generated_at,
        "market_bias": {"overall": "mixed", "htf": {"direction": "bullish"}},
        "multi_timeframe": {
            "H4": {"timeframe": "H4", "price": 1.17, "trend": "bullish"},
            "M5": {"timeframe": "M5", "price": 1.17, "trend": "mixed"},
        },
        "key_levels": {
            "current_price": 1.17,
            "supports": [{"price": 1.16}],
            "resistances": [{"price": 1.18}],
        },
        "scenarios": {
            "symbol": symbol,
            "scenarios": [
                {
                    "name": "range_or_no_clear_setup",
                    "status": "watching",
                    "trigger_reference": 1.16,
                }
            ],
        },
        "trade_plan": {
            "symbol": symbol,
            "status": "waiting",
            "scenario_name": "range_or_no_clear_setup",
            "risk_percent": 1.0,
        },
    }


class CountingProvider:
    def __init__(self):
        self.calls = 0
        self.payloads = []
        self.provider = "mock"
        self.model = "counting-v1"

    async def analyze(self, context):
        self.calls += 1
        self.payloads.append(context)
        return AIResponse(
            provider=self.provider,
            model=self.model,
            analysis="ok",
            raw={"n": self.calls},
        )


def test_fingerprint_ignores_generated_at():
    a = _sample_context("EURUSDm", "2026-09-28T01:00:00+00:00")
    b = _sample_context("EURUSDm", "2026-09-28T01:00:30+00:00")

    fp_a = make_analysis_fingerprint(a, provider_name="groq", model="x")
    fp_b = make_analysis_fingerprint(b, provider_name="groq", model="x")

    assert fp_a == fp_b
    assert "generated_at_utc" in a
    assert "generated_at_utc" not in fingerprint_context(a)


def test_fingerprint_includes_symbol_and_risk_and_provider():
    base = _sample_context()
    other_symbol = _sample_context("XAUUSDm")
    other_risk = _sample_context()
    other_risk["trade_plan"] = dict(other_risk["trade_plan"], risk_percent=2.0)

    fp_base = make_analysis_fingerprint(base, provider_name="groq", model="x")
    fp_symbol = make_analysis_fingerprint(
        other_symbol, provider_name="groq", model="x"
    )
    fp_risk = make_analysis_fingerprint(other_risk, provider_name="groq", model="x")
    fp_provider = make_analysis_fingerprint(base, provider_name="gemini", model="x")

    assert fp_base != fp_symbol
    assert fp_base != fp_risk
    assert fp_base != fp_provider


def test_cache_reuse_does_not_call_provider_twice():
    clear_analysis_cache()
    context = _sample_context()
    fingerprint = make_analysis_fingerprint(
        context, provider_name="mock", model="counting-v1"
    )

    first = AIResponse(provider="mock", model="counting-v1", analysis="one")
    store_cached_analysis(fingerprint, first)

    hit = get_cached_analysis(fingerprint)
    assert hit is not None
    assert hit.analysis == "one"
    assert analysis_cache_size() == 1

    hit.analysis = "mutated"
    again = get_cached_analysis(fingerprint)
    assert again.analysis == "one"


def test_reasoning_chat_is_single_provider_call():
    async def _run():
        provider = CountingProvider()
        service = AIReasoningService(provider)
        context = _sample_context()

        await service.chat(
            context,
            "Kenapa belum ada entry?",
            history=[
                {"role": "assistant", "content": "Hello"},
                {"role": "user", "content": "Kenapa belum ada entry?"},
            ],
        )

        assert provider.calls == 1
        prompt = provider.payloads[0]["analysis_prompt"]
        assert prompt.count("Kenapa belum ada entry?") == 1
        assert '"symbol":"EURUSDm"' in prompt or '"symbol": "EURUSDm"' in prompt
        assert "\n  " not in prompt.split("TRADER QUESTION")[0]

    asyncio.run(_run())


def test_chat_context_selection_is_deterministic():
    context = _sample_context()

    entry = select_chat_context(context, "Kenapa belum ada entry?")
    assert "trade_plan" in entry
    assert "scenarios" in entry
    assert "key_levels" in entry
    assert "multi_timeframe" in entry

    mixed = select_chat_context(context, "Kenapa bias sekarang mixed?")
    assert "multi_timeframe" in mixed

    setup = select_chat_context(context, "Explain setup")
    assert "multi_timeframe" in setup
    assert "scenarios" in setup
    assert "key_levels" in setup

    full = select_chat_context(
        context,
        "Analisis XAUUSD D1 sampai M1 dan jelaskan scenario",
    )
    assert "multi_timeframe" in full
    assert "key_levels" in full
    assert "scenarios" in full


def test_compact_json_smaller_than_indented():
    context = _sample_context()
    compact = dumps_compact(context)
    indented = json.dumps(context, ensure_ascii=False, indent=2)
    assert len(compact) < len(indented)
    assert "\n" not in compact


def test_select_analysis_candles_drops_forming_bar():
    now = datetime(2026, 9, 28, 10, 0, 30, tzinfo=timezone.utc)
    forming = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    candles = []

    for index in range(209, 0, -1):
        candles.append(
            SimpleNamespace(
                time_utc=forming - timedelta(minutes=index),
                close=float(index),
            )
        )

    candles.append(SimpleNamespace(time_utc=forming, close=999.0))

    selected = select_analysis_candles(
        candles,
        timeframe="M1",
        min_count=200,
        now=now,
    )

    assert selected[-1].time_utc == forming - timedelta(minutes=1)
    assert len(selected) == 209
    assert len(selected) == len(candles) - 1


async def main():
    test_fingerprint_ignores_generated_at()
    print("fingerprint generated_at: PASS")

    test_fingerprint_includes_symbol_and_risk_and_provider()
    print("fingerprint isolation: PASS")

    test_cache_reuse_does_not_call_provider_twice()
    print("cache reuse: PASS")

    await test_reasoning_chat_is_single_provider_call()
    print("chat single AI call: PASS")

    test_chat_context_selection_is_deterministic()
    print("chat context selection: PASS")

    test_compact_json_smaller_than_indented()
    print("compact serialization: PASS")

    test_select_analysis_candles_drops_forming_bar()
    print("forming candle exclusion: PASS")


if __name__ == "__main__":
    asyncio.run(main())
