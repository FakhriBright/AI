import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIProviderSettings(Base):
    """Per-user AI provider/model selection. API keys are never stored here."""

    __tablename__ = "ai_provider_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # Chosen model per provider, e.g. {"groq": "...", "openrouter": "..."}.
    # The active model is model_by_provider[provider]; the others are used
    # when Auto Switch falls back to that provider.
    model_by_provider: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    auto_switch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_order: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
