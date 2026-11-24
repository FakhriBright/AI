from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Single source of truth for configuration. Nothing in the app reads
    os.environ directly outside this file (PRD §29) — services depend on
    this object, not on the environment.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # Market data provider abstraction (PRD §16) — value selects the
    # concrete MarketDataProvider implementation at startup.
    market_data_provider: str = "mt5_bridge"
    mt5_bridge_url: str = "http://host.docker.internal:8765"
    mt5_bridge_timeout_seconds: float = 10.0

    # AI provider abstraction (PRD §15) — value selects the concrete implementation.
    ai_provider: str = "gemini"
    ai_api_key: str = ""

    # Shared request timeout for the hosted providers (Groq, Gemini, OpenRouter).
    ai_request_timeout_seconds: float = 90.0

    # Reasoning models (Gemini 3.x, gpt-oss, many OpenRouter models) count their
    # hidden thinking against the output-token limit. This allowance is added on
    # top of the max_tokens requested by AIReasoningService so thinking cannot
    # consume the whole budget and leave the visible answer empty or truncated.
    ai_reasoning_tokens: int = 6144

    # Multi-provider selector. Users without saved AI settings keep using
    # ai_provider above. The *_models values are optional comma-separated
    # allowlists that narrow (never extend) the models discovered per key.
    ai_fallback_order: str = "groq,gemini,openrouter"
    ai_fallback_max_attempts: int = 3
    ai_provider_cooldown_seconds: int = 60
    ai_model_cache_seconds: int = 600

    # Groq provider (used when ai_provider="groq")
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_models: str = ""

    # Gemini provider. GEMINI_API_KEY is preferred; AI_API_KEY is the legacy name.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_models: str = ""

    # OpenRouter provider (OpenAI-compatible API)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = ""
    openrouter_models: str = ""

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # CORS
    cors_origins: str = "http://localhost:5173"

    log_level: str = "info"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
