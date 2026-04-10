import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base


class TransportOrder(Base):
    __tablename__ = "transport_order"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_id = Column(String, nullable=False)
    office_from_id = Column(String, nullable=False)
    scheduled_departure = Column(DateTime(timezone=True), nullable=False)

    # Legacy single-type fields (nullable for backward compat)
    vehicle_type = Column(String, nullable=True)
    vehicle_count = Column(Integer, nullable=True)

    fura_count = Column(Integer, nullable=False, default=0, server_default="0")
    gazel_count = Column(Integer, nullable=False, default=0, server_default="0")

    capacity_units = Column(Float, nullable=False)
    planned_volume = Column(Float, nullable=True)

    chosen_horizon = Column(Integer, nullable=False)
    optimizer_score = Column(Float, nullable=False)
    y_hat_future = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="draft")
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_order_office_departure", "office_from_id", "scheduled_departure"),
        Index("ix_order_route_status", "route_id", "status"),
    )
