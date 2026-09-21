from dataclasses import dataclass


@dataclass
class RiskRequest:
    symbol: str
    account_equity: float
    risk_percent: float
    entry_price: float
    stop_price: float


@dataclass
class RiskPlan:
    symbol: str
    account_equity: float
    risk_percent: float
    risk_amount: float

    entry_price: float
    stop_price: float
    stop_distance: float

    tick_size: float
    tick_value: float

    raw_volume: float
    volume: float

    estimated_loss: float


def _normalize_volume(
    volume: float,
    volume_min: float,
    volume_max: float,
    volume_step: float,
) -> float:
    if volume_step <= 0:
        return volume

    volume = min(volume, volume_max)
    volume = max(volume, volume_min)

    steps = int((volume / volume_step) + 1e-9)
    normalized = steps * volume_step

    if normalized < volume_min:
        normalized = volume_min

    return round(normalized, 8)


def calculate_risk(
    request: RiskRequest,
    tick_size: float,
    tick_value: float,
    volume_min: float,
    volume_max: float,
    volume_step: float,
) -> RiskPlan:

    if request.account_equity <= 0:
        raise ValueError("account_equity must be greater than 0")

    if request.risk_percent <= 0:
        raise ValueError("risk_percent must be greater than 0")

    if request.entry_price <= 0 or request.stop_price <= 0:
        raise ValueError("entry_price and stop_price must be greater than 0")

    if tick_size <= 0:
        raise ValueError("tick_size must be greater than 0")

    if tick_value <= 0:
        raise ValueError("tick_value must be greater than 0")

    stop_distance = abs(request.entry_price - request.stop_price)

    if stop_distance <= 0:
        raise ValueError("entry_price and stop_price cannot be equal")

    risk_amount = request.account_equity * (
        request.risk_percent / 100
    )

    risk_per_lot = (
        stop_distance / tick_size
    ) * tick_value

    raw_volume = risk_amount / risk_per_lot

    volume = _normalize_volume(
        raw_volume,
        volume_min,
        volume_max,
        volume_step,
    )

    estimated_loss = (
        stop_distance / tick_size
    ) * tick_value * volume

    if estimated_loss > risk_amount + 1e-9:
        raise ValueError(
            "Minimum broker volume would exceed the requested risk limit"
        )

    return RiskPlan(
        symbol=request.symbol,
        account_equity=request.account_equity,
        risk_percent=request.risk_percent,
        risk_amount=risk_amount,
        entry_price=request.entry_price,
        stop_price=request.stop_price,
        stop_distance=stop_distance,
        tick_size=tick_size,
        tick_value=tick_value,
        raw_volume=raw_volume,
        volume=volume,
        estimated_loss=estimated_loss,
    )
