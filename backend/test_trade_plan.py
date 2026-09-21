from app.services.analysis.confirmation import ConfirmationResult
from app.services.analysis.risk import RiskPlan
from app.services.analysis.scenario import Scenario
from app.services.analysis.stop import StopPlan
from app.services.analysis.trade_plan import build_trade_plan


scenario = Scenario(
    name="bullish_reversal",
    direction="bullish",
    status="candidate",
    trigger="support rejection",
    invalidation="below support",
    trigger_reference=1.14725,
)


confirmation = ConfirmationResult(
    scenario_name="bullish_reversal",
    confirmed=True,
    confirmation_type="support_rejection",
    entry_price=1.14756,
    stop_price=None,
    reasons=[
        "Price touched support and reclaimed it"
    ],
)


stop_plan = StopPlan(
    direction="bullish",
    entry_price=1.14756,
    stop_price=1.147225,
    stop_distance=0.000335,
    method="trigger_reference",
    reasons=[
        "Stop placed below bullish entry"
    ],
)


risk_plan = RiskPlan(
    symbol="EURUSDm",
    account_equity=1000.0,
    risk_percent=1.0,
    risk_amount=10.0,
    entry_price=1.14756,
    stop_price=1.147225,
    stop_distance=0.000335,
    tick_size=0.00001,
    tick_value=1.0,
    raw_volume=0.2985,
    volume=0.29,
    estimated_loss=9.715,
)


plan = build_trade_plan(
    symbol="EURUSDm",
    scenario=scenario,
    confirmation=confirmation,
    stop_plan=stop_plan,
    risk_plan=risk_plan,
)


print("=" * 60)
print("TRADE PLAN TEST")
print("=" * 60)

print(f"SYMBOL          : {plan.symbol}")
print(f"SCENARIO        : {plan.scenario_name}")
print(f"DIRECTION       : {plan.direction}")
print(f"STATUS          : {plan.status}")
print(f"ENTRY           : {plan.entry_price}")
print(f"STOP            : {plan.stop_price}")
print(f"STOP DISTANCE   : {plan.stop_distance}")
print(f"CONFIRMATION    : {plan.confirmation_type}")
print(f"STOP METHOD     : {plan.stop_method}")
print(f"RISK %          : {plan.risk_percent}")
print(f"RISK AMOUNT     : {plan.risk_amount}")
print(f"VOLUME          : {plan.volume}")
print(f"EST. LOSS       : {plan.estimated_loss}")

print()
print("REASONS:")
for reason in plan.reasons:
    print(f"  - {reason}")

print()
print("WARNINGS:")
for warning in plan.warnings:
    print(f"  - {warning}")
