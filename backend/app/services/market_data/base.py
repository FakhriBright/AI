"""
The abstraction the rest of the backend depends on (PRD §16). Nothing outside
this module — and its concrete implementations — knows whether data came from
MT5, a broker API, or anything else.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class Candle(BaseModel):
    time_utc: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int | None = None


class SymbolInfo(BaseModel):
    symbol: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_step: float
    volume_max: float
    currency_base: str
    currency_profit: str
    spread_current: int | None = None


class Tick(BaseModel):
    symbol: str
    time_utc: datetime
    bid: float
    ask: float


class AccountInfo(BaseModel):
    login: int
    server: str
    currency: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int


class BridgeHealth(BaseModel):
    bridge_status: str  # ok / degraded / down
    data_source_connected: bool
    server_time_utc: datetime | None = None


class MarketDataUnavailable(Exception):
    """
    Raised for every failure mode instead of returning fabricated or
    partial data (PRD §2, §38). Callers must handle this and produce an
    explicit "DATA UNAVAILABLE" outcome — never fall back to a guess.
    """

    def __init__(self, reason: str, retryable: bool = False):
        self.reason = reason
        self.retryable = retryable
        super().__init__(reason)


class MarketDataProvider(ABC):
    """Every concrete provider (MT5 bridge, future broker API, ...) implements this."""

    @abstractmethod
    async def health(self) -> BridgeHealth: ...

    @abstractmethod
    async def list_symbols(self) -> list[str]: ...

    @abstractmethod
    async def symbol_info(self, symbol: str) -> SymbolInfo: ...

    @abstractmethod
    async def account_info(self) -> AccountInfo: ...

    @abstractmethod
    async def list_timeframes(self) -> list[str]: ...

    @abstractmethod
    async def get_candles(
        self, symbol: str, timeframe: str, count: int
    ) -> list[Candle]: ...

    @abstractmethod
    async def get_tick(self, symbol: str) -> Tick: ...
