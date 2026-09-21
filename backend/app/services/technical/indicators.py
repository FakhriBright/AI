import numpy as np


def ema(values: list[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None] * len(values)

    result = [None] * len(values)

    multiplier = 2 / (period + 1)

    first_ema = sum(values[:period]) / period
    result[period - 1] = first_ema

    for i in range(period, len(values)):
        result[i] = (
            (values[i] - result[i - 1]) * multiplier
            + result[i - 1]
        )

    return result


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    if len(values) < period + 1:
        return [None] * len(values)

    result = [None] * len(values)

    changes = np.diff(values)

    gains = np.maximum(changes, 0)
    losses = np.maximum(-changes, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(values)):
        gain = gains[i - 1]
        loss = losses[i - 1]

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))

    return result


def macd(
    values: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
):
    fast = ema(values, fast_period)
    slow = ema(values, slow_period)

    macd_line = [None] * len(values)

    for i in range(len(values)):
        if fast[i] is not None and slow[i] is not None:
            macd_line[i] = fast[i] - slow[i]

    valid_macd = [
        value for value in macd_line if value is not None
    ]

    signal_values = ema(valid_macd, signal_period)

    signal_line = [None] * len(values)

    start = len(values) - len(signal_values)

    for i, value in enumerate(signal_values):
        if value is not None:
            signal_line[start + i] = value

    histogram = [None] * len(values)

    for i in range(len(values)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]

    return macd_line, signal_line, histogram


def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:

    if len(highs) != len(lows) or len(highs) != len(closes):
        raise ValueError("OHLC arrays must have the same length")

    if len(closes) < period + 1:
        return [None] * len(closes)

    true_ranges = [None] * len(closes)

    for i in range(1, len(closes)):
        true_ranges[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    result = [None] * len(closes)

    first_atr = np.mean(
        [x for x in true_ranges[1:period + 1] if x is not None]
    )

    result[period] = first_atr

    for i in range(period + 1, len(closes)):
        result[i] = (
            (result[i - 1] * (period - 1))
            + true_ranges[i]
        ) / period

    return result
