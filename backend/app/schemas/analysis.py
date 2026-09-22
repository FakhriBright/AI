from typing import Any

from pydantic import BaseModel


class AIAnalysisResponse(BaseModel):
    provider: str
    model: str
    analysis: str
    raw: dict[str, Any] | None = None


class AnalysisResponse(BaseModel):
    symbol: str
    generated_at_utc: str

    market_bias: dict[str, Any]
    multi_timeframe: dict[str, Any]
    key_levels: dict[str, Any]
    scenarios: dict[str, Any]

    selected_scenario: dict[str, Any]
    latest_candle: dict[str, Any]
    confirmation: dict[str, Any]

    stop_plan: dict[str, Any] | None = None
    trade_plan: dict[str, Any]

    ai: AIAnalysisResponse


class ChatMessage(BaseModel):
    role: str  # "user", "assistant", or "system"
    content: str


class AnalysisChatRequest(BaseModel):
    symbol: str
    message: str
    history: list[ChatMessage] = []
    analysis_context: dict[str, Any] | None = None


class AnalysisChatResponse(BaseModel):
    symbol: str
    reply: str
    provider: str
    model: str

