"""Offline checks for deterministic ICT evidence and scenario selection."""
from types import SimpleNamespace

from app.services.ai.desk import detect_fvg_order_blocks
from app.services.ai.serializer import fingerprint_context
from app.services.analysis.pipeline import _select_scenario
from app.services.analysis.scenario import Scenario, ScenarioAnalysis


def _c(o, h, low, close, minute):
    return {
        "time_utc": f"2026-10-09T10:{minute:02d}:00+00:00",
        "open": o, "high": h, "low": low, "close": close,
    }


def test_fvg_and_order_block_are_detected_from_closed_candles():
    candles = [
        _c(10.0, 10.5, 9.5, 10.2, 0),
        _c(10.1, 10.3, 9.7, 9.8, 1),   # bearish OB candle
        _c(10.0, 12.5, 9.9, 12.0, 2),  # bullish displacement
        _c(12.1, 13.0, 11.0, 12.5, 3), # bullish FVG above candle 1 high
    ]
    result = detect_fvg_order_blocks(candles, current_price=11.8, atr=1.0)
    assert any(z["direction"] == "bullish" and z["low"] == 10.3 and z["high"] == 11.0
               for z in result["fvg"])
    assert any(z["direction"] == "bullish" and z["low"] == 9.7 and z["high"] == 10.3
               for z in result["order_blocks"])


def test_scenario_selection_uses_evidence_not_overall_bias_alone():
    weak_bull = Scenario(
        name="bullish_reversal", direction="bullish", status="conditional",
        trigger="support", invalidation="break support", conviction="low",
        confluence_score=20, trigger_reference=100, trigger_distance_atr=0.8,
    )
    strong_bear = Scenario(
        name="bearish_continuation", direction="bearish", status="conditional",
        trigger="support break", invalidation="resistance", conviction="high",
        confluence_score=75, trigger_reference=95, trigger_distance_atr=0.4,
    )
    bias = SimpleNamespace(
        overall="bullish",
        htf=SimpleNamespace(direction="bullish"),
        intraday=SimpleNamespace(direction="mixed"),
    )
    selected = _select_scenario(
        ScenarioAnalysis("XAUUSDm", 98, [weak_bull, strong_bear], []),
        bias,
    )
    assert selected.name == "bearish_continuation"


def test_fingerprint_ignores_only_narrative_only_trade_plan_fields():
    base = {
        "generated_at_utc": "10:00",
        "trade_plan": {
            "status": "conditional", "entry_price": 100,
            "reasons": ["price=100"], "warnings": ["forming candle"],
        },
    }
    changed_notes = {
        "generated_at_utc": "10:00:30",
        "trade_plan": {
            "status": "conditional", "entry_price": 100,
            "reasons": ["price=101"], "warnings": ["new forming candle"],
        },
    }
    changed_state = {
        "generated_at_utc": "10:00:30",
        "trade_plan": {
            "status": "confirmed", "entry_price": 101,
            "reasons": ["price=101"], "warnings": [],
        },
    }
    assert fingerprint_context(base) == fingerprint_context(changed_notes)
    assert fingerprint_context(base) != fingerprint_context(changed_state)
