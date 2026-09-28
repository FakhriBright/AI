from typing import Any

from app.services.ai.serializer import dumps_compact


def build_analysis_prompt(context: dict[str, Any]) -> str:
    market_context = dumps_compact(context)

    return f"""\
Analyze the following structured market-analysis context.

SYMBOL
{context["symbol"]}

RULES:
- Data comes from a deterministic engine. Treat as observed data.
- Do not invent missing values or assume unavailable indicators exist.
- Do not create entry/SL/TP/position size not present in context.
- A scenario is confirmed ONLY if confirmation explicitly says so.
- Mixed bias is valid; do not force bullish or bearish.
- Conflicting timeframes must be acknowledged explicitly.
- Decision support only. Do not execute trades.
- trigger_reference and invalidation_reference are canonical engine fields.
- Copy these numeric references exactly as provided. Never substitute, round, or reinterpret.
- If a reference is null, report it as unavailable. Do not infer or derive a substitute.
- Never swap trigger_reference for invalidation_reference or vice versa.
- Fundamental data is unavailable unless explicitly provided in context. Do NOT invent economic news or events; mark fundamental analysis as 'Unavailable / Belum tersedia'.

OUTPUT DISCIPLINE:
- Start with findings. No preamble, no restating the question or JSON.
- Keep reasoning that changes interpretation. Drop generic narration.
- Stay quantitative. Use only provided numbers.

ANALYSIS ORDER

1. MARKET CONDITION — overall bias, trend, structure.
2. HIGHER-TIMEFRAME (H4, D1) — trend, structure, EMA alignment, momentum, conflicts.
3. INTRADAY (H1, M30).
4. ENTRY-TIMEFRAME (M15, M5, M1) — agreement/divergence with HTF.
5. TECHNICAL CONFLUENCE — where multiple evidences actually agree.
6. CONFLICTS — timeframe, trend/structure, bias/scenario contradictions.
7. KEY LEVELS — support/resistance zones, timeframe confluence.
8. SCENARIOS — for each: direction, status, trigger, invalidation, distance, ATR ratio, confirmation.
9. TRADE PLAN — status, missing conditions, readiness.
10. RISK — provided risk only; never invent equity/volume/loss.
11. ALTERNATIVE SCENARIO — most relevant alternative, what changes interpretation.
12. FINAL NEUTRAL SUMMARY — condition, dominant context, major conflict, key level, confirmation, invalidation. No forced BUY/SELL.

STRUCTURED MARKET CONTEXT
{market_context}"""
