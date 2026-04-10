import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.raw_events import RawEvent

logger = logging.getLogger(__name__)


async def get_features(
    session: AsyncSession,
    warehouse_id: str,
    now: datetime,
) -> list[dict]:
    """
    Build feature rows for each route belonging to the warehouse.
    Returns one feature dict per route (the latest raw_events row per route
    within the last 2 hours), enriched with derived features.
    """
    cutoff = now - timedelta(hours=2)

    latest_subq = (
        select(
            RawEvent.route_id,
            RawEvent.office_from_id,
            RawEvent.timestamp,
            RawEvent.status_1,
            RawEvent.status_2,
            RawEvent.status_3,
            RawEvent.status_4,
            RawEvent.status_5,
            RawEvent.status_6,
            RawEvent.status_7,
            RawEvent.status_8,
            RawEvent.pipeline_velocity,
        )
        .where(RawEvent.office_from_id == warehouse_id)
        .where(RawEvent.timestamp >= cutoff)
        .order_by(RawEvent.route_id, RawEvent.timestamp.desc())
        .distinct(RawEvent.route_id)
        .subquery()
    )

    result = await session.execute(select(latest_subq))
    rows = result.all()

    if not rows:
        logger.warning(
            "No recent events for warehouse %s since %s",
            warehouse_id,
            cutoff.isoformat(),
        )
        return []

    features: list[dict] = []
    for row in rows:
        velocity = row.pipeline_velocity or sum(
            getattr(row, f"status_{i}", 0) or 0 for i in range(1, 9)
        )

        rolling_rows_result = await session.execute(
            select(RawEvent.pipeline_velocity)
            .where(RawEvent.route_id == row.route_id)
            .where(RawEvent.timestamp <= row.timestamp)
            .where(RawEvent.timestamp >= row.timestamp - timedelta(hours=2))
            .order_by(RawEvent.timestamp.desc())
            .limit(4)
        )
        rolling_values = [r[0] or 0.0 for r in rolling_rows_result.all()]

        rolling_mean = sum(rolling_values) / max(len(rolling_values), 1)
        rolling_std = (
            (sum((v - rolling_mean) ** 2 for v in rolling_values) / max(len(rolling_values), 1))
            ** 0.5
            if len(rolling_values) > 1
            else 0.0
        )

        ts = row.timestamp
        features.append(
            {
                "route_id": row.route_id,
                "office_from_id": row.office_from_id,
                "timestamp": ts.isoformat(),
                "status_1": row.status_1 or 0.0,
                "status_2": row.status_2 or 0.0,
                "status_3": row.status_3 or 0.0,
                "status_4": row.status_4 or 0.0,
                "status_5": row.status_5 or 0.0,
                "status_6": row.status_6 or 0.0,
                "status_7": row.status_7 or 0.0,
                "status_8": row.status_8 or 0.0,
                "pipeline_velocity": velocity,
                "hour_of_day": ts.hour,
                "day_of_week": ts.weekday(),
                "rolling_mean_2h": rolling_mean,
                "rolling_std_2h": rolling_std,
            }
        )

    logger.info(
        "Built %d feature rows for warehouse %s",
        len(features),
        warehouse_id,
    )
    return features
