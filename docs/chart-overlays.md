# Chart overlays and AI chat-to-chart

The Analysis chart draws market structure and ICT/SMC objects automatically,
and the AI Analyst chat can highlight and annotate them. **No LLM call is made
for drawing.** Objects come from the deterministic engine, and chat commands
are derived from the one chat call that already happens.

## Where the objects come from

`backend/app/services/chart/overlays.py` builds every object from the same
`ai_context` the AI receives. It uses the engine's existing detectors:

| Layer | Objects | Source |
|---|---|---|
| Market Structure | Swing markers (HH/HL/LH/LL), BOS, CHoCH / MSS (candidate) | `technical/structure.py`, `ai/desk.py::structure_break` |
| FVG | Bullish / bearish FVG, fresh (`active`) or `mitigated` | `ai/desk.py::detect_fvg_order_blocks` |
| Order Blocks | Bullish / bearish OB, fresh or mitigated | `ai/desk.py::detect_fvg_order_blocks` |
| Liquidity | BSL/SSL (last swing high/low), BSL/SSL sweep, EQH/EQL | `ai/desk.py::detect_sweep`, engine swings |
| Trendline | Bullish (HL→HL) / bearish (LH→LH), `active` / `broken` | engine swings |
| Support & Resistance | Top 3 per side, with touches and timeframes | `analysis/levels.py` (`key_levels`) |
| Premium & Discount | Premium, Equilibrium, Discount (45/55 % bands) | `ai/desk.py::premium_discount` |
| Trade Plan | Entry/SL/TP/RR box **only** when the entry gate allows it, otherwise WAITING with blockers | `trade_plan`, `ai/desk.py::build_entry_gate` |

Notes:

* EQH/EQL and trendlines are the only derived objects. They use engine
  swings only, plus the key-level clustering tolerance from `analysis/levels.py`
  (0.0002 below price 10, otherwise 0.20). Their `source` says "derived".
* Breaker and mitigation blocks are **not** drawn, because the engine does not
  detect them.
* The engine produces one target, so the position box shows **TP**, not TP1/TP2.
* `ai/desk.py` rounds FVG/OB/premium-discount prices to 3 decimals for the
  prompt. The chart reads the exact price from the same candle/swing and keeps
  it only if it rounds back to the desk value. So 5-digit FX zones are exact
  and still identical to what the AI sees.
* All coordinates use closed candles from the analysis snapshot (UTC). Objects
  of a timeframe only reference candles/swings of that timeframe.

## Data contract

`GET /analysis/{symbol}` has an additive field `chart_overlays`:

```json
{
  "type": "chart_overlay",
  "symbol": "XAUUSDm",
  "analysis_id": "XAUUSDm@2026-11-24T07:29:18+00:00",
  "generated_at_utc": "2026-11-24T07:29:18+00:00",
  "action": "replace",
  "overlays": [
    {
      "id": "XAUUSDm:M15:fvg:bearish:2026-11-24T03:00:00+00:00",
      "symbol": "XAUUSDm", "timeframe": "M15",
      "layer": "fvg", "kind": "zone", "name": "Bearish FVG",
      "color": "bearish", "status": "active",
      "price_low": 3643.056, "price_high": 3646.464,
      "time_start": "2026-11-24T02:30:00+00:00",
      "source": "ai.desk.detect_fvg_order_blocks",
      "created_at": "2026-11-24T07:29:18+00:00",
      "meta": {"fresh": true, "distance_atr": 2.1, "key": true}
    }
  ]
}
```

* `kind`: `hline`, `zone`, `trendline`, `arrow`, `marker`, `label`, `position`
* `status`: `active`, `confirmed`, `candidate`, `potential`, `waiting`,
  `invalidated`, `mitigated`, `taken`, `broken`, `expired`
* `timeframe`: `M1` … `D1`, or `MTF` for the trade plan and chat annotations
* `color` is a semantic token (`bullish`, `bearish`, `neutral`, `info`,
  `warning`, `entry`, `stop`, `target`)
* `id` is deterministic (symbol, timeframe, type, candle/swing time), so a
  refresh updates objects instead of duplicating them.

Validation runs twice. `app/schemas/chart.py::ChartOverlay` drops invalid
objects on the server (they are logged as `CHART_OVERLAY dropped`).
`frontend/src/utils/chartOverlays.js::validateOverlay` rejects anything
malformed before it reaches the canvas.

`POST /analysis/{symbol}/chat` has an additive field `chart`:

```json
{
  "type": "chart_command",
  "symbol": "XAUUSDm",
  "analysis_id": "…",
  "intents": ["pullback", "setup"],
  "entry_allowed": false,
  "blockers": ["Belum ada trigger yang terkonfirmasi …"],
  "notes": [],
  "operations": [
    {"op": "create", "overlays": [{"kind": "arrow", "name": "WAIT FOR CONFIRMATION", "…": "…"}]},
    {"op": "highlight", "ids": ["XAUUSDm:M5:ob:bearish:…"]}
  ],
  "overlay_payload": {"type": "chart_overlay", "…": "…"}
}
```

Operations are `create` / `update` (upsert by id), `highlight` and `clear`
(`scope: "ai"` removes chat annotations and highlights only). A new chat
message never clears existing annotations.

## How chat-to-chart works (no second LLM call)

`backend/app/services/chart/chat_commands.py`:

1. **Intent** from the trader's question (liquidity, structure/why, pullback,
   invalidation, setup, FVG, OB, S/R, premium/discount, trendline, clear).
2. **Grounding** in the AI reply. Prices it quotes are matched to engine
   objects (same tolerance as `answer_audit`), and timeframes it mentions
   (H1, M15, …) rank first.
3. **Annotations** use engine prices only:
   * invalidation: line(s) at the scenarios' `invalidation_reference`. If the
     plan's scenario has none, the command says so in `notes`.
   * pullback/wait: an arrow from the current price to the nearest same-direction
     engine zone, labelled WAIT FOR CONFIRMATION.
   * setup: highlights the trade-plan object. A position box exists only if the
     entry gate allows entry; otherwise it is WAITING with the blockers.

## Dashboard

On the Analysis page, the chart toolbar has:

* layer toggles (Market Structure, FVG, Order Blocks, Liquidity, Trendline,
  Support & Resistance, Premium & Discount, Trade Plan), plus **HTF refs**
* **Show All**, **Hide All**, **Clear AI Drawings**, **Highlight Latest Analysis**

Layer preferences are stored in `localStorage["quantterminal_chart_layers"]`
(this browser only, no API call).

Timeframe rules:

* each chart shows its own timeframe's objects;
* higher-timeframe S/R and premium/discount appear as dashed references tagged
  with their timeframe;
* higher-timeframe FVG/OB/liquidity appear only with **HTF refs** on;
* lower-timeframe objects never appear on a higher-timeframe chart.

Switching symbol drops all drawings of the previous symbol. If the AI
highlights objects on another timeframe, the chart says which timeframe to
switch to.

Faded or dashed styles mean `mitigated` / `taken` / `broken` (faded),
`candidate` / `waiting` (dashed), or a higher-timeframe reference (dashed,
tagged). Analysis older than 5 minutes is drawn faded with a **STALE** badge.

## Tests

```bash
cd ~/AI
docker compose run --rm --no-deps -v "$PWD/backend:/app" -w /app backend python test_chart_overlays.py
```
