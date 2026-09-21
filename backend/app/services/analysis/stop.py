from dataclasses import dataclass


@dataclass
class StopRequest:
    direction: str
    entry_price: float
    trigger_reference: float
    invalidation_reference: float | None
    atr_reference: float | None


@dataclass
class StopPlan:
    direction: str
    entry_price: float
    stop_price: float
    stop_distance: float
    method: str
    reasons: list[str]


def calculate_stop(request: StopRequest) -> StopPlan:
    if request.entry_price <= 0:
        raise ValueError("Entry price must be greater than zero")

    if request.trigger_reference <= 0:
        raise ValueError("Trigger reference must be greater than zero")

    if request.direction not in {"bullish", "bearish"}:
        raise ValueError("Stop placement requires bullish or bearish direction")

    reasons: list[str] = []

    if request.direction == "bearish":
        if request.invalidation_reference is None:
            raise ValueError(
                "Bearish stop requires an invalidation reference"
            )

        stop_price = request.invalidation_reference
        method = "invalidation_reference"

        if stop_price <= request.entry_price:
            raise ValueError(
                "Bearish stop must be above entry price"
            )

        reasons.append(
            f"Stop placed above bearish entry at invalidation reference "
            f"{stop_price}"
        )

    else:
        if request.invalidation_reference is None:
            raise ValueError(
                "Bullish stop requires an invalidation reference"
            )

        stop_price = request.invalidation_reference
        method = "invalidation_reference"

        if stop_price >= request.entry_price:
            raise ValueError(
                "Bullish stop must be below entry price"
            )

        reasons.append(
            f"Stop placed below bullish entry at invalidation reference "
            f"{stop_price}"
        )

    stop_distance = abs(request.entry_price - stop_price)

    if request.atr_reference is not None:
        if request.atr_reference <= 0:
            raise ValueError("ATR reference must be greater than zero")

        stop_distance_atr = stop_distance / request.atr_reference

        reasons.append(
            f"Stop distance is {stop_distance_atr:.2f} ATR"
        )

    return StopPlan(
        direction=request.direction,
        entry_price=request.entry_price,
        stop_price=stop_price,
        stop_distance=stop_distance,
        method=method,
        reasons=reasons,
    )
