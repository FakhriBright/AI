"""Gold-style daily break must not break XAUUSD analysis; real outages still do."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as C

import pytest

from app.services.analysis.candles import MarketDataInvalid, validate_candle_series


def _series(gap_min: int, weekday_start=datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc)):
    cs = [C(time_utc=weekday_start + timedelta(minutes=i)) for i in range(240)]
    resume = cs[-1].time_utc + timedelta(minutes=gap_min)
    cs += [C(time_utc=resume + timedelta(minutes=i)) for i in range(60)]
    return cs, cs[-1].time_utc + timedelta(minutes=1)


def test_m1_daily_break_60min_is_accepted():
    cs, now = _series(61)  # Wednesday, 21:59 -> 23:00
    validate_candle_series(cs, "M1", now=now)


def test_m1_outage_longer_than_daily_break_still_rejected():
    cs, now = _series(121)  # 2h hole is a data problem, not a daily break
    with pytest.raises(MarketDataInvalid, match="Abnormal gap"):
        validate_candle_series(cs, "M1", now=now)


def test_m5_three_hour_hole_still_rejected():
    cs, now = _series(180)
    with pytest.raises(MarketDataInvalid):
        validate_candle_series(cs, "M5", now=now)


def test_error_detail_is_readable():
    from app.services.analysis.errors import market_data_error_detail as _market_data_error_detail

    assert "Data market tidak valid" in _market_data_error_detail(MarketDataInvalid("Abnormal gap"))
    assert _market_data_error_detail(RuntimeError("x")) is None
