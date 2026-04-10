from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, String

from ..database import Base


class RouteMetadata(Base):
    __tablename__ = "route_metadata"

    route_id = Column(String, primary_key=True)
    office_from_id = Column(String, nullable=False)
    avg_duration_min = Column(Float, nullable=False, default=120.0)
    stddev_duration_min = Column(Float, default=15.0)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
