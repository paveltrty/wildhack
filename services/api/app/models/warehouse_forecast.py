import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WarehouseForecast(Base):
    __tablename__ = "warehouse_forecast"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    office_from_id: Mapped[str] = mapped_column(String, nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    minutes_ahead: Mapped[int] = mapped_column(Integer, nullable=False)
    y_hat: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    y_hat_low: Mapped[float | None] = mapped_column(Float)
    y_hat_high: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("run_ts", "office_from_id", "horizon", name="uq_forecast_run_office_h"),
        Index("ix_forecast_office_run", "office_from_id", "run_ts"),
    )
