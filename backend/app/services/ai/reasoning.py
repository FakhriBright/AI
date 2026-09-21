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
