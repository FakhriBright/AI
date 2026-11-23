import re
from typing import Any

import httpx

from app.core.config import settings
from app.services.ai.base import AIResponse

# Qwen3 is a reasoning model. `think: false` disables its <think> block on
# current Ollama versions; the regex is a fallback for builds that ignore it.
_THINK_BLOCK = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)


class OllamaAIProvider:

    def __init__(self):
        if not settings.ollama_base_url:
            raise RuntimeError(
                "OLLAMA_BASE_URL is not configured. "
                "Set the OLLAMA_BASE_URL environment variable to use the Ollama provider."
            )

        self.base_url = settings.ollama_base_url.rstrip("/")
        self.timeout = settings.ollama_timeout_seconds

        self.provider = "ollama"
        self.model = settings.ollama_model

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

        options: dict[str, Any] = {
            "temperature": 0.3,
            "num_ctx": settings.ollama_num_ctx,
        }

        max_tokens = context.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            options["num_predict"] = max_tokens

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": context["system_instruction"],
                },
                {
                    "role": "user",
                    "content": context["analysis_prompt"],
                },
            ],
            "stream": False,
            "think": False,
            "options": options,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        analysis = (data.get("message") or {}).get("content") or ""
        analysis = _THINK_BLOCK.sub("", analysis)

        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        completion_tokens = int(data.get("eval_count") or 0)

        return AIResponse(
            provider="ollama",
            model=data.get("model") or self.model,
            analysis=analysis,
            raw={
                "model": data.get("model") or self.model,
                "finish_reason": data.get("done_reason"),
                "usage": {
                    "type": "ACTUAL",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            },
        )
