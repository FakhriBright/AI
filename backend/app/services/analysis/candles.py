from datetime import datetime, timedelta, timezone


TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


def candle_close_time(candle_time: datetime, timeframe: str) -> datetime:
    minutes = TIMEFRAME_MINUTES.get(timeframe)

    if minutes is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    return candle_time + timedelta(minutes=minutes)


def is_candle_closed(
    candle_time: datetime,
    timeframe: str,
    now: datetime | None = None,
) -> bool:
    if now is None:
        now = datetime.now(timezone.utc)

    if candle_time.tzinfo is None:
        candle_time = candle_time.replace(tzinfo=timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return now >= candle_close_time(candle_time, timeframe)


def get_closed_candles(
    candles: list,
    timeframe: str,
    now: datetime | None = None,
) -> list:
    if now is None:
        now = datetime.now(timezone.utc)

    return [
        candle
        for candle in candles
        if is_candle_closed(
            candle.time_utc,
            timeframe,
            now,
        )
    ]
