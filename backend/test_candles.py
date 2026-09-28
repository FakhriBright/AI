from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.analysis.candles import (
    candle_close_time,
    is_candle_closed,
    validate_candle_series,
    MarketDataInvalid,
)


tests = [
    ("M5", "2026-09-17T09:15:00+00:00", "2026-09-17T09:19:59+00:00"),
    ("M5", "2026-09-17T09:15:00+00:00", "2026-09-17T09:20:00+00:00"),
    ("M15", "2026-09-17T09:00:00+00:00", "2026-09-17T09:14:59+00:00"),
    ("M15", "2026-09-17T09:00:00+00:00", "2026-09-17T09:15:00+00:00"),
]

for timeframe, candle_text, now_text in tests:
    candle_time = datetime.fromisoformat(candle_text)
    now = datetime.fromisoformat(now_text)

    close_time = candle_close_time(candle_time, timeframe)
    closed = is_candle_closed(candle_time, timeframe, now)

    print(
        f"{timeframe} | "
        f"candle={candle_time} | "
        f"closes={close_time} | "
        f"now={now} | "
        f"closed={closed}"
    )


# --- Weekend & Intra-session Gap Validation Unit Tests ---
def test_weekend_gap_allowed():
    # Simulate series spanning Friday 20:55 UTC to Sunday 21:05 UTC (user scenario)
    t_base = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)  # Friday
    candles = []
    for i in range(12):
        candles.append(SimpleNamespace(time_utc=t_base + timedelta(minutes=5 * i), close=1.0850))

    # Add Sunday open candle (gap of 2890 minutes across weekend)
    t_sunday = datetime(2026, 9, 27, 21, 5, tzinfo=timezone.utc)
    candles.append(SimpleNamespace(time_utc=t_sunday, close=1.0855))

    now = t_sunday + timedelta(minutes=5)
    # Should not raise exception
    validate_candle_series(candles, "M5", now=now)
    print("test_weekend_gap_allowed: PASS")


def test_abnormal_intrasession_gap_rejected():
    # Simulate series on Tuesday with 3-hour missing gap
    t_tuesday = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)  # Tuesday
    candles = []
    for i in range(12):
        candles.append(SimpleNamespace(time_utc=t_tuesday + timedelta(minutes=5 * i), close=1.0850))

    # Add candle 3 hours later (180 min gap on a Tuesday)
    candles.append(SimpleNamespace(time_utc=t_tuesday + timedelta(minutes=5 * 11 + 180), close=1.0860))
    now = candles[-1].time_utc + timedelta(minutes=5)

    try:
        validate_candle_series(candles, "M5", now=now)
        assert False, "Should have raised MarketDataInvalid for intra-session gap"
    except MarketDataInvalid as exc:
        assert "Abnormal gap detected" in str(exc)
        print("test_abnormal_intrasession_gap_rejected: PASS")


test_weekend_gap_allowed()
test_abnormal_intrasession_gap_rejected()
