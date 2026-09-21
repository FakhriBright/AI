from typing import Any

from anthropic import AsyncAnthropic

from app.core.config import settings
from app.services.ai.base import AIResponse


class AnthropicAIProvider:

    def __init__(self):
        if not settings.ai_api_key:
            raise RuntimeError("AI_API_KEY is not configured")

        self.client = AsyncAnthropic(
            api_key=settings.ai_api_key
        )

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

        response = await self.client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4000,
            system=context["system_instruction"],
            messages=[
                {
                    "role": "user",
                    "content": context["analysis_prompt"],
                }
            ],
        )

        analysis_parts = []

        for block in response.content:
            if getattr(block, "type", None) == "text":
                analysis_parts.append(block.text)

        analysis = "\n".join(analysis_parts).strip()

        return AIResponse(
            provider="anthropic",
            model=response.model,
            analysis=analysis,
            raw={
                "id": response.id,
                "model": response.model,
                "stop_reason": response.stop_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            },
        )
