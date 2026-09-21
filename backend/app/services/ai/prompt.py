from typing import Any


def build_analysis_prompt(context: dict[str, Any]) -> str:
    return f"""
Analyze the following structured market-analysis context.

SYMBOL
{context["symbol"]}

IMPORTANT:
- The data comes from a deterministic market-analysis engine.
- Treat provided market data as observed data.
- Do not invent missing values.
- Do not assume an indicator exists if its value is null.
- Do not create entry, stop loss, take profit, or position size values
  that are not present in the context.
- Do not treat a scenario as confirmed unless confirmation explicitly
  says confirmed.
- A mixed market bias is valid and must not be forced into bullish
  or bearish.
- Conflicting timeframes must be explicitly acknowledged.
- The analysis is decision support for a human trader.
- Do not execute trades.
- The numeric values in trigger_reference and invalidation_reference are canonical engine fields, not values to be inferred.
- Copy these numeric reference values exactly as provided, preserving their digits.
- If trigger_reference is 1.148025, the scenario trigger number must be 1.148025, even if key_levels contains a nearby level such as 1.14762.
- Never substitute, round, approximate, or reinterpret scenario reference numbers.
- For each scenario, use trigger_reference and invalidation_reference as the authoritative numeric references for that scenario.
- Do not replace a scenario's trigger_reference or invalidation_reference with another support or resistance level from key_levels.
- When describing a scenario numerically, the corresponding *_reference fields take precedence over other levels.
- A null trigger_reference or invalidation_reference means that numeric reference is unavailable.
- If a scenario reference is null, do not infer, derive, substitute, reuse, or calculate a numeric level or distance for it.
- If invalidation_reference is null, report the invalidation reference and any invalidation distance as unavailable.
- Never use trigger_reference as a substitute for invalidation_reference, or invalidation_reference as a substitute for trigger_reference.
- Do not invent an invalidation condition from the scenario trigger when the engine provides no invalidation_reference.

ANALYSIS ORDER

1. MARKET CONDITION
Explain the overall market condition using the provided market bias,
trend, and structure.

2. HIGHER-TIMEFRAME CONTEXT
Analyze H4 and D1.
Explain:
- trend
- structure
- EMA alignment
- momentum indicators when available
- important conflicts

3. INTRADAY CONTEXT
Analyze H1 and M30.

4. ENTRY-TIMEFRAME CONTEXT
Analyze M15, M5, and M1.
Pay particular attention to whether the lower timeframes agree
with the higher-timeframe context.

5. TECHNICAL CONFLUENCE
Identify where multiple pieces of evidence agree.
Do not call something confluence merely because several indicators
exist; explain what actually agrees.

6. CONFLICTS
Explicitly identify:
- timeframe conflicts
- trend vs structure conflicts
- bias vs scenario conflicts
- any other meaningful contradiction

7. KEY LEVELS
Explain the provided support and resistance zones.
Mention timeframe confluence where available.

8. SCENARIOS
Review every provided scenario.
For each scenario explain:
- direction
- status
- trigger
- invalidation
- distance to trigger when available
- ATR relationship when available
- confirmation status

9. TRADE PLAN
Explain the current trade-plan status.
If it is waiting, explain what condition is still missing.
If it is confirmed but missing risk or stop information, explain that.
If it is ready for manual review, clearly distinguish that from
an instruction to trade.

10. RISK
Discuss the provided risk information only.
Never invent account equity, risk percentage, volume, or loss.

11. ALTERNATIVE SCENARIO
Explain the most relevant alternative scenario and what would
cause the market interpretation to change.

12. FINAL NEUTRAL SUMMARY
Give a concise summary containing:
- current market condition
- dominant context
- major conflict
- important level
- confirmation state
- invalidation condition

Do not give a forced BUY or SELL recommendation.

STRUCTURED MARKET CONTEXT
{context}
""".strip()
