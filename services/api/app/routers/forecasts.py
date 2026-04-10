import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.route_forecast import RouteForecast

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/forecasts")
async def get_forecasts(
    route_id: Optional[str] = Query(None),
    office_from_id: Optional[str] = Query(None),
    run_ts: Optional[datetime] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    q = select(RouteForecast)

    if route_id:
        q = q.where(RouteForecast.route_id == route_id)
    if office_from_id:
        q = q.where(RouteForecast.office_from_id == office_from_id)

    if run_ts:
        q = q.where(RouteForecast.run_ts == run_ts)
    else:
        if route_id:
            latest_ts_q = (
                select(RouteForecast.run_ts)
                .where(RouteForecast.route_id == route_id)
                .order_by(RouteForecast.run_ts.desc())
                .limit(1)
            )
            result = await session.execute(latest_ts_q)
            latest = result.scalar_one_or_none()
            if latest:
                q = q.where(RouteForecast.run_ts == latest)

    q = q.order_by(RouteForecast.run_ts.desc(), RouteForecast.horizon)
    result = await session.execute(q)
    rows = result.scalars().all()

    return [
        {
            "id": str(r.id),
            "route_id": r.route_id,
            "office_from_id": r.office_from_id,
            "run_ts": r.run_ts.isoformat(),
            "horizon": r.horizon,
            "y_hat_raw": r.y_hat_raw,
            "y_hat_future": r.y_hat_future,
            "confidence": r.confidence,
            "y_hat_low": r.y_hat_low,
            "y_hat_high": r.y_hat_high,
        }
        for r in rows
    ]
