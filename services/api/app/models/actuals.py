import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base


class Actual(Base):
    __tablename__ = "actuals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_id = Column(String, nullable=False)
    office_from_id = Column(String, nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    shipments = Column(Float, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("route_id", "window_start", name="uq_actuals_route_window"),
        Index("ix_actuals_route_window", "route_id", window_start.desc()),
    )
