import uuid

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base


class RouteForecast(Base):
    __tablename__ = "route_forecast"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_id = Column(String, nullable=False)
    office_from_id = Column(String, nullable=False)
    run_ts = Column(DateTime(timezone=True), nullable=False)
    horizon = Column(Integer, nullable=False)
    y_hat_raw = Column(Float, nullable=False)
    y_hat_future = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    y_hat_low = Column(Float, nullable=True)
    y_hat_high = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("route_id", "run_ts", "horizon", name="uq_forecast_route_run_h"),
        Index("ix_forecast_route_run", "route_id", run_ts.desc()),
        Index("ix_forecast_office_run", "office_from_id", run_ts.desc()),
    )
