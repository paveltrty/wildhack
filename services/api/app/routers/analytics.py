"""Analytics and metrics endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.services.metrics_collector import compute_business_metrics

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/analytics/metrics")
async def get_metrics(
    warehouse_id: str = Query(...),
    period_days: int = Query(7),
    session: AsyncSession = Depends(get_session),
):
    metrics = await compute_business_metrics(session, warehouse_id, period_days)
    return {
        "metrics": metrics.model_dump(),
        "period_days": period_days,
        "warehouse_id": warehouse_id,
    }


@router.get("/analytics/score-profile")
async def get_score_profile(
    warehouse_id: str = Query(...),
):
    """Return last 20 optimizer decisions with scores_by_horizon."""
    decisions = []
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        cached = await r.get(f"optimizer:latest:{warehouse_id}")
        if cached:
            decision = json.loads(cached)
            decisions.append(decision)
        history_key = f"optimizer:history:{warehouse_id}"
        history = await r.lrange(history_key, 0, 19)
        for item in history:
            decisions.append(json.loads(item))
        await r.aclose()
    except Exception:
        logger.debug("Redis not available for score profile")

    return {"decisions": decisions, "warehouse_id": warehouse_id}
