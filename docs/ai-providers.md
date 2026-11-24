# AI Providers

The backend can call **Groq**, **Google Gemini** or **OpenRouter** for the AI
analysis and the AI Analyst chat. Each user picks the provider and model in
the dashboard under **Settings → AI Provider**. The choice is stored per user
in the database (`ai_provider_settings`), so it survives reloads and does not
affect other users.

The deterministic trading engine (market structure, scenarios, risk, trade
plan) and the ICT/SMC prompt are identical for every provider. Only the model
that writes the narrative changes.

## Architecture

```
analysis routes ──► get_ai_provider_for_user(db, user)     services/ai/factory.py
                         │
                         ├─ no saved settings ──► get_ai_provider()   (AI_PROVIDER, unchanged behavior)
                         │
                         └─ saved settings ──► RoutedAIProvider        services/ai/routing.py
                                                 │  same analyze(context) -> AIResponse contract
                                                 ▼
                                   build_provider(provider, model)    services/ai/registry.py
                                   ├─ GroqAIProvider        groq_provider.py
                                   ├─ GeminiAIProvider      gemini_provider.py
                                   └─ OpenRouterAIProvider  openrouter_provider.py
```

* `AIReasoningService`, the prompt, the pipeline and the `/analysis` response
  format are unchanged. `ai.provider` and `ai.model` in the response are the
  provider/model that **actually** produced the text.
* `ai.raw.provider_routing` records the requested provider/model, which one
  served the answer, whether a fallback was used, and every failed attempt
  (error kind and HTTP status only).
* Settings API (all require login):

  | Method | Path | Purpose |
  |---|---|---|
  | GET | `/ai/settings` | Current selection (or the server default) and which providers have a key |
  | PUT | `/ai/settings` | Save provider, model per provider, Auto Switch, fallback order |
  | GET | `/ai/providers/{provider}/models?refresh=true` | Models usable by the server's key |
  | POST | `/ai/test` | Send a tiny prompt to exactly one provider/model (no fallback) |

## Adding API keys

Keys live only in the backend environment (the root `.env` read by
docker-compose). They are never stored in the database, never returned by the
API (the dashboard only receives `configured: true/false`), and never stored in
the browser.

```env
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_API_KEY=...        # legacy AI_API_KEY is read only if this is empty
GEMINI_MODEL=gemini-3.6-flash
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=...      # e.g. a ":free" model for a free-tier key
AI_PROVIDER=groq          # server default for users who never saved a choice
```

Then recreate the backend container so it picks up the new environment:

```bash
cd ~/AI
docker compose up -d backend
```

A provider without a key is shown as "API key not configured" and cannot be
selected or saved.

## Models

The model dropdown is filled from each provider's model-listing API **using the
server's key**, so it only shows models that key can use:

| Provider | Source | Filtering |
|---|---|---|
| Groq | `GET https://api.groq.com/openai/v1/models` | active chat models (speech, TTS and guard models removed) |
| Gemini | `GET https://generativelanguage.googleapis.com/v1beta/models` | models supporting `generateContent` (embedding/image/live models removed) |
| OpenRouter | `GET /api/v1/key` + `GET /api/v1/models` | text-output models; if the key is free-tier or has no credit left, only free (`$0`) models |

Listings are cached for `AI_MODEL_CACHE_SECONDS` (default 600). Use **Refresh
Models** in the dashboard to bypass the cache.

Optional allowlists narrow the list without code changes:

```env
GROQ_MODELS=openai/gpt-oss-120b,llama-3.3-70b-versatile
GEMINI_MODELS=
OPENROUTER_MODELS=
```

* The allowlist is intersected with the discovered models, so a model the key
  cannot use is never shown.
* If the listing API is temporarily unreachable (timeout, connection error, 5xx,
  429), the dropdown falls back to the models configured in `.env` (the allowlist
  plus the `*_MODEL` default), marked "unverified". You can still select one
  manually, and **Test Connection** verifies it. An invalid key or exhausted
  credit is always reported as an error, never masked by configured models.

`GROQ_MODEL`, `GEMINI_MODEL` and `OPENROUTER_MODEL` are the defaults used when
a user has not chosen a model for that provider. OpenRouter has no built-in
default, so pick a model in the dashboard.

The model is validated against the listing when you save.

### Reasoning tokens

Reasoning models count their hidden thinking against the output-token limit:
Gemini 3.x, Groq's `openai/gpt-oss-*`, and many OpenRouter models. With only the
`max_tokens` requested by the reasoning service (1,200–2,200), thinking can use
the whole budget, which leaves the analysis truncated (Gemini
`finish_reason=MAX_TOKENS`) or completely empty (Groq `gpt-oss-20b`
`finish_reason=length`, 0 characters).

All three providers therefore add `AI_REASONING_TOKENS` (default 6144) on top
of the requested `max_tokens`. This is a ceiling only: providers bill the tokens
actually generated. The prompt and the requested `max_tokens` are unchanged.
The pinned `google-genai==1.2.0` SDK has no thinking-budget setting, so this
allowance is the available control there. `ai.raw.finish_reason` is
`stop`/`STOP` when the answer is complete.

## Choosing a provider in the dashboard

1. Open **Settings**. The **AI PROVIDER** card shows the active provider and
   model, and whether they come from your saved settings or the server default.
2. Pick an **AI Provider**. The **AI Model** list reloads for that provider.
3. Pick a model and press **Test Connection**. This sends a one-line prompt
   and reports Connected, an invalid key, quota exhausted, rate limit, and so on.
4. Press **Save Settings**. The next analysis refresh and chat message use the
   new selection.

## Auto Switch

When **Auto Switch** is off (default), only the selected provider is called.
If it fails, the error is shown, and the app never moves to another provider
silently.

When it is on:

* The selected provider is tried first, then the enabled providers in the
  **Fallback order** (each with the model chosen for it in the dashboard, or its
  `*_MODEL` default).
* It falls back only for failures another provider may not have: HTTP 429 (rate
  limit or quota), 402 (insufficient credits), 5xx, timeouts and connection errors.
* It never falls back for request or configuration errors: 400, 401/403
  (invalid key), 404 (unknown model), 413 (request too large) or a missing key on
  the selected provider. These are raised as before, and 413 still triggers the
  existing smaller-prompt retry.
* At most `AI_FALLBACK_MAX_ATTEMPTS` provider calls per request (default 3).
  Each provider is tried once.
* A provider that returned 429 or a quota error is skipped for
  `AI_PROVIDER_COOLDOWN_SECONDS` (default 60). This stops the 30-second
  dashboard refresh from repeatedly hitting a provider that is out of quota.
* The analysis cache still applies, so an unchanged market context is not sent
  again.
* The dashboard's AI panel shows `· FALLBACK` when another provider answered,
  and the backend logs `AI_FALLBACK requested=... served_by=...`.

## Tests

```bash
cd ~/AI
docker compose run --rm --no-deps -v "$PWD/backend:/app" -w /app backend \
    python test_ai_provider_selector.py
```
