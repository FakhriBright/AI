# Architecture — Phase 1

## 1. System Diagram

```
                         ┌─────────────────────────┐
                         │   Windows Host (dev)     │
                         │                          │
                         │  MT5 Terminal             │
                         │       ▲                   │
                         │       │ local IPC          │
                         │  MT5 Bridge (native)       │
                         │   - Python                 │
                         │   - MetaTrader5 pkg         │
                         │   - HTTP/WS API             │
                         └───────────┬─────────────────┘
                                     │ HTTP/WebSocket
                                     │ (http://host.docker.internal:PORT in dev)
┌────────────────────────────────────┼─────────────────────────────────────┐
│  Docker Compose network            │                                    │
│                                     ▼                                    │
│  ┌───────────┐   ┌──────────────────────────┐   ┌───────────────────┐   │
│  │  Frontend │   │        Backend            │   │     PostgreSQL     │   │
│  │  (Vue)    │◄──┤        FastAPI             ├──►│                    │   │
│  └───────────┘   │  MarketDataProvider        │   └───────────────────┘   │
│                  │    └── MT5BridgeProvider    │                          │
│                  │  TechnicalEngine (Phase 3)  │                          │
│                  │  FundamentalEngine (Phase 4)│                          │
│                  │  RiskEngine (Phase 5)       │                          │
│                  │  AIProvider (Phase 6)       │                          │
│                  │    └── <ChosenProvider>Impl │                          │
│                  └──────────────────────────────┘                        │
└───────────────────────────────────────────────────────────────────────────┘
```

In production, the same Docker Compose network sits behind Nginx + HTTPS on a
Debian VPS; only the `MT5BridgeProvider`'s target URL changes (Phase 10 decides
whether the prod bridge is a Windows VPS or Debian+Wine — deferred, does not
affect anything above the provider boundary).

## 2. Service Boundaries

| Service | Responsibility | Owns |
|---|---|---|
| **mt5-bridge** (native, not containerized) | Talks to the MT5 terminal via the official package. Nothing else. | MT5 session, symbol/candle/tick retrieval, connection health |
| **backend** (FastAPI, Docker) | Everything else: data validation, technical/fundamental/risk engines, AI orchestration, trade plan assembly, persistence, API for frontend | Business logic, schema validation, DB writes, provider abstractions |
| **frontend** (Vue, Docker) | Dashboard, chart rendering, history view | Presentation only — never computes indicators or trade logic itself |
| **postgres** (Docker) | Durable storage | See `docs/database-boundaries.md` |
| **worker** (not yet needed) | Reserved for future async jobs (scheduled analysis runs, news polling) | Introduced only when a concrete need appears — not added speculatively (PRD §27) |

**Hard rule enforced by this boundary:** the `MetaTrader5` package is a dependency of the bridge process only. It never appears in `backend/requirements.txt`. If a future dev accidentally imports it in the backend, that's an architecture violation, not a style nitpick.

## 3. Data Provenance Boundary (PRD §2)

Every payload that reaches the AI layer must be traceable to one of four buckets. This is enforced structurally, not just by convention:

- **OBSERVED** — raw fields from the MT5 Bridge response (OHLC, tick, symbol spec), stored verbatim with their source timestamp.
- **CALCULATED** — anything the Technical/Risk engines derive (EMA, RSI, ATR, S/R, position size). Stored separately, always referencing the OBSERVED candle range that produced it.
- **AI INTERPRETATION** — LLM output, stored as its own record, referencing the OBSERVED + CALCULATED payload that was sent to it (see `analysis_id` traceability, PRD §40).
- **UNAVAILABLE** — explicit marker, never a null silently treated as zero/absent, when the bridge can't supply something.

These four are separate columns/tables, never merged into one blob, so the frontend and any evaluation code can always tell which bucket a number came from.

## 4. Failure Modes the Backend Must Detect (PRD §38–39, this decision's "Important" section)

| Condition | Detection point | Resulting behavior |
|---|---|---|
| Bridge unreachable (connection refused/timeout) | HTTP client to mt5-bridge | `DATA UNAVAILABLE`, logged, no retNo fabricated candle |
| MT5 terminal disconnected (bridge up, terminal down) | Bridge's own `/health` reports `mt5_connected: false` | Same as above |
| Symbol not found/not in Market Watch | Bridge returns `SYMBOL_NOT_FOUND` | Surfaced to user, no default symbol substitution |
| Stale data (last candle older than expected for timeframe) | Backend-side check on returned timestamp vs. now | Flagged as `DATA UNAVAILABLE` / stale, not passed to engines as current |
| Missing candles (gaps in requested range) | Backend-side OHLC integrity check | Logged, gap excluded from calculation range or analysis blocked if critical |
| Malformed response (schema mismatch from bridge) | Pydantic validation on the response | Rejected before reaching any engine, logged as an ingestion error |
| Timeout | HTTP client timeout setting | Same as "bridge unreachable" |

None of these ever produce a fabricated value — they produce an explicit status that propagates up through to the trade plan as `NO TRADE` / `DATA UNAVAILABLE` where relevant (PRD §12).

## 5. What Is Explicitly Deferred

- Concrete `AIProvider` implementation (which cloud provider) — Phase 6.
- Concrete production `MarketDataProvider` (Windows VPS vs. Debian+Wine vs. broker API) — Phase 10.
- Order Block/FVG/liquidity algorithmic definitions — Phase 3, blocked on user input.
- Economic calendar/news provider — Phase 4, blocked on user input.
- Confidence scoring methodology — Phase 6/7.
- Nginx/HTTPS/reverse proxy config — Phase 10.
