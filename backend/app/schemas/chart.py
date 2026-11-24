import math
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

OverlayKind = Literal["hline", "zone", "trendline", "arrow", "marker", "label", "position"]
OverlayLayer = Literal[
    "structure", "fvg", "order_blocks", "liquidity", "trendline", "sr", "premium_discount", "trade_plan",
]
OverlayStatus = Literal[
    "active", "confirmed", "candidate", "potential", "waiting",
    "invalidated", "mitigated", "taken", "broken", "expired",
]
# Semantic colour tokens; the frontend maps them to theme colours.
OverlayColor = Literal["bullish", "bearish", "neutral", "info", "warning", "entry", "stop", "target"]
OverlayTimeframe = Literal["M1", "M5", "M15", "M30", "H1", "H4", "D1", "MTF"]


class OverlayPoint(BaseModel):
    time: str | None = None
    price: float


class ChartOverlay(BaseModel):
    """One drawable object. Every price must come from engine/market data."""

    id: str = Field(min_length=1, max_length=200)
    symbol: str = Field(min_length=1, max_length=32)
    timeframe: OverlayTimeframe
    layer: OverlayLayer
    kind: OverlayKind
    name: str = Field(max_length=120)
    color: OverlayColor
    status: OverlayStatus = "active"
    source: str = Field(max_length=120)
    created_at: str | None = None

    price: float | None = None
    price_low: float | None = None
    price_high: float | None = None
    time_start: str | None = None
    time_end: str | None = None
    points: list[OverlayPoint] | None = None
    extend: bool | None = None
    position: Literal["above", "below"] | None = None
    shape: Literal["circle", "triangle"] | None = None

    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rr: float | None = None
    direction: str | None = None

    meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_geometry(self) -> "ChartOverlay":
        prices = [self.price, self.price_low, self.price_high, self.entry, self.stop, self.target]
        prices += [p.price for p in self.points or []]
        if any(p is not None and (not math.isfinite(p) or p <= 0) for p in prices):
            raise ValueError("prices must be finite and positive")

        if self.kind in ("hline", "marker", "label") and self.price is None:
            raise ValueError(f"{self.kind} needs price")
        if self.kind == "zone":
            if self.price_low is None or self.price_high is None or self.price_low >= self.price_high:
                raise ValueError("zone needs price_low < price_high")
        if self.kind in ("trendline", "arrow") and len(self.points or []) != 2:
            raise ValueError(f"{self.kind} needs exactly 2 points")
        if self.kind == "position" and (self.entry is None or self.stop is None):
            raise ValueError("position needs entry and stop")
        return self


class ChartCommandOperation(BaseModel):
    op: Literal["create", "update", "highlight", "clear"]
    ids: list[str] = Field(default_factory=list)
    overlays: list[ChartOverlay] = Field(default_factory=list)
    scope: Literal["ai", "all"] | None = None
