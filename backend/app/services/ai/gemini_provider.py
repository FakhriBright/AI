from typing import Any

from google import genai

from app.core.config import settings
from app.services.ai.base import AIResponse


class GeminiAIProvider:

    def __init__(self):
        if not settings.ai_api_key:
            raise RuntimeError("AI_API_KEY is not configured")

        self.client = genai.Client(
            api_key=settings.ai_api_key
        )

        self.model = "gemini-3.6-flash"

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

        prompt = (
            context["system_instruction"]
            + "\n\n"
            + context["analysis_prompt"]
        )

        interaction = await self.client.aio.interactions.create(
            model=self.model,
            input=prompt,
        )

        analysis = interaction.output_text or ""

        return AIResponse(
            provider="gemini",
            model=self.model,
            analysis=analysis,
            raw={
                "id": interaction.id,
                "model": self.model,
                "status": interaction.status,
            },
        )
