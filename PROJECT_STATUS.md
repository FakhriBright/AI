# PROJECT STATUS — AI Trading Analysis Platform

Last updated: Phase 1 (Architecture) — no engine code written yet.

## Current State

Greenfield project. No prior repository existed before this planning phase.
Nothing is implemented; this document and the accompanying architecture/config
skeleton are the first artifacts.

## Target Architecture

```
MARKET DATA → VALIDATION → TECHNICAL ENGINE → FUNDAMENTAL ENGINE
→ RISK ENGINE → LLM ANALYST → TRADE PLAN → DASHBOARD
```

Decision-support only. No auto-trading. Execution stays manual, via MT5, by the user.
See `docs/ARCHITECTURE.md` for the full breakdown.

## Decisions Locked So Far

| # | Decision | Choice |
|---|---|---|
| 1 | Market data source | Hybrid: MT5/broker feed is the data source of record. TradingView is visualization-only, not a data pipeline. |
| 2 | AI provider | Provider-agnostic `AIProvider` abstraction. Starting cloud provider still open (see Open Decisions) — comparison provided, not yet chosen by user. |
| 3 | Hosting | Local-first dev (Windows + Docker Compose). Production (Debian VPS + Nginx + HTTPS) deferred to Phase 10, but architecture must not assume localhost. |
| 4 | Dev MT5 bridge | Standalone native Windows Python process (official `MetaTrader5` package) exposing HTTP/WebSocket API. Dockerized backend never imports `MetaTrader5` directly — only talks to the bridge through `MarketDataProvider` → `MT5BridgeProvider`. |
| 5 | User/auth model | Single user now, schema and auth boundary shaped for clean multi-user/RBAC later. No `/register` endpoint; single user seeded via `scripts/create_user.py`. JWT-based auth behind a `get_current_user()` boundary. |

## Completed

- [x] Requirement discovery (PRD reviewed)
- [x] Repository inspected (confirmed empty/greenfield)
- [x] Market data source decision
- [x] Dev/prod MT5 bridge architecture investigated and dev-phase shape decided
- [x] AI provider landscape compared (no provider chosen yet)
- [x] Service boundaries, MT5 Bridge API contract, DB boundary list, config strategy drafted
- [x] User/auth model decided; ownership relationships defined
- [x] Backend skeleton scaffolded: FastAPI app, config, SQLAlchemy models
      (`users`, `risk_settings`, `instruments`, `strategy_profiles`,
      `analysis_sessions`, `analysis_results`, `trade_plans`), Alembic wiring,
      JWT auth (login only, no public registration), `MarketDataProvider`
      abstraction + working `MT5BridgeProvider` client against the agreed
      API contract, `/health` and `/health/market-data` endpoints, seed
      script for the single user, Dockerfile, requirements.txt

## In Progress

- Nothing actively in flight. Backend skeleton compiles; not yet run against
  a live database or a live MT5 bridge (no migration has been generated or
  applied yet — `migrations/versions/` is empty).

## Missing (not started)

- First Alembic migration (autogenerate against the models above) and
  actually running the stack end-to-end
- Data validation layer (OHLC integrity, gap/staleness checks) sitting in
  front of `MarketDataProvider` output before it reaches any engine
- The MT5 Bridge process itself (Windows-side: MT5 terminal + Python +
  HTTP/WS server implementing the contract) — only the backend's *client*
  for it exists so far
- Technical engine (indicators, structure, S/R)
- Fundamental/news engine
- Risk engine
- AI reasoning service + concrete `AIProvider` implementation
- Frontend (Vue) — anything at all
- Analysis history / evaluation framework
- Deployment (Nginx, HTTPS, prod Docker overlay)
- Tests of any kind

## Blocked

- **Order Block / FVG / liquidity/SMC definitions** (PRD §7) — cannot be implemented until the user chooses an explicit algorithmic definition. Not needed until Phase 3 (Technical Engine), so it does not block Phase 1–2.
- **Economic calendar / news provider** (PRD §8–9) — not chosen yet. Not needed until Phase 4 (Fundamental Engine), does not block current phase.
- **Confidence score definition** (PRD §11) — explicitly must not be a "fake number." Deferred until the Trade Plan / AI Reasoning phases (6–7).

None of the above block Phase 1–2 work.

## Open Decisions

See the end of the accompanying chat response for the one decision being asked now
(user/auth model). Additional decisions listed above under "Blocked" will be asked
again, one at a time, when their owning phase starts.
