"""
Concrete MarketDataProvider implementation talking to the standalone MT5
Bridge process over HTTP, per docs/api-contracts/mt5-bridge-api.md.

This is the ONLY place in the backend allowed to know about the MT5 bridge's
wire format. It never imports the `MetaTrader5` Python package itself —
that package only exists in the bridge process, on the Windows host.
"""

import httpx

from app.services.market_data.base import (
    BridgeHealth,
    Candle,
    MarketDataProvider,
    MarketDataUnavailable,
    SymbolInfo,
    Tick,
)

# Bridge error_code -> retryable, per the contract doc.
_RETRYABLE_CODES = {"TIMEOUT"}
_NON_RETRYABLE_CODES = {"SYMBOL_NOT_FOUND", "INSUFFICIENT_HISTORY", "MT5_DISCONNECTED"}


class MT5BridgeProvider(MarketDataProvider):
    def __init__(self, base_url: str, timeout_seconds: float = 10.0):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise MarketDataUnavailable(f"Bridge request timed out: {path}", retryable=True) from exc
        except httpx.ConnectError as exc:
            raise MarketDataUnavailable(f"Bridge unreachable: {path}", retryable=True) from exc

        if response.status_code != 200:
            try:
                body = response.json()
                code = body.get("error_code", "INTERNAL_ERROR")
                message = body.get("message", "Unknown bridge error")
            except ValueError:
                code, message = "INTERNAL_ERROR", response.text

            retryable = code in _RETRYABLE_CODES
            raise MarketDataUnavailable(f"{code}: {message}", retryable=retryable)

        try:
            return response.json()
        except ValueError as exc:
            # Malformed response — never partially trust it (PRD §38).
            raise MarketDataUnavailable("Malformed response from bridge", retryable=False) from exc

    async def health(self) -> BridgeHealth:
        data = await self._get("/health")
        return BridgeHealth(
            bridge_status=data["bridge_status"],
            data_source_connected=data["mt5_connected"],
            server_time_utc=data.get("server_time_utc"),
        )

    async def list_symbols(self) -> list[str]:
        data = await self._get("/symbols")
        return data["symbols"]

    async def symbol_info(self, symbol: str) -> SymbolInfo:
        data = await self._get(f"/symbols/{symbol}/info")
        return SymbolInfo(**data)

    async def list_timeframes(self) -> list[str]:
        data = await self._get("/timeframes")
        return data["timeframes"]

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        data = await self._get(
            "/candles", params={"symbol": symbol, "timeframe": timeframe, "count": count}
        )
        candles = [Candle(**c) for c in data["candles"]]

        if data.get("truncated") and len(candles) < count:
            # Not an error by itself — the technical engine (Phase 3) decides
            # whether it has enough history for a given indicator/timeframe.
            # We surface the shortfall rather than silently padding it.
            pass

        return candles

    async def get_tick(self, symbol: str) -> Tick:
        data = await self._get("/tick", params={"symbol": symbol})
        return Tick(**data)

    async def aclose(self) -> None:
        await self._client.aclose()
