import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AnalysisSession(Base):
    """
    The root of ownership + traceability for one analysis run (PRD §40).
    id doubles as the `analysis_id` referenced throughout the system.
    """

    __tablename__ = "analysis_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False
    )
    strategy_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_profiles.id"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # pending / data_collected / analyzed / failed
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    user: Mapped["User"] = relationship(back_populates="analysis_sessions")
    trade_plans: Mapped[list["TradePlan"]] = relationship(
        back_populates="analysis_session", cascade="all, delete-orphan"
    )
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(
        back_populates="analysis_session", cascade="all, delete-orphan"
    )


class AnalysisResult(Base):
    """AI INTERPRETATION bucket — never mixed with OBSERVED/CALCULATED data."""

    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_sessions.id"), nullable=False, index=True
    )
    ai_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_llm_response: Mapped[str] = mapped_column(Text, nullable=False)
    validated_schema_output: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # ok / repaired / failed — PRD §39: AI output must be validated, never
    # written to the DB as fact until it passes schema validation.
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    analysis_session: Mapped["AnalysisSession"] = relationship(
        back_populates="analysis_results"
    )


class TradePlan(Base):
    """
    Owned via analysis_session.user_id, not its own user_id column —
    see docs/database-boundaries.md "Ownership rule".
    """

    __tablename__ = "trade_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_sessions.id"), nullable=False, index=True
    )

    bias: Mapped[str] = mapped_column(String(16), nullable=False)  # long / short / neutral
    entry: Mapped[float | None] = mapped_column(Numeric(18, 5), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 5), nullable=True)
    take_profit_1: Mapped[float | None] = mapped_column(Numeric(18, 5), nullable=True)
    take_profit_2: Mapped[float | None] = mapped_column(Numeric(18, 5), nullable=True)
    take_profit_3: Mapped[float | None] = mapped_column(Numeric(18, 5), nullable=True)
    risk_reward_ratio: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    invalidation_condition: Mapped[str | None] = mapped_column(Text, nullable=True)

    # WAITING / TRIGGERED / INVALIDATED / EXPIRED / TP1 / TP2 / TP3 / STOPPED / CLOSED
    status: Mapped[str] = mapped_column(String(16), default="WAITING", nullable=False)
    # populated instead of an entry/SL/TP set when the plan is NO TRADE (PRD §12)
    no_trade_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    analysis_session: Mapped["AnalysisSession"] = relationship(back_populates="trade_plans")
