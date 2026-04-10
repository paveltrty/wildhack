import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base


class VehicleState(Base):
    __tablename__ = "vehicle_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id = Column(String, nullable=False)
    vehicle_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="free")
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    eta_return = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_vehicle_warehouse_status", "warehouse_id", "status"),
    )
