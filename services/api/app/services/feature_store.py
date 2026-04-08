"""Build feature rows from raw_events for inference service."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_events import RawEvent

logger = logging.getLogger(__name__)

STATUS_COLS = [f"status_{i}" for i in range(1, 9)]
MAX_POINTS_PER_ROUTE = 336  # as implied by model feature requirements


async def get_actual_shipments(
    session: AsyncSession,
    office_from_id: str,
    now: datetime,
    lookback_minutes: int,
) -> float:
    """Sum pipeline_velocity across all routes for the lookback window.

    Each RawEvent row records per-30-min throughput as pipeline_velocity.
    Summing over [now - lookback, now) gives actual shipments for that period.
    """
    if lookback_minutes <= 0:
        return 0.0

    window_start = now - timedelta(minutes=lookback_minutes)

    result = await session.execute(
        select(func.coalesce(func.sum(RawEvent.pipeline_velocity), 0.0)).where(
            and_(
                RawEvent.office_from_id == office_from_id,
                RawEvent.timestamp >= window_start,
                RawEvent.timestamp < now,
            )
        )
    )
    return float(result.scalar() or 0.0)


async def get_features_for_inference(
    session: AsyncSession,
    office_from_id: str,
    run_ts: datetime,
) -> list[dict]:
    """
    Query raw_events for all routes of the warehouse.
    Pull the last 336+ timestamps per route (needed for rolling features).
    Return the full history for the inference service to compute features.
    """
    # IMPORTANT: do not ship the full raw history to inference.
    # Use a window function to take the latest N points per route.
    rn = func.row_number().over(
        partition_by=RawEvent.route_id,
        order_by=RawEvent.timestamp.desc(),
    ).label("rn")

    subq = (
        select(RawEvent, rn)
        .where(
            and_(
                RawEvent.office_from_id == office_from_id,
                RawEvent.timestamp <= run_ts,
            )
        )
        .subquery()
    )

    # Note: ordering by route_id,timestamp makes inference-side grouping stable.
    events_q = (
        select(subq)
        .where(subq.c.rn <= MAX_POINTS_PER_ROUTE)
        .order_by(subq.c.route_id, subq.c.timestamp)
    )
    result = await session.execute(events_q)
    rows_raw = result.mappings().all()
    if not rows_raw:
        return []

    rows = []
    for ev in rows_raw:
        pipeline_vel = sum(
            (ev.get(f"status_{i}") or 0) for i in range(1, 9)
        )
        rows.append({
            "route_id": ev["route_id"],
            "office_from_id": ev["office_from_id"],
            "timestamp": ev["timestamp"].isoformat(),
            "status_1": ev.get("status_1") or 0.0,
            "status_2": ev.get("status_2") or 0.0,
            "status_3": ev.get("status_3") or 0.0,
            "status_4": ev.get("status_4") or 0.0,
            "status_5": ev.get("status_5") or 0.0,
            "status_6": ev.get("status_6") or 0.0,
            "status_7": ev.get("status_7") or 0.0,
            "status_8": ev.get("status_8") or 0.0,
            "target_2h": ev.get("target_2h"),
            "pipeline_velocity": pipeline_vel,
            "hour_of_day": ev["timestamp"].hour,
            "day_of_week": ev["timestamp"].weekday(),
            "rolling_mean_2h": pipeline_vel,
            "rolling_std_2h": 0.0,
        })

    return rows
