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


class MarketDataInvalid(ValueError):
    """Raised when market data fails validation (stale candles or abnormal gaps)."""
    pass


# Gold/index CFDs pause for about an hour every weekday (broker maintenance).
# Forex pairs (EURUSD...) trade 24h and never show this gap.
DAILY_BREAK_MAX_GAP_SEC = 90 * 60

# Holiday early closes (e.g. US Thanksgiving: gold closed ~19:30 -> 23:00 UTC)
# are longer than the daily break. They are accepted only when trading resumes
# at the symbol's REGULAR reopen time, learned from its own history; a data
# outage resumes at an arbitrary time and is still rejected.
SESSION_CLOSURE_MAX_GAP_SEC = 24 * 3600
REOPEN_TOLERANCE_SEC = 5 * 60
REOPEN_MIN_OCCURRENCES = 2


def _minute_of_day(t: datetime) -> int:
    return t.hour * 60 + t.minute


def learn_session_reopen_minutes(candles: list, timeframe: str) -> set[int]:
    """UTC minutes-of-day at which the symbol regularly resumes trading after a
    break (a gap longer than one bar), seen at least REOPEN_MIN_OCCURRENCES
    times in this series. Empty for instruments that trade continuously."""
    step = TIMEFRAME_MINUTES.get(timeframe, 60) * 60
    seen: dict[int, int] = {}
    for previous, current in zip(candles, candles[1:]):
        t1, t2 = previous.time_utc, current.time_utc
        if t1.tzinfo is None:
            t1 = t1.replace(tzinfo=timezone.utc)
        if t2.tzinfo is None:
            t2 = t2.replace(tzinfo=timezone.utc)
        if (t2 - t1).total_seconds() > step:
            minute = _minute_of_day(t2)
            seen[minute] = seen.get(minute, 0) + 1
    return {minute for minute, count in seen.items() if count >= REOPEN_MIN_OCCURRENCES}


def _resumes_at_reopen(t2: datetime, reopen_minutes: set[int]) -> bool:
    minute = _minute_of_day(t2)
    return any(0 <= (minute - r) % 1440 <= REOPEN_TOLERANCE_SEC // 60 for r in reopen_minutes)


def is_market_closure_gap(
    t1: datetime,
    t2: datetime,
    session_reopen_minutes: set[int] | None = None,
) -> bool:
    """
    Returns True if the gap between t1 and t2 represents a normal market closure:
    - the weekend closure, or
    - the short (<= 90 min) weekday daily break of metals/indices, or
    - a longer weekday session closure (holiday early close, < 24 h) that
      resumes exactly at the symbol's regular reopen time (learned from its
      own history and passed in as `session_reopen_minutes`).

    Other intra-session gaps are still rejected as abnormal.
    """
    gap_sec = (t2 - t1).total_seconds()
    if gap_sec <= 0 or gap_sec > (72 * 3600):
        return False

    # Daily maintenance break: short gap that starts on a weekday (Mon-Fri).
    if gap_sec <= DAILY_BREAK_MAX_GAP_SEC and t1.weekday() <= 4:
        return True

    w1 = t1.weekday()
    w2 = t2.weekday()

    # Weekend gap: Friday/Saturday -> Sunday/Monday.
    if w1 in (3, 4, 5) and w2 in (6, 0):
        return True

    # Session closure (early close) that ends at the regular reopen time.
    if (
        session_reopen_minutes
        and w1 <= 4
        and gap_sec < SESSION_CLOSURE_MAX_GAP_SEC
        and _resumes_at_reopen(t2, session_reopen_minutes)
    ):
        return True

    return False


def validate_candle_series(
    candles: list,
    timeframe: str,
    max_gap_multiplier: float = 20.0,
    max_stale_hours: float = 72.0,
    now: datetime | None = None,
    session_reopen_minutes: set[int] | None = None,
) -> None:
    if not candles:
        raise MarketDataInvalid(f"No candles provided for timeframe {timeframe}")

    if len(candles) < 10:
        raise MarketDataInvalid(f"Insufficient candle count ({len(candles)}) for timeframe {timeframe}")

    if now is None:
        now = datetime.now(timezone.utc)

    # 1. Stale candle check: latest candle close time vs current time
    latest_candle = candles[-1]
    latest_time = latest_candle.time_utc
    if latest_time.tzinfo is None:
        latest_time = latest_time.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    close_time = candle_close_time(latest_time, timeframe)
    stale_duration = (now - close_time).total_seconds()
    if stale_duration > (max_stale_hours * 3600):
        raise MarketDataInvalid(
            f"Stale market data for {timeframe}: latest candle close time {close_time.isoformat()} "
            f"is older than {max_stale_hours} hours"
        )

    # 2. Gap check: abnormal gap between consecutive candles (allowing normal weekend & daily closures)
    tf_minutes = TIMEFRAME_MINUTES.get(timeframe, 1)
    expected_delta_sec = tf_minutes * 60
    max_allowed_gap_sec = expected_delta_sec * max_gap_multiplier

    for i in range(1, len(candles)):
        t1 = candles[i - 1].time_utc
        t2 = candles[i].time_utc
        if t1.tzinfo is None:
            t1 = t1.replace(tzinfo=timezone.utc)
        if t2.tzinfo is None:
            t2 = t2.replace(tzinfo=timezone.utc)

        gap_sec = (t2 - t1).total_seconds()
        if gap_sec < 0:
            raise MarketDataInvalid(f"Out of order timestamps in candle series for {timeframe}: {t1} > {t2}")

        if gap_sec > max_allowed_gap_sec:
            if not is_market_closure_gap(t1, t2, session_reopen_minutes):
                raise MarketDataInvalid(
                    f"Abnormal gap detected in {timeframe} candles between {t1.isoformat()} and {t2.isoformat()} ({gap_sec / 60:.1f} min)"
                )


def select_analysis_candles(
    candles: list,
    timeframe: str,
    min_count: int = 200,
    now: datetime | None = None,
) -> list:
    """
    Bars used for deterministic technical analysis / AI reasoning.

    Live UI may still consume the forming candle separately (latest_candle,
    confirmation). Forming OHLC changes on every tick and would otherwise
    retrigger identical reasoning.
    """
    closed = get_closed_candles(
        candles,
        timeframe,
        now=now,
    )

    if len(closed) >= min_count:
        return closed

    return list(candles)
