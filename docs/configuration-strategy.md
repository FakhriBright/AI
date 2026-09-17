# Configuration Strategy — Phase 1

All configuration via environment variables (PRD §29). No secrets committed.
`.env` files are git-ignored; `.env.example` (repo root) documents required
keys with placeholder values.

## Variables by service

**backend**
- `DATABASE_URL` — postgres connection string
- `MARKET_DATA_PROVIDER` — e.g. `mt5_bridge` (selects which `MarketDataProvider` implementation to instantiate)
- `MT5_BRIDGE_URL` — dev: `http://host.docker.internal:8765`; prod: internal URL of whatever bridge Phase 10 lands on
- `AI_PROVIDER` — e.g. `anthropic` / `openai` (selects which `AIProvider` implementation)
- `AI_API_KEY` — provider's API key, injected at runtime, never logged
- `JWT_SECRET` — signing key for auth tokens (only relevant once the auth decision below is made)
- `CORS_ORIGINS` — comma-separated allowed origins (frontend dev URL, later the prod domain)
- `LOG_LEVEL` — `info` in dev, configurable in prod

**mt5-bridge** (native process, its own local `.env` or CLI args — not part of Docker Compose)
- `MT5_TERMINAL_PATH` (if not auto-detected)
- `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` — broker account credentials, never shared with the backend directly
- `BRIDGE_PORT` — defaults to `8765`

**frontend**
- `VITE_API_BASE_URL` — dev: `http://localhost:8000`; prod: the real domain's API path

**postgres**
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`

## Dev vs. prod difference (by design, not by code branching)

Only the *values* differ between `.env.dev` and `.env.prod` — service code
never checks `if environment == "production"`. The one architectural
difference (Nginx/HTTPS/reverse proxy in front of everything) is an additive
Docker Compose overlay file introduced in Phase 10, not a change to existing
services.

## Secrets handling

- `AI_API_KEY`, `MT5_LOGIN`/`MT5_PASSWORD`, `JWT_SECRET`, `POSTGRES_PASSWORD` are secrets.
- None of the above are ever exposed to the frontend bundle or logged at any log level.
- Postgres and the MT5 Bridge are never exposed directly to the internet (PRD §24) — only the backend (behind Nginx in prod) is internet-facing.
