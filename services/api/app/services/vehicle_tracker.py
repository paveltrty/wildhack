"""Vehicle availability tracking and dispatch management."""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle_state import VehicleState
from app.models.route_metadata import RouteMetadata
from app.models.warehouse_config import WarehouseConfig

logger = logging.getLogger(__name__)

async def assign_free_vehicles_to_routes(
    session: AsyncSession,
    warehouse_id: str,
    *,
    ensure_all_routes: bool = True,
) -> dict:
    """
    Simple (deterministic) assignment so that routes are "utilized" even without dispatch logic.
    - Picks routes for the warehouse from route_metadata.
    - Assigns free vehicles with route_id IS NULL round-robin across routes.
    - If ensure_all_routes=True and free vehicles >= routes, guarantees at least 1 per route.
    """
    routes_q = (
        select(RouteMetadata.route_id)
        .where(RouteMetadata.office_from_id == warehouse_id)
        .order_by(RouteMetadata.route_id.asc())
    )
    result = await session.execute(routes_q)
    routes = [r[0] for r in result.fetchall()]
    if not routes:
        return {"warehouse_id": warehouse_id, "routes_total": 0, "assigned": 0}

    if ensure_all_routes:
        # If we don't have enough vehicles to cover routes, create extra demo vehicles (gazel)
        # so that every route can be utilized.
        existing_cnt_res = await session.execute(
            select(func.count(VehicleState.id)).where(VehicleState.warehouse_id == warehouse_id)
        )
        existing_cnt = int(existing_cnt_res.scalar() or 0)
        need = max(0, len(routes) - existing_cnt)
        # safety cap to avoid runaway creation
        need = min(need, 2000)
        if need > 0:
            for _ in range(need):
                session.add(
                    VehicleState(
                        warehouse_id=warehouse_id,
                        vehicle_type="gazel",
                        status="free",
                        route_id=None,
                    )
                )
            await session.commit()

    veh_q = (
        select(VehicleState)
        .where(
            and_(
                VehicleState.warehouse_id == warehouse_id,
                VehicleState.status == "free",
                VehicleState.route_id.is_(None),
            )
        )
        .order_by(VehicleState.id.asc())
    )
    result = await session.execute(veh_q)
    free = result.scalars().all()
    if not free:
        return {"warehouse_id": warehouse_id, "routes_total": len(routes), "assigned": 0}

    assigned = 0
    # Round-robin assignment.
    for idx, v in enumerate(free):
        v.route_id = routes[idx % len(routes)]
        assigned += 1

    await session.commit()
    return {"warehouse_id": warehouse_id, "routes_total": len(routes), "assigned": assigned}


async def get_availability_profile(
    session: AsyncSession,
    warehouse_id: str,
    now: datetime,
    horizons: int = 10,
) -> dict[int, float]:
    """
    Returns {horizon: available_capacity} for horizons 1..10.
    Capacity = (free_count + vehicles_returning_by_that_horizon) * vehicle_capacity
    """
    config_q = select(WarehouseConfig).where(WarehouseConfig.warehouse_id == warehouse_id)
    result = await session.execute(config_q)
    config = result.scalar_one_or_none()
    if config is None:
        gazel_cap = 10.0
        fura_cap = 40.0
    else:
        gazel_cap = config.gazel_capacity
        fura_cap = config.fura_capacity

    vehicles_q = select(VehicleState).where(VehicleState.warehouse_id == warehouse_id)
    result = await session.execute(vehicles_q)
    vehicles = result.scalars().all()

    profile: dict[int, float] = {}
    for h in range(1, horizons + 1):
        horizon_time = now + timedelta(minutes=h * 30)
        capacity = 0.0
        for v in vehicles:
            cap = gazel_cap if v.vehicle_type == "gazel" else fura_cap
            if v.status == "free":
                capacity += cap
            elif v.status == "busy" and v.eta_return and v.eta_return <= horizon_time:
                capacity += cap
        profile[h] = capacity

    return profile


async def dispatch_vehicle(
    session: AsyncSession,
    vehicle_id: uuid.UUID,
    route_id: str,
    now: datetime,
) -> VehicleState | None:
    """Set status=busy, compute eta_return from route_metadata.avg_duration_min."""
    result = await session.execute(select(VehicleState).where(VehicleState.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        return None

    route_q = select(RouteMetadata).where(RouteMetadata.route_id == route_id)
    result = await session.execute(route_q)
    route = result.scalar_one_or_none()
    duration_min = route.avg_duration_min if route else 120.0

    config_q = select(WarehouseConfig).where(WarehouseConfig.warehouse_id == vehicle.warehouse_id)
    result = await session.execute(config_q)
    config = result.scalar_one_or_none()
    buffer_min = config.travel_buffer_min if config else 15

    vehicle.status = "busy"
    vehicle.route_id = route_id
    vehicle.dispatched_at = now
    vehicle.eta_return = now + timedelta(minutes=duration_min + buffer_min)

    await session.commit()
    logger.info("Dispatched vehicle %s on route %s, ETA return %s", vehicle_id, route_id, vehicle.eta_return)
    return vehicle


async def return_vehicle(
    session: AsyncSession,
    vehicle_id: uuid.UUID,
) -> VehicleState | None:
    """Set status=free, clear route_id and eta_return."""
    result = await session.execute(select(VehicleState).where(VehicleState.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        return None

    vehicle.status = "free"
    vehicle.route_id = None
    vehicle.dispatched_at = None
    vehicle.eta_return = None

    await session.commit()
    logger.info("Returned vehicle %s", vehicle_id)
    return vehicle
