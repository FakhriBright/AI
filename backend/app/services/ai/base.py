from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class AIResponse:
    provider: str
    model: str
    analysis: str
    raw: dict[str, Any] | None = None


class AIProvider(Protocol):

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:
        ...

