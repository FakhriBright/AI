from typing import Any

import httpx

from app.core.config import settings
from app.services.ai.base import AIResponse
from app.services.ai.errors import AIProviderConfigError, AIProviderHTTPError


def _error_message(response: httpx.Response) -> str:
    try:
        error = response.json().get("error") or {}
        return str(error.get("message") or "")
    except Exception:
        return ""


class OpenRouterAIProvider:

    def __init__(self, model: str | None = None):
        if not settings.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not configured. "
                "Set the OPENROUTER_API_KEY environment variable to use the OpenRouter provider."
            )

        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url.rstrip("/")
        self.timeout = settings.ai_request_timeout_seconds

        self.provider = "openrouter"
        self.model = model or settings.openrouter_model
        if not self.model:
            raise AIProviderConfigError(
                "No OpenRouter model selected. Pick one in the dashboard or set OPENROUTER_MODEL."
            )

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

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
            "temperature": 0.3,
        }

        max_tokens = context.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0:
            payload["max_tokens"] = max_tokens + max(0, settings.ai_reasoning_tokens)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )

        if response.status_code >= 400:
            raise AIProviderHTTPError("openrouter", response.status_code, _error_message(response))

        data = response.json()

        # OpenRouter can answer 200 with an error object (e.g. upstream failure).
        if data.get("error") and not data.get("choices"):
            error = data["error"] or {}
            code = error.get("code")
            raise AIProviderHTTPError(
                "openrouter",
                code if isinstance(code, int) else 502,
                str(error.get("message") or ""),
            )

        choice = data["choices"][0]
        analysis = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)

        return AIResponse(
            provider="openrouter",
            model=data.get("model") or self.model,
            analysis=analysis,
            raw={
                "id": data.get("id"),
                "model": data.get("model") or self.model,
                "finish_reason": choice.get("finish_reason"),
                "usage": {
                    "type": "ACTUAL" if usage else "ESTIMATED",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
                },
            },
        )
