import pytest

from app.services.analysis.confirmation import ConfirmationResult
from app.services.analysis.levels import KeyLevels, LevelZone
from app.services.analysis.risk import RiskPlan
from app.services.analysis.scenario import Scenario, build_scenarios
from types import SimpleNamespace
from app.services.analysis.stop import StopPlan
from app.services.analysis.trade_plan import build_trade_plan, calculate_rr


def zone(price, kind):
    return LevelZone(
        price=price, low=price - 0.1, high=price + 0.1,
        level_type=kind, timeframes=["M15"], touches=2, is_fresh=False,
    )


def make_plan(direction, entry, stop, levels):
    scenario = Scenario(
        name="test_candidate", direction=direction, status="confirmed",
        trigger="test trigger", invalidation="test invalidation",
        trigger_reference=entry,
    )
    confirmation = ConfirmationResult(
        scenario_name=scenario.name, confirmed=True,
        confirmation_type="closed_candle_confirmation",
        entry_price=entry, stop_price=stop,
    )
    stop_plan = StopPlan(
        direction=direction, entry_price=entry, stop_price=stop,
        stop_distance=abs(entry - stop), method="test", reasons=[],
    )
    risk_plan = RiskPlan(
        symbol="TEST", account_equity=1000, risk_percent=1,
        risk_amount=10, entry_price=entry, stop_price=stop,
        stop_distance=abs(entry-stop), tick_size=0.01, tick_value=1,
        raw_volume=0.1, volume=0.1, estimated_loss=10,
    )
    return build_trade_plan(
        symbol="TEST", scenario=scenario, confirmation=confirmation,
        stop_plan=stop_plan, risk_plan=risk_plan, levels=levels,
    )


def test_rr_rejects_reward_on_wrong_side():
    with pytest.raises(ValueError):
        calculate_rr("bearish", 99, 105, 100)


def test_bearish_target_must_be_below_entry_not_nearest_current_level():
    levels = KeyLevels(
        symbol="TEST", current_price=100,
        supports=[zone(100, "support"), zone(90, "support"), zone(80, "support")],
        resistances=[zone(110, "resistance")],
    )
    plan = make_plan("bearish", 99, 105, levels)
    assert plan.target_price == 90
    assert plan.rr_ratio == pytest.approx(9 / 6)


def test_bullish_target_must_be_above_entry():
    levels = KeyLevels(
        symbol="TEST", current_price=100,
        supports=[zone(90, "support")],
        resistances=[zone(100, "resistance"), zone(110, "resistance")],
    )
    plan = make_plan("bullish", 101, 95, levels)
    assert plan.target_price == 110
    assert plan.rr_ratio == pytest.approx(9 / 6)


def test_engine_keeps_alternative_support_candidates_for_comparison():
    timeframe = lambda trend: SimpleNamespace(
        trend=trend, atr14=1.0, candles=[], price=100.0
    )
    context = SimpleNamespace(
        symbol="TEST",
        timeframes={"M15": timeframe("bearish"), "H4": timeframe("bearish")},
    )
    bias = SimpleNamespace(
        htf=SimpleNamespace(direction="bearish"),
        intraday=SimpleNamespace(direction="bearish"),
        entry=SimpleNamespace(direction="bearish"),
        conflicts=[],
    )
    levels = KeyLevels(
        symbol="TEST", current_price=100,
        supports=[zone(99, "support"), zone(98, "support"), zone(97, "support")],
        resistances=[zone(101, "resistance")],
    )

    analysis = build_scenarios(context, bias, levels)
    names = {candidate.name for candidate in analysis.scenarios}

    assert "bearish_continuation" in names
    assert "bearish_continuation_support_2" in names
    assert "bearish_continuation_support_3" in names
    assert "bullish_reversal_support_2" in names
    assert "bullish_reversal_support_3" in names
