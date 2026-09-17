# Database Boundaries — Phase 1

This defines entity scope and provenance, not final DDL/migrations (that's
Phase 2+ implementation). PostgreSQL, migrations via Alembic.

## Provenance separation (PRD §2, §40)

Every analysis run gets one `analysis_id` (UUID). Everything below hangs off
that id so a user (or an evaluator) can trace: raw data → calculations → AI
prompt/response → trade plan → later outcome.

## Entities

| Entity | Bucket | Key fields (illustrative, not final) |
|---|---|---|
| `users` | — | id (UUID), email (unique), hashed_password, is_active, created_at. No `role` column yet — deliberately omitted, not deferred-and-forgotten; see `docs/auth-architecture.md` for how roles slot in later without a migration that breaks existing rows. |
| `instruments` | reference (not user-owned) | symbol, display_name, category (fx/metal/index/crypto), is_active |
| `strategy_profiles` | reference (not user-owned) | name (scalping/intraday/swing), timeframes[], min_rr, news_sensitivity, holding_period |
| `analysis_sessions` | **user-owned** | id (=analysis_id, UUID), **user_id (FK → users.id, NOT NULL)**, instrument_id, strategy_profile_id, requested_at, status |
| `market_data` / `candles` | **OBSERVED** | analysis_id (nullable, candles are also cached independent of a session), symbol, timeframe, time_utc, OHLCV, source (`mt5_bridge`), fetched_at |
| `indicators` | **CALCULATED** | analysis_id, symbol, timeframe, indicator_name, value(s), computed_from_candle_range |
| `market_structures` | **CALCULATED** | analysis_id, symbol, timeframe, structure_type (BOS/CHoCH/swing/etc.), price, time |
| `support_resistance` | **CALCULATED** | analysis_id, symbol, timeframe, level_type, price, basis (swing/prev-day/etc.) |
| `economic_events` | **OBSERVED** (external) | event_name, country, currency, actual, forecast, previous, importance, timestamp |
| `news` | **OBSERVED** (external) | headline, source, timestamp, related_instrument, importance |
| `risk_settings` | **user-owned** | id, **user_id (FK → users.id, NOT NULL, unique)**, account_balance, risk_percent, max_exposure, min_rr |
| `analysis_results` | **AI INTERPRETATION** | id, analysis_id (FK → analysis_sessions.id), raw_llm_response, validated_schema_output, validation_status (ok/repaired/failed), ai_provider, model_name |
| `trade_plans` | **user-owned** (via session) | id, analysis_id (FK → analysis_sessions.id, NOT NULL), bias, entry, stop_loss, tp1-3, rr, invalidation_condition, status (WAITING/TRIGGERED/.../CLOSED), no_trade_reason (nullable) |

### Ownership rule

`trade_plans` doesn't carry its own `user_id` — it inherits ownership through
`analysis_sessions.user_id`. This is deliberate: ownership has exactly one
source of truth per object graph, not duplicated foreign keys that can drift.
Any future query for "this user's trade plans" joins through
`analysis_sessions`, never reads a denormalized `user_id` off `trade_plans`.

`market_data`/`candles`, `indicators`, `market_structures`, and
`support_resistance` remain **not** user-owned — they're keyed by
symbol/timeframe/time and shared across all analyses (and, later, all users),
since raw market data and its calculated derivatives aren't a per-user
concept. Only the *session that requested* an analysis, and what it produced
as a trade plan, are owned.

## Explicit non-goals for Phase 1

- No table for Order Block/FVG/liquidity constructs until their algorithmic
  definition is chosen (PRD §7) — adding a table now would imply a definition
  that hasn't been approved.
- No `positions`/`orders` table — this platform never places orders (PRD §18).
- No backtesting result tables yet — Phase 9/23 concern, schema will be
  informed by what `trade_plans` + real outcomes actually look like once
  populated.

## Open item affecting `users`

The `users` table shape (single implicit user vs. multiple users with roles)
depends on the auth-model decision — see the question at the end of this
response. Everything else in this list is unaffected by that decision.
