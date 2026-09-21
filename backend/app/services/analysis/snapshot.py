from dataclasses import dataclass, field
from typing import Literal


Timeframe = Literal[
    "M1",
    "M5",
    "M15",
    "M30",
    "H1",
    "H4",
    "D1",
]


@dataclass
class IndicatorSnapshot:
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None

    rsi14: float | None = None

    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None

    atr14: float | None = None


@dataclass
class SwingSnapshot:
    time_utc: object
    type: str
    label: str | None
    price: float


@dataclass
class StructureSnapshot:
    direction: str
    recent_swings: list[SwingSnapshot] = field(default_factory=list)


@dataclass
class TrendSnapshot:
    direction: str
    ema_alignment: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class TimeframeSnapshot:
    timeframe: Timeframe
    candle_time_utc: object
    price: float

    indicators: IndicatorSnapshot
    structure: StructureSnapshot
    trend: TrendSnapshot


@dataclass
class AnalysisSnapshot:
    symbol: str
    generated_at_utc: object

    timeframes: dict[Timeframe, TimeframeSnapshot] = field(
        default_factory=dict
    )
