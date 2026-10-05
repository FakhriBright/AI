from typing import Any

from app.services.ai.serializer import dumps_compact


def build_analysis_prompt(context: dict[str, Any]) -> str:
    market_context = dumps_compact(context)

    return f"""\
Analyze the following structured market-analysis context.

SYMBOL
{context["symbol"]}

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
  live broker spread, unless live spread is explicitly present in context.

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
  be stated plainly in the next read -- it is not a reason to hedge now.

ANALYSIS ORDER

1. MARKET CONDITION -- structure, trend, which mode(s) currently have
   usable conviction (intraday, scalp, or neither).
2. HIGHER-TIMEFRAME (H4, D1) -- trend, structure, EMA alignment.
3. INTRADAY (H1, M30) -- same, plus relation to HTF (aligned/conflicting).
4. ENTRY-TIMEFRAME (M15, M5, M1) -- structure independent of HTF; this is
   the primary input for scalp_scenarios regardless of HTF direction.
5. PATTERN & ZONE CONFLUENCE -- candlestick pattern strength, supply/demand
   zone freshness, breakout_status, at the specific levels in play.
6. INTRADAY SCENARIOS -- for each: direction, breakout_status, conviction,
   trigger, invalidation, distance/ATR.
7. SCALP SCENARIOS -- same fields, explicitly labeled relative to HTF
   (aligned vs counter-trend bounce), smaller ATR reference.
8. CONFLICTS -- timeframe/trend conflicts, stated as coexisting facts
   across modes, not resolved away.
9. KEY LEVELS -- support/resistance AND supply/demand zones, with
   freshness and touch count.
10. TRADE PLAN -- status, missing conditions, readiness, per mode.
11. RISK -- provided risk only; never invent equity/volume/loss.
12. INVALIDATED PRIOR SCENARIOS -- explicitly flag anything that failed
    since the last read.
13. FINAL SUMMARY -- state the clearest available read per mode (intraday
    and scalp separately) with its conviction level. A low-conviction read
    is reported as low-conviction, not papered over as "neutral for
    safety." Do not force a trade recommendation beyond what context
    supports, but do not default to vagueness when conviction is high.

STRUCTURED MARKET CONTEXT
{market_context}"""
