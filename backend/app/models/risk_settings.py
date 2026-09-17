import uuid

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RiskSettings(Base):
    __tablename__ = "risk_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )

    account_balance: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    risk_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    max_exposure_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    min_risk_reward: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    user: Mapped["User"] = relationship(back_populates="risk_settings")
