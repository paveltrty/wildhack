from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WarehouseConfig(Base):
    __tablename__ = "warehouse_config"

    warehouse_id: Mapped[str] = mapped_column(String, primary_key=True)
    gazel_capacity: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    fura_capacity: Mapped[float] = mapped_column(Float, nullable=False, default=40.0)
    lead_time_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    safety_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.05)
    alpha: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    beta: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    travel_buffer_min: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
