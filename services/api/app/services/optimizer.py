"""Dispatch optimization: score horizons, pick optimal, compute vehicle needs."""

import logging
import math
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.models.warehouse_config import WarehouseConfig

logger = logging.getLogger(__name__)


class DispatchDecision(BaseModel):
    optimal_horizon: int
    optimal_score: float
    scores_by_horizon: dict[int, float]
    vehicles_needed: int
    extra_needed: int
    scheduled_departure: datetime
    y_hat: float
    available_capacity: float


async def compute_dispatch_decision(
    session,
    warehouse_id: str,
    forecasts: list[dict],
    availability: dict[int, float],
    config: WarehouseConfig,
) -> DispatchDecision:
    """
    For each horizon h in 1..10:
      utilization_h  = y_hat_h / availability[h]
      miss_risk_h    = max(0, y_hat_h - availability[h]) / y_hat_h
      overflow_h     = max(0, availability[h] - y_hat_h) / availability[h]
      biz_metric_h   = 1 - (alpha * miss_risk_h + beta * overflow_h)
      score_h        = confidence * biz_metric_h

    Pick h* = argmax(score_h)
    """
    scores: dict[int, float] = {}
    best_h = 1
    best_score = -float("inf")

    for fc in forecasts:
        h = fc["horizon"]
        y_hat = fc["y_hat"]
        confidence = fc["confidence"]
        avail = availability.get(h, 0.0)

        if avail <= 0:
            miss_risk = 1.0
            overflow = 0.0
        elif y_hat <= 0:
            miss_risk = 0.0
            overflow = 1.0
        else:
            miss_risk = max(0.0, y_hat - avail) / y_hat
            overflow = max(0.0, avail - y_hat) / avail

        biz_metric = 1.0 - (config.alpha * miss_risk + config.beta * overflow)
        score = confidence * biz_metric
        scores[h] = round(score, 4)

        if score > best_score:
            best_score = score
            best_h = h

    best_forecast = next((fc for fc in forecasts if fc["horizon"] == best_h), forecasts[0])
    y_hat_star = best_forecast["y_hat"]
    avail_star = availability.get(best_h, 0.0)

    vehicle_capacity = config.fura_capacity
    vehicles_needed = math.ceil((y_hat_star * config.safety_factor) / vehicle_capacity) if vehicle_capacity > 0 else 0

    from sqlalchemy import select, func as sqlfunc
    from app.models.vehicle_state import VehicleState
    result = await session.execute(
        select(sqlfunc.count()).where(
            VehicleState.warehouse_id == warehouse_id,
            VehicleState.status == "free",
        )
    )
    free_count = result.scalar() or 0
    extra_needed = max(0, vehicles_needed - free_count)

    scheduled = datetime.utcnow() + timedelta(minutes=best_h * 30)

    return DispatchDecision(
        optimal_horizon=best_h,
        optimal_score=round(best_score, 4),
        scores_by_horizon=scores,
        vehicles_needed=vehicles_needed,
        extra_needed=extra_needed,
        scheduled_departure=scheduled,
        y_hat=round(y_hat_star, 4),
        available_capacity=round(avail_star, 4),
    )
