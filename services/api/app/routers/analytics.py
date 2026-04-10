import logging
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.route_forecast import RouteForecast
from ..services.metrics_collector import (
    compute_all_routes_summary,
    compute_metrics,
    compute_route_metrics,
    compute_system_metrics,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/analytics/metrics")
async def get_metrics(
    warehouse_id: str = Query(...),
    period_days: int = Query(7),
    session: AsyncSession = Depends(get_session),
):
    metrics = await compute_metrics(session, warehouse_id, period_days)
    return asdict(metrics)


@router.get("/analytics/system")
async def get_system_metrics(
    period_days: int = Query(7),
    session: AsyncSession = Depends(get_session),
):
    metrics = await compute_system_metrics(session, period_days)
    return asdict(metrics)


@router.get("/analytics/route-metrics")
async def get_route_metrics(
    route_id: str = Query(...),
    period_days: int = Query(7),
    session: AsyncSession = Depends(get_session),
):
    metrics = await compute_route_metrics(session, route_id, period_days)
    return asdict(metrics)


@router.get("/analytics/routes-summary")
async def get_routes_summary(
    period_days: int = Query(7),
    session: AsyncSession = Depends(get_session),
):
    return await compute_all_routes_summary(session, period_days)


@router.get("/analytics/score-profile")
async def get_score_profile(
    route_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    from ..models.transport_order import TransportOrder

    result = await session.execute(
        select(TransportOrder)
        .where(TransportOrder.route_id == route_id)
        .order_by(TransportOrder.created_at.desc())
        .limit(20)
    )
    orders = result.scalars().all()

    profiles = []
    for order in orders:
        forecasts_q = await session.execute(
            select(RouteForecast)
            .where(RouteForecast.route_id == route_id)
            .where(RouteForecast.run_ts <= order.created_at)
            .order_by(RouteForecast.run_ts.desc())
            .limit(10)
        )
        forecasts = forecasts_q.scalars().all()

        scores_by_horizon = {}
        for f in forecasts:
            scores_by_horizon[f.horizon] = {
                "y_hat_future": f.y_hat_future,
                "confidence": f.confidence,
            }

        profiles.append(
            {
                "order_id": str(order.id),
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "chosen_horizon": order.chosen_horizon,
                "optimizer_score": order.optimizer_score,
                "y_hat_future": order.y_hat_future,
                "scores_by_horizon": scores_by_horizon,
            }
        )

    return profiles
