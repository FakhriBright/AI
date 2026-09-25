from typing import Any

from groq import AsyncGroq

from app.core.config import settings
from app.services.ai.base import AIResponse


class GroqAIProvider:

    def __init__(self):
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. "
                "Set the GROQ_API_KEY environment variable to use the Groq provider."
            )

        self.client = AsyncGroq(
            api_key=settings.groq_api_key,
        )

        self.model = settings.groq_model

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": context["system_instruction"],
                },
                {
                    "role": "user",
                    "content": context["analysis_prompt"],
                },
            ],
            temperature=0.3,
        )

        choice = response.choices[0]
        analysis = choice.message.content or ""

        return AIResponse(
            provider="groq",
            model=response.model,
            analysis=analysis,
            raw={
                "id": response.id,
                "model": response.model,
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            },
        )
