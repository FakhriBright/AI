from typing import Any

from app.services.ai.desk import (
    analysis_context_max_chars,
    build_analysis_llm_context,
    dumps,
    shrink_to_budget,
)

# Methodology text is kept verbatim from the previous monolithic prompt, but
# split per desk so only the relevant desks are sent (token efficiency).

_HARD_RULES = """\
HARD RULES (do not violate these under any framing):
- Data comes from a deterministic engine. Treat as observed data.
- Do not invent missing values or assume unavailable indicators exist.
- Do not create entry/SL/TP/position size not present in context.
- A scenario is confirmed ONLY if confirmation explicitly says so
  (breakout_status / pattern fields), not by narrative inference.
- trigger_reference and invalidation_reference are canonical engine
  fields. Copy them exactly. Never substitute, round, or reinterpret.
  If null, report as unavailable -- do not infer a substitute.
- Never swap trigger_reference for invalidation_reference or vice versa.
- Fundamental data is unavailable unless explicitly provided in context.
  Do NOT invent economic news or events; mark fundamental analysis as
  'Unavailable / Belum tersedia'.
- DIRECTIONAL ALIGNMENT: a break-and-close below support is bearish
  continuation. A break-and-close above resistance is bullish breakout.
  A support test with close back above it is a bullish reclaim/rejection
  -- call it that, never a "breakout".
- false_breakout means wick pierced the level but body closed back on the
  original side -- describe this explicitly as a false breakout / trap,
  never as a continuation signal.
- pullback_failed means a prior true_breakout reversed with a body close
  back past the original level -- this is a structure change, not a
  pullback. Say so plainly.
- NO CONTRADICTORY OUTPUT: scenario label, breakout_status, and narration
  must never contradict each other.
- SPREAD vs ATR: the ATR-based buffer is a volatility estimate, not a
  live broker spread, unless live spread is explicitly present in context."""

_DECISION = """\
DECISION DISCIPLINE (this replaces any instinct to stay neutral by default):
- You are given TWO independent scenario sets: `intraday_scenarios`
  (higher-timeframe aligned) and `scalp_scenarios` (entry-timeframe, may
  run counter to the higher-timeframe trend). Analyze and report BOTH,
  even if only one has usable conviction right now.
- Each scenario carries a `conviction` field (low/medium/high) computed
  from confluence scoring already done upstream. Use it as your anchor:
  - conviction=high -> state the directional read plainly and commit to
    it (e.g. "bias bearish lanjut, breakout tertahan di X, invalidasi di
    Y"). Do not hedge a high-conviction read into vague language.
  - conviction=medium -> state the read but name explicitly what
    confluence is still missing for it to become high.
  - conviction=low -> say plainly that there is no actionable edge yet;
    describe what would need to happen for that to change. This is NOT
    the same as silently defaulting everything to neutral -- name the
    specific missing piece.
- A higher-timeframe bearish read and a lower-timeframe bullish
  scalp_scenario are NOT a contradiction to resolve into "mixed" -- they
  are two different, simultaneously true facts operating on different
  holding periods. Report both explicitly, each with its own conviction,
  instead of collapsing them into one vague verdict.
- If a scenario's status is `invalidated` (its invalidation_reference was
  hit since the prior read), say so explicitly and plainly: name the
  scenario, state that it did not play out, and state why. Do not quietly
  drop it or rephrase around it.
- Being direction-committal when conviction is high is REQUIRED, not
  optional. The failure mode to avoid is generic hedge-everything
  language when the underlying data already supports a clear read. Being
  wrong later (when invalidation triggers) is acceptable and expected to
  be stated plainly in the next read -- it is not a reason to hedge now."""

_DESK_RULES = """\
DESK BRIEF (deterministic router output in `desk`):
- `desk.reads` = one block per timeframe: latest CLOSED `candle`, its
  `where` (location vs key levels) and `sweep`, plus `patterns` with aliases
  already merged: ONE pattern item = ONE evidence family. Never count the
  entries inside `names` as separate confluence. Each pattern has `vs_htf`
  and `route` = {desk, play, needs}. Follow the route: cite the candle (tf +
  OHLC), say which desk (SNR/SMC/ICT) handles it and why, then give the plan
  and what must still happen.
- `desk.no_pattern_tfs`: closed candle exists but no pattern was detected.
- `desk.entry_gate.can_enter_now` is authoritative on whether an entry exists.
- `desk.setups` are conditional reference calculations, NOT permission to
  place an order. `ref` is hypothetical entry at trigger; `now` is hypothetical
  entry at snapshot market price. Both are backend-validated calculations.
  `ref.order` describes order geometry only; it is NOT an execution instruction.
  `execution.place_order_now` is authoritative and false for scenario-reference
  setups. If `execution.status=wait_for_confirmation`, wait for the exact
  `confirm_rule`, then reassess current price and a fresh plan. Never recommend
  both a pending order at `ref.entry` and a market order after confirmation.
  Never mix prices from `ref`, `now`, and `trade_plan` in one plan. Copy values;
  never recompute. High RR is not quality: report `rr_tidak_wajar_tinggi`.
  Reject views flagged for invalid geometry, missing ATR, RR below 1, or
  implausible target/stop distances; do not present them as actionable.
  Patterns with `rel: far` are historical context, never entry evidence.
  Do not mix triggers from different `mode` (intraday/scalp).
- `desk.unavailable` lists data the engine does not provide: say "tidak
  tersedia" for those, never estimate them."""

