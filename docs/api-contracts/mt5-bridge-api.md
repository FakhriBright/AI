# MT5 Bridge API Contract (v1)

This is the contract the Dockerized backend's `MT5BridgeProvider` speaks against
the native Windows bridge process. The bridge is treated as an untrusted external
service: every response is schema-validated before use, and every failure mode
maps to an explicit status, never a fabricated value.

Base URL (dev): `http://host.docker.internal:8765` (Docker Desktop's route from
a container to the Windows host). Configured via `MT5_BRIDGE_URL`.

## Design principle

Only the capabilities actually needed now are exposed. New capabilities are added
as new endpoints/fields; existing ones are not repurposed. The backend's
`MarketDataProvider` interface only depends on the shapes below, not on anything
MT5-specific (terminal internals, MQL5 types, etc.) — so a future non-MT5
provider can implement the same interface.

## Endpoints

### `GET /health`

```json
{
  "bridge_status": "ok",
  "mt5_connected": true,
  "terminal_info": {
    "name": "MetaTrader 5",
    "build": 4500,
    "connected_to_broker": true
  },
  "server_time_utc": "2026-09-17T10:15:00Z"
}
```
`bridge_status`: `"ok" | "degraded" | "down"`. `mt5_connected: false` means the
bridge process is alive but the terminal/session is not — backend must treat
this the same as fully unavailable for data purposes.

### `GET /symbols`

Returns the list of symbols currently visible in MT5's Market Watch (not
"every symbol in the world" — only what's actually tradeable/visible for this
account, since that's what the terminal can actually serve data for).

```json
{ "symbols": ["EURUSD", "XAUUSD", "GBPUSD", "US30", "..."] }
```

### `GET /symbols/{symbol}/info`

```json
{
  "symbol": "XAUUSD",
  "digits": 2,
  "point": 0.01,
  "contract_size": 100.0,
  "volume_min": 0.01,
  "volume_step": 0.01,
  "volume_max": 100.0,
  "currency_base": "XAU",
  "currency_profit": "USD",
  "spread_current": 25
}
```
This is what the Risk Engine uses for position sizing — never hardcoded
contract sizes (PRD §10).

### `GET /timeframes`

```json
{ "timeframes": ["M1", "M5", "M15", "H1", "H4", "D1"] }
```
Static per bridge version, but exposed rather than assumed, since MT5 supports
more than this and future config may enable others.

### `GET /candles`

Query params: `symbol`, `timeframe`, `count` (or `from`/`to`).

```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "candles": [
    {
      "time_utc": "2026-09-17T09:00:00Z",
      "open": 1.1723,
      "high": 1.1731,
      "low": 1.1719,
      "close": 1.1728,
      "tick_volume": 1432,
      "spread": 8
    }
  ]
}
```
If fewer candles are available than requested (e.g. new symbol, broker history
limit), the bridge returns what it has plus `"truncated": true` — it never pads
with synthetic candles.

### `GET /tick`

Query param: `symbol`.

```json
{
  "symbol": "EURUSD",
  "time_utc": "2026-09-17T10:14:58Z",
  "bid": 1.1727,
  "ask": 1.1728
}
```

## Error Envelope

Any non-200 response uses:

```json
{
  "error_code": "SYMBOL_NOT_FOUND",
  "message": "XAUUSD is not visible in Market Watch",
  "retryable": false
}
```

Defined `error_code` values (extendable, backend treats unknown codes as
non-retryable `DATA UNAVAILABLE`):

| Code | Meaning | Backend behavior |
|---|---|---|
| `MT5_DISCONNECTED` | Bridge up, terminal/broker session down | `DATA UNAVAILABLE`, retry after backoff |
| `SYMBOL_NOT_FOUND` | Symbol not in Market Watch | Surface to user, no fallback symbol |
| `INSUFFICIENT_HISTORY` | Fewer candles available than the engine's minimum | `DATA UNAVAILABLE` for that timeframe only |
| `TIMEOUT` | Bridge took too long to respond internally | Retryable |
| `INTERNAL_ERROR` | Unhandled bridge-side error | Logged, non-retryable by default |

Network-level failures (connection refused, DNS failure, HTTP timeout from the
backend's own client) are handled by the backend's HTTP layer, not the bridge,
and map to the same `DATA UNAVAILABLE` outcome as `MT5_DISCONNECTED`.
