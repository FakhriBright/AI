from typing import Any

from app.services.ai.base import AIResponse


class MockAIProvider:
    def __init__(self, provider: str = "gemini", model: str = "gemini-3.6-flash"):
        self.provider = provider
        self.model = model

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

        market_context = context["market_context"]
        analysis_prompt = context["analysis_prompt"]
        system_instruction = context["system_instruction"]

        symbol = market_context["symbol"]
        bias = market_context["market_bias"]["overall"]

        trade_plan = market_context["trade_plan"]

        scenario = trade_plan["scenario_name"]
        status = trade_plan["status"]

        analysis = (
            f"Symbol: {symbol}\n"
            f"Market bias: {bias}\n"
            f"Scenario: {scenario}\n"
            f"Trade plan status: {status}\n\n"
            "Prompt contract received: YES\n"
            f"System instruction received: "
            f"{bool(system_instruction)}\n"
            f"Analysis prompt received: "
            f"{bool(analysis_prompt)}\n\n"
            "This is a mock AI response. "
            "No external AI model has been called."
        )

        return AIResponse(
            provider=self.provider,
            model=self.model,
            analysis=analysis,
            raw={
                "source": "mock",
                "symbol": symbol,
                "bias": bias,
                "scenario": scenario,
                "status": status,
                "system_instruction_received": bool(system_instruction),
                "analysis_prompt_received": bool(analysis_prompt),
            },
        )
