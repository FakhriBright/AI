from app.services.analysis.stop import StopRequest, calculate_stop


def print_plan(name, plan):
    print()
    print(f"[{name}]")
    print(f"DIRECTION     : {plan.direction}")
    print(f"ENTRY PRICE   : {plan.entry_price}")
    print(f"STOP PRICE    : {plan.stop_price}")
    print(f"STOP DISTANCE : {plan.stop_distance}")
    print(f"METHOD        : {plan.method}")

    print("REASONS:")
    for reason in plan.reasons:
        print(f"  - {reason}")


print("=" * 60)
print("STOP PLACEMENT TEST")
print("=" * 60)


# ------------------------------------------------------------
# 1. BEARISH
# ------------------------------------------------------------

bearish = calculate_stop(
    StopRequest(
        direction="bearish",
        entry_price=1.14720,
        trigger_reference=1.14725,
        invalidation_reference=1.14753,
        atr_reference=0.00030,
    )
)

print_plan("BEARISH", bearish)


# ------------------------------------------------------------
# 2. BULLISH
# ------------------------------------------------------------

bullish = calculate_stop(
    StopRequest(
        direction="bullish",
        entry_price=1.14735,
        trigger_reference=1.14725,
        invalidation_reference=None,
        atr_reference=0.00030,
    )
)

print_plan("BULLISH", bullish)


# ------------------------------------------------------------
# 3. INVALID BEARISH
# ------------------------------------------------------------

print()
print("[INVALID BEARISH]")

try:
    calculate_stop(
        StopRequest(
            direction="bearish",
            entry_price=1.14750,
            trigger_reference=1.14725,
            invalidation_reference=1.14730,
            atr_reference=0.00030,
        )
    )
except ValueError as error:
    print(f"ERROR CAUGHT : {error}")


# ------------------------------------------------------------
# 4. INVALID BULLISH
# ------------------------------------------------------------

print()
print("[INVALID BULLISH]")

try:
    calculate_stop(
        StopRequest(
            direction="bullish",
            entry_price=1.14720,
            trigger_reference=1.14730,
            invalidation_reference=None,
            atr_reference=0.00030,
        )
    )
except ValueError as error:
    print(f"ERROR CAUGHT : {error}")
