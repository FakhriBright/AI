"""Offline checks for deterministic ICT evidence and scenario selection."""
from types import SimpleNamespace

from app.services.ai.desk import detect_fvg_order_blocks
from app.services.ai.serializer import fingerprint_context
from app.services.analysis.pipeline import _select_scenario
from app.services.analysis.scenario import Scenario, ScenarioAnalysis
from app.services.analysis.breakout_classifier import classify_support_rejection


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
        name="scalp_bullish_reversal", direction="bullish", status="conditional",
        trigger="support", invalidation="break support", conviction="low",
        confluence_score=20, trigger_reference=100, trigger_distance_atr=0.8,
    )
    strong_bear = Scenario(
        name="scalp_bearish_continuation", direction="bearish", status="conditional",
        trigger="support break", invalidation="resistance", conviction="high",
        confluence_score=75, trigger_reference=95, trigger_distance_atr=0.4,
    )
    bias = SimpleNamespace(
        overall="bullish",
        htf=SimpleNamespace(direction="bullish"),
        intraday=SimpleNamespace(direction="mixed"),
    )
    selected = _select_scenario(
        ScenarioAnalysis("XAUUSDm", 98, [], [weak_bull, strong_bear]),
        bias,
    )
    assert selected.name == "scalp_bearish_continuation"


def test_scenario_selection_returns_wait_when_no_scalp_candidates_exist():
    bias = SimpleNamespace(
        overall="mixed",
        htf=SimpleNamespace(direction="mixed"),
        intraday=SimpleNamespace(direction="mixed"),
    )
    selected = _select_scenario(
        ScenarioAnalysis("XAUUSDm", 4100, [], []),
        bias,
    )
    assert selected.name == "scalp_wait_for_directional_bias"
    assert selected.direction == "mixed"
    assert selected.trigger_confirmed is False
    assert "no_scalp_candidate" in selected.rationale


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


def test_bullish_reversal_confirmation_uses_support_rejection_not_resistance_break():
    # A close above support after touching it is valid; merely trading above
    # support without touching it is not a confirmed reversal.
    touched_and_reclaimed = SimpleNamespace(low=99.5, high=101.0, close=100.4)
    no_touch = SimpleNamespace(low=100.2, high=101.2, close=100.8)
    failed_reclaim = SimpleNamespace(low=99.4, high=100.3, close=99.8)

    assert classify_support_rejection([touched_and_reclaimed], 100).status == "pullback_valid"
    assert classify_support_rejection([no_touch], 100).status == "awaiting"
    assert classify_support_rejection([failed_reclaim], 100).status == "false_breakout"


def test_fvg_is_not_marked_touched_by_candle_entirely_below_zone():
    candles = [
        _c(9.8, 10.0, 9.5, 9.9, 0),
        _c(10.0, 10.4, 9.8, 10.3, 1),
        _c(10.5, 11.2, 10.5, 11.0, 2),  # bullish FVG from 10.0 to 10.5
        _c(9.4, 9.8, 9.1, 9.5, 3),      # below the gap; no overlap
    ]
    result = detect_fvg_order_blocks(candles, current_price=9.6, atr=1.0)
    bullish = next(z for z in result["fvg"] if z["direction"] == "bullish")
    assert bullish["fresh"] is True
