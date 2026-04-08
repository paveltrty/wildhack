import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TransportOrder(Base):
    __tablename__ = "transport_order"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_departure: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String, nullable=False)
    vehicle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity_units: Mapped[float] = mapped_column(Float, nullable=False)
    chosen_horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    optimizer_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_order_warehouse_departure", "warehouse_id", "scheduled_departure"),
        Index("ix_order_status", "status"),
    )
