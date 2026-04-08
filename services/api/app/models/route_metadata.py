from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RouteMetadata(Base):
    __tablename__ = "route_metadata"

    route_id: Mapped[str] = mapped_column(String, primary_key=True)
    office_from_id: Mapped[str] = mapped_column(String, nullable=False)
    avg_duration_min: Mapped[float] = mapped_column(Float, nullable=False)
    stddev_duration_min: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
