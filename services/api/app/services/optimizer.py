import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.warehouse_config import WarehouseConfig

logger = logging.getLogger(__name__)


@dataclass
class VehicleAllocation:
    fura_count: int
    gazel_count: int
    total_capacity: float
    waste: float


@dataclass
class RouteDispatchDecision:
    route_id: str
    office_from_id: str
    optimal_horizon: int
    optimal_score: float
    scores_by_horizon: dict[int, float]
    y_hat_future: float
    available_capacity: float
    fura_count: int
    gazel_count: int
    total_capacity: float
    scheduled_departure: datetime


def optimal_vehicle_mix(
    y_needed: float,
    fura_cap: float,
    gazel_cap: float,
) -> VehicleAllocation:
    """
    Find (n_fura, n_gazel) that covers y_needed with minimum wasted capacity.
    Ties broken by fewer total vehicles.
    """
    if y_needed <= 0:
        return VehicleAllocation(0, 0, 0.0, 0.0)

    max_fura = ceil(y_needed / fura_cap) if fura_cap > 0 else 0

    best_nf, best_ng = 0, 0
    best_waste = float("inf")
    best_count = float("inf")

    for nf in range(max_fura + 1):
        remaining = y_needed - nf * fura_cap
        if remaining <= 0:
            ng = 0
        elif gazel_cap > 0:
            ng = ceil(remaining / gazel_cap)
        else:
            continue

        total_cap = nf * fura_cap + ng * gazel_cap
        waste = total_cap - y_needed
        total_count = nf + ng

        if waste < best_waste or (waste == best_waste and total_count < best_count):
            best_nf, best_ng = nf, ng
            best_waste = waste
            best_count = total_count

    total_cap = best_nf * fura_cap + best_ng * gazel_cap
    return VehicleAllocation(best_nf, best_ng, total_cap, total_cap - y_needed)


async def compute_route_decision(
    session: AsyncSession,
    route_id: str,
    office_from_id: str,
    future_increments: list[float],
    confidences: list[float],
    availability: dict[int, float],
    config: WarehouseConfig,
    now: datetime,
) -> RouteDispatchDecision | None:
    """
    For each horizon h (1..10), compute business score.
    Select h* = argmax over horizons where y_h > 0.1.
    If no horizon qualifies, return None.
    """
    scores: dict[int, float] = {}
    alpha = config.alpha
    beta = config.beta

    for h in range(1, 11):
        y_h = future_increments[h - 1]
        cap_h = availability.get(h, 0.0)
        miss_risk = max(0.0, y_h - cap_h) / max(y_h, 1e-6)
        overflow = max(0.0, cap_h - y_h) / max(cap_h, 1e-6)
        biz_metric = 1.0 - (alpha * miss_risk + beta * overflow)
        scores[h] = confidences[h - 1] * biz_metric

    eligible = {h: s for h, s in scores.items() if future_increments[h - 1] > 0.1}
    if not eligible:
        return None

    h_star = max(eligible, key=eligible.get)
    y_hat = future_increments[h_star - 1]
    y_needed = y_hat * config.safety_factor

    alloc = optimal_vehicle_mix(y_needed, config.fura_capacity, config.gazel_capacity)

    scheduled_departure = now + timedelta(
        minutes=h_star * 30 - config.travel_buffer_min
    )

    decision = RouteDispatchDecision(
        route_id=route_id,
        office_from_id=office_from_id,
        optimal_horizon=h_star,
        optimal_score=scores[h_star],
        scores_by_horizon=scores,
        y_hat_future=y_hat,
        available_capacity=availability.get(h_star, 0.0),
        fura_count=alloc.fura_count,
        gazel_count=alloc.gazel_count,
        total_capacity=alloc.total_capacity,
        scheduled_departure=scheduled_departure,
    )

    parts = []
    if alloc.fura_count:
        parts.append(f"{alloc.fura_count} fura")
    if alloc.gazel_count:
        parts.append(f"{alloc.gazel_count} gazel")
    mix_str = " + ".join(parts) or "none"

    logger.info(
        "Route %s: h*=%d, score=%.3f, y_hat=%.1f, mix=%s (cap=%.1f, waste=%.1f)",
        route_id,
        h_star,
        scores[h_star],
        y_hat,
        mix_str,
        alloc.total_capacity,
        alloc.waste,
        extra={"route_id": route_id, "warehouse_id": office_from_id},
    )

    return decision
