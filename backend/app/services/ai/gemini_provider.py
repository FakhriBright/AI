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

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        analysis = response.text or ""

        return AIResponse(
            provider="gemini",
            model=self.model,
            analysis=analysis,
            raw={
                "model": self.model,
            },
        )
