from typing import Literal

from pydantic import BaseModel, Field


class AIProviderInfo(BaseModel):
    id: str
    label: str
    configured: bool  # whether the server has an API key; the key itself is never returned
    default_model: str


class AIProviderModelRef(BaseModel):
    provider: str
    model: str


class AISettingsResponse(BaseModel):
    provider: str
    model: str
    model_by_provider: dict[str, str]
    auto_switch: bool
    fallback_order: list[str]
    source: Literal["user", "server_default"]
    server_default: AIProviderModelRef
    providers: list[AIProviderInfo]
    updated_at: str | None = None


class AISettingsUpdate(BaseModel):
    provider: str = Field(max_length=32)
    model_by_provider: dict[str, str]
    auto_switch: bool = False
    fallback_order: list[str] = []


class AIModelInfo(BaseModel):
    id: str
    name: str
    context_length: int | None = None
    free: bool | None = None


class AIModelListResponse(BaseModel):
    provider: str
    models: list[AIModelInfo]
    source: Literal["discovery", "configured"]
    verified: bool
    error_kind: str | None = None
    error: str | None = None


class AIConnectionTestRequest(BaseModel):
    provider: str = Field(max_length=32)
    model: str = Field(min_length=1, max_length=200)


class AIConnectionTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_ms: int | None = None
    error_kind: str | None = None
    message: str
