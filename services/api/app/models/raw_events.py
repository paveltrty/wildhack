import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_id: Mapped[str] = mapped_column(String, nullable=False)
    office_from_id: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status_1: Mapped[float | None] = mapped_column(Float)
    status_2: Mapped[float | None] = mapped_column(Float)
    status_3: Mapped[float | None] = mapped_column(Float)
    status_4: Mapped[float | None] = mapped_column(Float)
    status_5: Mapped[float | None] = mapped_column(Float)
    status_6: Mapped[float | None] = mapped_column(Float)
    status_7: Mapped[float | None] = mapped_column(Float)
    status_8: Mapped[float | None] = mapped_column(Float)
    pipeline_velocity: Mapped[float | None] = mapped_column(Float)
    target_2h: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_raw_events_route_ts", "route_id", "timestamp"),
        Index("ix_raw_events_office_ts", "office_from_id", "timestamp"),
    )
