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


# ---------------------------------------------------------------------------
# Holiday early close (2026-11-26 US Thanksgiving: XAUUSDm M1 19:29 -> 23:01,
# M5 19:25 -> 23:00). Regression: this aborted the whole analysis with 503.
# ---------------------------------------------------------------------------
from app.services.analysis.candles import learn_session_reopen_minutes  # noqa: E402

UTC = timezone.utc
GOLD_REOPEN = {23 * 60}  # learned from H1 history of the real symbol (23:00 UTC)


def _gold_session(t: datetime) -> bool:
    """Gold-like calendar: daily break 22:00-23:00, weekend Fri 22:00 -> Sun 23:00,
    Thanksgiving early close 2026-11-26 19:30 -> 23:00 (all UTC)."""
    wd, minute = t.weekday(), t.hour * 60 + t.minute
    if wd == 5 or (wd == 4 and minute >= 22 * 60) or (wd == 6 and minute < 23 * 60):
        return False
    if 22 * 60 <= minute < 23 * 60:
        return False
    if t.date() == datetime(2026, 11, 26).date() and 19 * 60 + 30 <= minute < 23 * 60:
        return False
    return True


def _gold_series(tf_min: int, end: datetime, count: int = 300):
    out, t = [], end
    while len(out) < count:
        if _gold_session(t):
            out.append(t)
        t -= timedelta(minutes=tf_min)
    return [C(time_utc=x) for x in reversed(out)]


def test_reopen_time_is_learned_from_h1_history():
    h1 = _gold_series(60, datetime(2026, 11, 27, 1, 0, tzinfo=UTC))
    assert learn_session_reopen_minutes(h1, "H1") == GOLD_REOPEN
    fx = [C(time_utc=datetime(2026, 11, 20, tzinfo=UTC) + timedelta(hours=i)) for i in range(150)]
    assert learn_session_reopen_minutes(fx, "H1") == set()  # 24h market: nothing to learn


def test_thanksgiving_early_close_accepted_when_it_resumes_at_regular_reopen():
    for tf in (1, 5):
        cs = _gold_series(tf, datetime(2026, 11, 27, 1, 45, tzinfo=UTC))
        now = cs[-1].time_utc + timedelta(minutes=tf)
        with pytest.raises(MarketDataInvalid, match="Abnormal gap"):
            validate_candle_series(cs, f"M{tf}", now=now)  # without session knowledge: old behaviour
        validate_candle_series(cs, f"M{tf}", now=now, session_reopen_minutes=GOLD_REOPEN)


def test_outage_not_ending_at_reopen_is_still_rejected():
    cs, now = _series(150)  # Wednesday 21:59 -> 00:29: not the 23:00 reopen
    with pytest.raises(MarketDataInvalid, match="Abnormal gap"):
        validate_candle_series(cs, "M1", now=now, session_reopen_minutes=GOLD_REOPEN)
    start = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)  # Tuesday
    cs = [C(time_utc=start + timedelta(minutes=i)) for i in range(100)]
    cs += [C(time_utc=datetime(2026, 10, 7, 23, 0, tzinfo=UTC) + timedelta(minutes=i)) for i in range(50)]
    with pytest.raises(MarketDataInvalid):  # > 24 h hole, even though it ends at 23:00
        validate_candle_series(cs, "M1", now=cs[-1].time_utc + timedelta(minutes=1), session_reopen_minutes=GOLD_REOPEN)


def test_builder_learns_reopen_and_builds_snapshot_across_holiday_gap():
    import asyncio
    import math

    from app.services.analysis import builder
    from app.services.market_data.base import Candle

    end = datetime(2026, 11, 27, 1, 45, tzinfo=UTC)
    minutes = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}

    class FakeBridge:
        async def get_candles(self, symbol, timeframe, count):
            tf = minutes[timeframe]
            last = end - timedelta(minutes=(end.hour * 60 + end.minute) % tf)  # bar-aligned
            rows = []
            for i, c in enumerate(_gold_series(tf, last, count)):
                mid = 3500 + 20 * math.sin(i / 7) + i * 0.05
                rows.append(Candle(time_utc=c.time_utc, open=mid - 0.3, high=mid + 1.0, low=mid - 1.0, close=mid + 0.3, tick_volume=100))
            return rows

    seen = {}
    real_validate = builder.validate_candle_series

    def recording_validate(candles, timeframe, **kwargs):
        seen[timeframe] = kwargs.get("session_reopen_minutes")
        return real_validate(candles, timeframe, now=candles[-1].time_utc + timedelta(minutes=minutes[timeframe]), **kwargs)

    builder.validate_candle_series = recording_validate
    try:
        snapshot = asyncio.run(builder.build_analysis_snapshot(provider=FakeBridge(), symbol="XAUUSDm", count=300))
    finally:
        builder.validate_candle_series = real_validate
    assert seen["M1"] == GOLD_REOPEN and seen["M5"] == GOLD_REOPEN
    assert set(snapshot.timeframes) == set(minutes)
