from types import SimpleNamespace

from app.services.analysis.levels import _build_supply_demand_zones


def test_supply_demand_uses_closed_evidence_candles_field():
    # A small base candle followed by a strong bullish displacement should
    # produce a demand zone. This regression protects the shared field name.
    candles = []
    for i in range(14):
        if i == 5:
            values = (100.0, 100.2, 99.8, 100.05)
        elif i == 6:
            values = (100.1, 102.0, 100.0, 101.8)
        else:
            values = (100.0, 100.3, 99.7, 100.05)
        candles.append(SimpleNamespace(
            open=values[0], high=values[1], low=values[2], close=values[3]
        ))

    context = SimpleNamespace(timeframes={
        "M15": SimpleNamespace(evidence_candles=candles)
    })
    supply, demand = _build_supply_demand_zones(context)
    assert demand
    assert demand[0].timeframes == ["M15"]
