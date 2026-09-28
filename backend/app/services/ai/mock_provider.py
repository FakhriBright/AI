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

        analysis_prompt = context.get("analysis_prompt", "")
        system_instruction = context.get("system_instruction", "")

        analysis = (
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
                "system_instruction_received": bool(system_instruction),
                "analysis_prompt_received": bool(analysis_prompt),
            },
        )
