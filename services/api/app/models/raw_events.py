from sqlalchemy import Column, DateTime, Float, Index, String, UniqueConstraint
from ..database import Base


class RawEvent(Base):
    __tablename__ = "raw_events"

    route_id = Column(String, primary_key=True)
    timestamp = Column(DateTime(timezone=True), primary_key=True)
    office_from_id = Column(String, nullable=False)
    status_1 = Column(Float)
    status_2 = Column(Float)
    status_3 = Column(Float)
    status_4 = Column(Float)
    status_5 = Column(Float)
    status_6 = Column(Float)
    status_7 = Column(Float)
    status_8 = Column(Float)
    pipeline_velocity = Column(Float)
    target_2h = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("route_id", "timestamp", name="uq_raw_events_route_ts"),
        Index("ix_raw_events_office_ts", "office_from_id", timestamp.desc()),
    )
