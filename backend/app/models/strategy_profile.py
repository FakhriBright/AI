import uuid

from sqlalchemy import ARRAY, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyProfile(Base):
    __tablename__ = "strategy_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # scalping / intraday / swing
    timeframes: Mapped[list[str]] = mapped_column(ARRAY(String(8)), nullable=False)
    min_risk_reward: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    news_sensitivity: Mapped[str] = mapped_column(String(16), nullable=False)  # low / medium / high
    holding_period_description: Mapped[str] = mapped_column(String(128), nullable=False)
