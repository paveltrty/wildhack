from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from ..database import Base


class WarehouseConfig(Base):
    __tablename__ = "warehouse_config"

    warehouse_id = Column(String, primary_key=True)
    gazel_capacity = Column(Float, default=10.0)
    fura_capacity = Column(Float, default=40.0)
    lead_time_min = Column(Integer, default=60)
    safety_factor = Column(Float, default=1.05)
    alpha = Column(Float, default=0.7)
    beta = Column(Float, default=0.3)
    travel_buffer_min = Column(Integer, default=15)
    avg_route_duration_min = Column(Float, default=120.0)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
