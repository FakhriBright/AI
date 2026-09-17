# Auth Architecture — Single User Now, Multi-User Ready

## Principle

Auth is a replaceable boundary, same pattern as `MarketDataProvider` and
`AIProvider`: routes and business logic depend on `get_current_user()`, never
on how a token was issued or validated. Swapping the mechanism later (adding
roles, SSO, invitations) changes what's behind that boundary, not its callers.

```
Single User  →  Multi User  →  Roles / Permissions
      \_____________|_____________/
                     |
        get_current_user() -> User
   (everything else in the app only sees this)
```

## What's built now

- **Password handling:** passwords hashed with `passlib[bcrypt]` (or `argon2`
  — either is fine; bcrypt is the more battle-tested default). Never stored
  or logged in plaintext.
- **Session mechanism:** JWT access tokens (short-lived, e.g. 30–60 min) via
  `python-jose`, signed with `JWT_SECRET`. No refresh-token rotation, no
  server-side session store yet — deliberately simple, since a single-user
  tool doesn't need distributed session revocation infrastructure yet.
- **Protected endpoints:** a FastAPI dependency (`get_current_user`) validates
  the bearer token and loads the `User` row. Every route that touches
  user-owned data (`risk_settings`, `analysis_sessions`, `trade_plans`)
  requires this dependency — there is no "trusted internal" bypass.
- **Bootstrapping the single user:** rather than a public `/register` endpoint
  (unnecessary attack surface for a single-user app), the one user account is
  created via a one-off CLI/script (`create_user.py`) or a seed migration.
  `/register` can be added later if multi-user is ever turned on.
- **Transport security:** the app assumes HTTPS termination at Nginx in
  production (PRD §24/§26); tokens are never accepted meaningfully over plain
  HTTP outside local dev.
- **No RBAC yet:** there is no `role` or `permissions` column. Every
  authenticated request is simply "the owner." This is intentionally the
  smallest correct thing, not a placeholder pretending to be RBAC.

## What is explicitly NOT built now (and why that's fine later)

| Deferred | Why it's safe to defer | How it slots in later |
|---|---|---|
| Multiple users | Only one real user exists | `users` table already supports arbitrary rows; nothing assumes `id == 1` |
| Roles/permissions | No second user to differentiate | Add a `role` column + a permission-check dependency layered *on top of* `get_current_user`, without touching engines |
| Invitations | No team concept yet | New table + endpoint, doesn't touch existing ownership FKs |
| Org/tenant model | Out of scope per this decision | Would sit *above* `users`, e.g. `organization_id` added later — deferred until actually needed, not designed speculatively now |
| Refresh token rotation / server-side revocation | Overkill for one user | Swappable inside the same `get_current_user` boundary if the app ever needs to revoke sessions remotely |

## Why this doesn't block or complicate the analysis engine

The technical/fundamental/risk/AI engines never see auth at all — they
operate on an `analysis_session` and its owned data once the API layer has
already resolved `user_id`. Nothing in Phases 3–7 needs to change when auth
evolves from single-user to multi-user to RBAC.