_SMC = """\
SMC — Smart Money Concepts:
- Order Blocks (OB): the last opposing candle before a strong impulse move.
  A bullish OB = last bearish candle before a bullish impulse; treat as
  demand zone on retest. A bearish OB = last bullish candle before bearish
  impulse; treat as supply zone.
- Break of Structure (BOS): a closed candle beyond a confirmed swing high
  (bullish BOS) or swing low (bearish BOS). Must be a body close, not a wick.
- Change of Character (CHoCH): the FIRST structure break opposite to the
  prevailing trend; signals a potential trend reversal, not just a pullback.
  Label bullish/bearish CHoCH and the timeframe it occurred on.
- Fair Value Gap (FVG / Imbalance): three-candle sequence where candle 3
  low > candle 1 high (bullish FVG) or candle 3 high < candle 1 low
  (bearish FVG). Report bounds and freshness only if deterministic context
  provides them; never infer from prose.
- Liquidity sweep: wick pierces a prior swing high/low (BSL/SSL) but body
  closes back inside range. This is NOT a BOS; it is a stop-hunt / trap.
  After a sweep of sell-side liquidity (SSL) with bullish close → look for
  long entries. After a sweep of buy-side liquidity (BSL) with bearish
  close → look for short entries.
- Premium / Discount zones: above equilibrium (50% of the range) is premium
  (favor shorts); below equilibrium is discount (favor longs)."""

_ICT = """\
ICT — Inner Circle Trader concepts:
- Killzones (optimal entry windows): London Open (02:00–05:00 NY time),
  NY AM (08:30–11:00 NY time), NY PM (13:30–16:00 NY time). Flag if the
  current candle is within a killzone when context provides server time.
- Optimal Trade Entry (OTE): 61.8%–79% Fibonacci retracement of the last
  swing move; highest-probability entry within an OB or demand/supply zone.
- Market Structure Shift (MSS): same as CHoCH in SMC; the first internal
  structure break that signals trend exhaustion.
- Breaker blocks: a failed OB that price trades through and then retests
  from the other side; changes from demand to supply or vice versa.
- Mitigation block: when price returns to an OB to partially fill orders
  before continuing in the original direction.
- Institutional candles (displacement): large-body candles (marubozu /
  engulfing) that leave FVGs; indicate institutional order flow."""

_SNR = """\
SNR — Support and Resistance:
- Key levels: swing highs/lows, round numbers, prior session highs/lows,
  weekly/monthly opens, point of control from volume profile if available.
- Zone vs line: treat levels as zones (± ATR * 0.15), not exact prices.
  Multiple timeframe confluence strengthens a zone.
- Level freshness: first test of a level is highest probability; repeated
  tests deplete liquidity. A level tested 3+ times is likely to break.
- Flip levels: a support that breaks and is retested from below becomes
  resistance (and vice versa). Always state whether a level has flipped."""

_CANDLE = """\
CANDLESTICK PATTERN INTERPRETATION (SMC/ICT/SNR context):
- Candlestick patterns are descriptive evidence, never standalone entry commands.
- Use ONLY pattern names/directions/strengths explicitly present in
  deterministic context. Never claim a pattern was detected from prose.
- Candles are compact arrays [time_utc,open,high,low,close] (CLOSED candles
  only, oldest first, last = latest closed). Patterns come from the
  deterministic engine; if none is listed for a timeframe, say no pattern
  was detected. A pattern is never an automatic entry: judge it by
  location, structure and follow-through.
- Pin bar / Hammer at demand zone or after SSL sweep → bullish confluence;
  require closed-candle confirmation above the pin bar high (or CHoCH).
- Pin bar / Shooting star at supply zone or after BSL sweep → bearish
  confluence; require closed-candle confirmation below the pattern low.
- Engulfing / Marubozu → displacement candle; marks start of an impulsive
  move; the engulfing body is the OB candidate. Do not enter after an
  extended engulfing; wait for retest of the OB body.
- Inside bar at a key level → compression before BOS; trade the breakout
  with a closed candle, not the wick.
- Doji / Spinning top at key level → indecision; wait for the next candle
  to provide directional close before assigning bias.
- Morning / Evening star, Three white soldiers / Three black crows →
  HTF reversal or continuation confirmation; check if the pattern aligns
  with HTF bias before labeling it actionable.
- For patterns that require a gap (kicker, abandoned baby): lower confidence
  in FX/CFD where continuous price eliminates gaps. State explicitly if a
  gap was absent.
- Tweezer top/bottom → equal-high/low rejection (SNR); treated as
  double-test of a zone. Useful as CHoCH confirmation if trend context agrees.
- Inverted hammer (in downtrend): upper wick shows attempted buying;
  requires a bullish close on the next candle for confirmation.
- BOS/CHoCH must reference a specific confirmed swing level with a body
  close through it. Wick sweeps are liquidity grabs, not BOS.
- FVG bounds must come from deterministic context only. If absent, say
  'FVG data unavailable'; do not estimate.
- Avoid counting the same formation under multiple pattern aliases as
  independent confluence votes (e.g., pin_bar and hammer on the same candle
  count as one evidence family)."""

