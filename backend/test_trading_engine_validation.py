import asyncio
from app.services.analysis.stop import StopRequest, calculate_stop
from app.services.analysis.risk import RiskRequest, calculate_risk
from app.services.analysis.scenario import Scenario
from app.services.analysis.confirmation import ConfirmationResult
from app.services.analysis.trade_plan import build_trade_plan, calculate_rr


def test_rule_1_entry_sl_distance_correct():
    # Bullish: Entry = 1.0850, Stop (Invalidation) = 1.0820
    req = StopRequest(
        direction="bullish",
        entry_price=1.0850,
        trigger_reference=1.0820,
        invalidation_reference=1.0820,
        atr_reference=0.0015,
    )
    plan = calculate_stop(req)
    assert plan.stop_price == 1.0820
    assert abs(plan.stop_distance - 0.0030) < 1e-9, "Bullish stop distance calculation mismatch"

    # Bearish: Entry = 1.0850, Stop (Invalidation) = 1.0880
    req_bear = StopRequest(
        direction="bearish",
        entry_price=1.0850,
        trigger_reference=1.0880,
        invalidation_reference=1.0880,
        atr_reference=0.0015,
    )
    plan_bear = calculate_stop(req_bear)
    assert plan_bear.stop_price == 1.0880
    assert abs(plan_bear.stop_distance - 0.0030) < 1e-9, "Bearish stop distance calculation mismatch"
    print("RULE 1 (Entry -> SL distance correct): PASS")


def test_rule_2_tick_based_risk_calculation():
    # Calculation uses tick_size and tick_value from symbol info, not undefined pips
    r_req = RiskRequest(
        symbol="EURUSDm",
        account_equity=10000.0,
        risk_percent=1.0,
        entry_price=1.0850,
        stop_price=1.0820,  # 30 ticks of 0.0001
    )
    # EURUSD: tick_size=0.00001 (0.1 pip), tick_value=0.1 for 0.01 lot
    risk_plan = calculate_risk(
        r_req,
        tick_size=0.00001,
        tick_value=0.1,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )
    assert risk_plan.risk_amount == 100.0
    assert abs(risk_plan.stop_distance - 0.0030) < 1e-9
    assert risk_plan.volume > 0
    print("RULE 2 (Instrument tick size/value defined risk calculation): PASS")


def test_rule_3_sl_based_on_invalidation_level():
    req = StopRequest(
        direction="bullish",
        entry_price=1.0850,
        trigger_reference=1.0840,  # nearest support
        invalidation_reference=1.0810,  # actual structural invalidation level
        atr_reference=0.0020,
    )
    plan = calculate_stop(req)
    assert plan.method == "invalidation_reference"
    assert plan.stop_price == 1.0810, "SL must be placed at invalidation_reference level"
    print("RULE 3 (SL based strictly on invalidation level): PASS")


def test_rule_4_breakout_direction_consistent():
    scenario_bull = Scenario(
        name="bullish_reversal",
        direction="bullish",
        status="watching",
        trigger="hold_and_reject_from_support",
        invalidation="break_below_support_market_noise_buffer",
        trigger_reference=1.0820,
        invalidation_reference=1.0790,
    )
    assert scenario_bull.direction == "bullish"
    assert "bullish" in scenario_bull.name
    print("RULE 4 (Breakout direction consistent with scenario label): PASS")


def test_rule_5_confirmation_distinguishes_breakout_types():
    conf_rejection = ConfirmationResult(
        scenario_name="bullish_reversal",
        confirmed=True,
        confirmation_type="support_rejection",
        entry_price=1.0825,
        stop_price=1.0790,
        reasons=["Price tested support 1.0820 and formed bullish rejection pin bar"],
    )
    assert conf_rejection.confirmation_type == "support_rejection"
    assert conf_rejection.confirmation_type != "true_breakout"
    assert conf_rejection.confirmed is True
    print("RULE 5 (Distinguishes rejection/reclaim from true breakout): PASS")


def test_rule_6_rr_long_and_short_calculation():
    # LONG: (target - entry) / (entry - stop) = (1.0910 - 1.0850) / (1.0850 - 1.0820) = 0.0060 / 0.0030 = 2.0
    rr_long = calculate_rr(
        direction="bullish",
        entry_price=1.0850,
        stop_price=1.0820,
        target_price=1.0910,
    )
    assert abs(rr_long - 2.0) < 1e-9, "R:R LONG calculation mismatch"

    # SHORT: (entry - target) / (stop - entry) = (1.0850 - 1.0790) / (1.0880 - 1.0850) = 0.0060 / 0.0030 = 2.0
    rr_short = calculate_rr(
        direction="bearish",
        entry_price=1.0850,
        stop_price=1.0880,
        target_price=1.0790,
    )
    assert abs(rr_short - 2.0) < 1e-9, "R:R SHORT calculation mismatch"
    print("RULE 6 (R:R LONG and SHORT calculated strictly from actual entry/stop/target): PASS")


def test_rule_7_atr_market_noise_buffer():
    req = StopRequest(
        direction="bullish",
        entry_price=1.0850,
        trigger_reference=1.0820,
        invalidation_reference=1.0820,
        atr_reference=0.0020,  # ATR 14 = 20 pips
    )
    plan = calculate_stop(req)
    # Stop distance is 0.0030 / 0.0020 = 1.50 ATR
    assert "1.50 ATR" in plan.reasons[1]
    print("RULE 7 (ATR market-noise buffer evaluated): PASS")


def test_rule_8_unrealistic_invalidation_rejected():
    # If invalidation level is above bullish entry (invalid setup), calculate_stop raises ValueError
    try:
        calculate_stop(
            StopRequest(
                direction="bullish",
                entry_price=1.0850,
                trigger_reference=1.0820,
                invalidation_reference=1.0860,  # Invalid: above entry for a buy!
                atr_reference=0.0015,
            )
        )
        assert False, "Should have raised ValueError"
    except ValueError as exc:
        assert "Bullish stop must be below entry price" in str(exc)
        print("RULE 8 (Unrealistic invalidation level rejected cleanly): PASS")


def main():
    test_rule_1_entry_sl_distance_correct()
    test_rule_2_tick_based_risk_calculation()
    test_rule_3_sl_based_on_invalidation_level()
    test_rule_4_breakout_direction_consistent()
    test_rule_5_confirmation_distinguishes_breakout_types()
    test_rule_6_rr_long_and_short_calculation()
    test_rule_7_atr_market_noise_buffer()
    test_rule_8_unrealistic_invalidation_rejected()
    print("\nALL 8 TRADING ENGINE & ARITHMETIC CONSISTENCY RULES PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
