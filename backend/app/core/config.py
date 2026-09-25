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

    # Groq provider (used when ai_provider="groq")
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

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
