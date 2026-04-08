"""Forecast retrieval endpoints."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models.warehouse_forecast import WarehouseForecast

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/forecasts")
async def get_forecasts(
    warehouse_id: str = Query(...),
    from_ts: datetime | None = Query(None),
    to_ts: datetime | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    conditions = [WarehouseForecast.office_from_id == warehouse_id]
    if from_ts:
        conditions.append(WarehouseForecast.run_ts >= from_ts)
    if to_ts:
        conditions.append(WarehouseForecast.run_ts <= to_ts)

    q = (
        select(WarehouseForecast)
        .where(and_(*conditions))
        .order_by(desc(WarehouseForecast.run_ts), WarehouseForecast.horizon)
    )
    result = await session.execute(q)
    forecasts = result.scalars().all()

    optimizer_scores = None
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        cached = await r.get(f"optimizer:latest:{warehouse_id}")
        if cached:
            optimizer_scores = json.loads(cached)
        await r.aclose()
    except Exception:
        logger.debug("Redis not available for optimizer scores")

    return {
        "forecasts": [
            {
                "id": str(f.id),
                "run_ts": f.run_ts.isoformat(),
                "office_from_id": f.office_from_id,
                "horizon": f.horizon,
                "minutes_ahead": f.minutes_ahead,
                "y_hat": f.y_hat,
                "confidence": f.confidence,
                "y_hat_low": f.y_hat_low,
                "y_hat_high": f.y_hat_high,
            }
            for f in forecasts
        ],
        "optimizer_scores": optimizer_scores,
    }
