from dataclasses import dataclass, field

from app.services.analysis.snapshot import AnalysisSnapshot, TimeframeSnapshot


@dataclass
class TimeframeContext:
    timeframe: str
    price: float
    trend: str
    structure: str
    ema_alignment: str
    ema20: float | None
    ema50: float | None
    ema200: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    atr14: float | None
    reasons: list[str] = field(default_factory=list)
    swings: list = field(default_factory=list)


@dataclass
class MultiTimeframeContext:
    symbol: str
    generated_at_utc: object
    timeframes: dict[str, TimeframeContext] = field(default_factory=dict)


def _build_timeframe_context(
    snapshot: TimeframeSnapshot,
) -> TimeframeContext:
    indicators = snapshot.indicators
    trend = snapshot.trend

    return TimeframeContext(
    timeframe=snapshot.timeframe,
    price=snapshot.price,
    trend=trend.direction,
    structure=snapshot.structure.direction,
    ema_alignment=trend.ema_alignment,
    ema20=indicators.ema20,
    ema50=indicators.ema50,
    ema200=indicators.ema200,
    rsi14=indicators.rsi14,
    macd=indicators.macd,
    macd_signal=indicators.macd_signal,
    macd_hist=indicators.macd_hist,
    atr14=indicators.atr14,
    reasons=list(trend.reasons),
    swings=list(snapshot.structure.recent_swings),
)


def build_multi_timeframe_context(
    snapshot: AnalysisSnapshot,
) -> MultiTimeframeContext:
    context = MultiTimeframeContext(
        symbol=snapshot.symbol,
        generated_at_utc=snapshot.generated_at_utc,
    )

    for timeframe, timeframe_snapshot in snapshot.timeframes.items():
        context.timeframes[timeframe] = _build_timeframe_context(
            timeframe_snapshot
        )

    return context


def print_multi_timeframe_context(
    context: MultiTimeframeContext,
) -> None:
    print("\n=== MULTI-TIMEFRAME CONTEXT ===")
    print(f"SYMBOL: {context.symbol}")
    print(f"GENERATED: {context.generated_at_utc}")

    for timeframe, data in context.timeframes.items():
        print(f"\n--- {timeframe} ---")
        print(f"PRICE         : {data.price}")
        print(f"TREND         : {data.trend}")
        print(f"STRUCTURE     : {data.structure}")
        print(f"EMA ALIGNMENT : {data.ema_alignment}")
        print(f"EMA20         : {data.ema20}")
        print(f"EMA50         : {data.ema50}")
        print(f"EMA200        : {data.ema200}")
        print(f"RSI14         : {data.rsi14}")
        print(f"MACD          : {data.macd}")
        print(f"MACD SIGNAL   : {data.macd_signal}")
        print(f"MACD HIST     : {data.macd_hist}")
        print(f"ATR14         : {data.atr14}")

        if data.reasons:
            print("REASONS:")
            for reason in data.reasons:
                print(f"  - {reason}")