_ORDER = """\
ANALYSIS ORDER

1. MARKET CONDITION -- structure, trend, and which mode(s) have usable
   conviction (intraday, scalp, or neither). State SMC phase if determinable
   (accumulation, distribution, markup, markdown, re-accumulation, etc.).
2. HIGHER-TIMEFRAME (H4, D1) -- trend, BOS/CHoCH, OB / supply-demand zones,
   EMA alignment, FVG if available, premium/discount position.
3. INTRADAY (H1, M30) -- same fields plus HTF alignment / conflict.
   Note any HTF OB or FVG being tested.
4. ENTRY-TIMEFRAME (M15, M5, M1) -- independent structure analysis;
   primary input for scalp_scenarios. Identify MSS / internal BOS.
   Note killzone overlap if server time is available.
5. PATTERN & ZONE CONFLUENCE -- pattern strength, OB/zone freshness,
   liquidity sweep context, breakout_status at the levels in play.
6. INTRADAY SCENARIOS -- for each: direction, breakout_status, conviction,
   trigger (with price), invalidation (with price), distance/ATR.
7. SCALP SCENARIOS -- same fields; label as aligned or counter-trend vs HTF;
   note OTE range if applicable.
8. CONFLICTS -- timeframe/trend conflicts as coexisting facts, not resolved
   into a single vague verdict.
9. KEY LEVELS -- support/resistance AND OB/supply-demand zones; freshness,
   touch count, flip status, HTF confluence.
10. TRADE PLAN -- status, missing conditions, readiness, per mode.
11. RISK -- provided risk parameters only; never invent equity/volume/loss.
12. INVALIDATED PRIOR SCENARIOS -- flag anything that failed since last read;
    name what broke the scenario.
13. FINAL SUMMARY -- clearest read per mode (intraday and scalp separately)
    with conviction level. Low-conviction = report as low-conviction, not
    "neutral for safety." High-conviction = commit to the directional read."""

_MINIMAL_ORDER = (
    "ANALYSIS ORDER: market condition, higher timeframe, intraday, entry "
    "timeframe, pattern & zone confluence, scenarios, conflicts, key levels, "
    "trade plan, risk, final summary."
)

_DESK_TEXT = {"SMC": _SMC, "ICT": _ICT, "SNR": _SNR}


def build_analysis_prompt(
    context: dict[str, Any],
    *,
    minimal: bool = False,
) -> str:
    """Prompt for the full analysis.

    `context` may be the full ai_context or an already-slim one (has `desk`).
    Only the methodology desks that the deterministic router selected are
    included. `minimal=True` is the retry shape after a 413.
    """
    llm_ctx = context if "desk" in context else build_analysis_llm_context(context)
    budget = analysis_context_max_chars()
    llm_ctx = shrink_to_budget(llm_ctx, budget // 2 if minimal else budget)

    desks = (llm_ctx.get("desk") or {}).get("desks") or ["SMC", "ICT", "SNR"]

    parts = [
        "Analyze the following structured market-analysis context.",
        f"SYMBOL\n{llm_ctx.get('symbol')}",
        _HARD_RULES.strip(),
    ]
    if not minimal:
        parts.append(_DECISION.strip())
    parts.append(_DESK_RULES.strip())

    if not minimal:
        parts.append("TRADING METHOD FRAMEWORK (only the desks routed for this read):")
        parts.extend(_DESK_TEXT[d].strip() for d in desks if d in _DESK_TEXT)

    parts.append(_CANDLE.strip())
    parts.append(_MINIMAL_ORDER if minimal else _ORDER.strip())
    parts.append("STRUCTURED MARKET CONTEXT\n" + dumps(llm_ctx))

    return "\n\n".join(parts)
