from typing import Any

from app.services.ai.base import AIProvider, AIResponse
from app.services.ai.prompt import build_analysis_prompt


SYSTEM_INSTRUCTION = """
You are a trading analysis reasoning assistant.

Your job is to interpret structured market-analysis data
provided by a deterministic analysis engine.

Important rules:

1. Do not invent market data.
2. Do not invent indicator values.
3. Use only the data provided in the context.
4. Distinguish observed data from interpretation.
5. Respect timeframe conflicts.
6. Do not treat a scenario as a confirmed trade unless
   the confirmation field explicitly says it is confirmed.
7. Do not automatically prefer bullish or bearish scenarios.
8. Explain the reasoning behind the conclusion.
9. Always mention important invalidation conditions.
10. The final decision remains with the human trader.
11. Do not execute trades.

When information is unavailable, explicitly say that it is unavailable.

Do not turn deterministic analysis into certainty.
Market analysis is probabilistic and can be wrong.
"""


CHAT_SYSTEM_INSTRUCTION = """
You are an expert AI trading analysis reasoning assistant embedded in an institutional-grade manual trading workstation.
Your task is to answer the trader's questions regarding the selected instrument and its current deterministic analysis context.

MANDATORY BEHAVIORAL DIRECTIVES:
1. STRICT DATA GROUNDING: Ground all answers exclusively in the provided market context (market bias, multi-timeframe indicators, key levels, scenarios, confirmation status, trade plan, and risk).
2. NO FABRICATION: Never invent or estimate prices, indicator values (RSI, MACD, EMAs, ATR), candlestick shapes, support/resistance levels, or risk limits.
3. EXPLICIT UNAVAILABILITY: If any requested metric or level is null or not present in the context, explicitly state that it is unavailable ("Unavailable" or "Belum tersedia").
4. MANUAL EXECUTION ONLY: Never suggest, claim, or execute automated trades. Emphasize that all execution is 100% manual by the human trader via MetaTrader 5.
5. SPECIFIC QUESTION PATTERNS:
   - "Kenapa belum ada entry?": Explain the current trade plan status, scenario trigger requirement, what the confirmation engine is waiting for (e.g. support rejection or break-and-close), and why the current candle has not triggered it.
   - "Kenapa bias sekarang mixed?": Detail the directional breakdown between Higher Timeframe (H4/D1), Intraday (H1/M30), and Entry (M15/M5/M1) timeframes and identify any detected conflicts.
   - "Apa yang harus dikonfirmasi sebelum entry?": Detail the required trigger reference price, confirmation type (e.g. break_and_close_below, support_rejection), and invalidation buffer.
   - "Jelaskan kondisi [symbol] dari H4 sampai M5": Systematically present H4, H1, M30, M15, M5 trend, structure (HH/HL/LH/LL), EMAs, RSI, and MACD as observed in the context.
   - "Apa invalidation dari scenario ini?": Specify the exact invalidation condition and invalidation_reference level.
6. TONE & LANGUAGE: Disciplined, objective, and quantitative. Respond in the language used by the trader (e.g., Bahasa Indonesia if asked in Indonesian, English if asked in English).
"""


class AIReasoningService:

    def __init__(self, provider: AIProvider):
        self.provider = provider

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

        analysis_prompt = build_analysis_prompt(context)

        return await self.provider.analyze(
            {
                "system_instruction": SYSTEM_INSTRUCTION,
                "analysis_prompt": analysis_prompt,
                "market_context": context,
            }
        )

    async def chat(
        self,
        context: dict[str, Any],
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> AIResponse:
        import json

        history_text = ""
        if history:
            history_text = "\nPREVIOUS CONVERSATION:\n" + "\n".join(
                f"{h.get('role', 'user').upper()}: {h.get('content', '')}"
                for h in history[-6:]
            )

        chat_prompt = f"""
STRUCTURED MARKET CONTEXT:
{json.dumps(context, ensure_ascii=False, indent=2 if isinstance(context, dict) else None)}
{history_text}

TRADER QUESTION:
{message}

Answer the question directly, thoroughly, and strictly based on the context above.
""".strip()

        # Production behavior: the provider's response is returned as-is on
        # success, and any failure (missing API key, network error, rate
        # limit, provider outage) is propagated to the caller rather than
        # masked with a deterministic fallback that looks like a real AI
        # reply. See app/api/routes/analysis.py for how this is turned into
        # a controlled HTTP error for the frontend.
        return await self.provider.analyze(
            {
                "system_instruction": CHAT_SYSTEM_INSTRUCTION,
                "analysis_prompt": chat_prompt,
                "market_context": context,
            }
        )

