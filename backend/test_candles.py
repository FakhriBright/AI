from datetime import datetime, timezone

from app.services.analysis.candles import (
    candle_close_time,
    is_candle_closed,
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
