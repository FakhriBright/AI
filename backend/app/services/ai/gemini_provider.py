from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.ai.base import AIResponse


class GeminiAIProvider:

    def __init__(self, model: str | None = None):
        api_key = settings.gemini_api_key or settings.ai_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY (or legacy AI_API_KEY) is not configured")

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(settings.ai_request_timeout_seconds * 1000),
            ),
        )

        self.provider = "gemini"
        self.model = model or settings.gemini_model

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

        prompt = (
            context["system_instruction"]
            + "\n\n"
            + context["analysis_prompt"]
        )

        generate_kwargs: dict[str, Any] = {
            "model": self.model,
            "contents": prompt,
        }

        max_tokens = context.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            generate_kwargs["config"] = types.GenerateContentConfig(
                max_output_tokens=max_tokens + max(0, settings.ai_reasoning_tokens),
            )

        response = await self.client.aio.models.generate_content(
            **generate_kwargs,
        )

        analysis = response.text or ""

        finish_reason = None
        if response.candidates:
            reason = response.candidates[0].finish_reason
            finish_reason = getattr(reason, "value", reason)

        usage = {"type": "ESTIMATED", "prompt_tokens": len(prompt) // 4, "completion_tokens": len(analysis) // 4, "total_tokens": (len(prompt) + len(analysis)) // 4}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            p_tok = getattr(meta, "prompt_token_count", None)
            c_tok = getattr(meta, "candidates_token_count", None)
            t_tok = getattr(meta, "total_token_count", None)
            if p_tok is not None:
                usage = {
                    "type": "ACTUAL",
                    "prompt_tokens": int(p_tok),
                    "completion_tokens": int(c_tok or 0),
                    "total_tokens": int(t_tok or ((p_tok or 0) + (c_tok or 0))),
                }

        return AIResponse(
            provider="gemini",
            model=self.model,
            analysis=analysis,
            raw={
                "model": self.model,
                "model_version": getattr(response, "model_version", None),
                "finish_reason": finish_reason,
                "usage": usage,
            },
        )
