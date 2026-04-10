import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.vehicle_state import VehicleState
from ..models.warehouse_config import WarehouseConfig

logger = logging.getLogger(__name__)


async def get_availability_profile(
    session: AsyncSession,
    warehouse_id: str,
    now: datetime,
) -> dict[int, float]:
    """
    For each horizon h in 1..10:
      available_capacity(h) = free_gazel(h)*gazel_cap + free_fura(h)*fura_cap
    where free(h) = currently free + vehicles returning by now + h*30min.
    """
    cfg_result = await session.execute(
        select(WarehouseConfig).where(WarehouseConfig.warehouse_id == warehouse_id)
    )
    cfg = cfg_result.scalar_one_or_none()
    gazel_cap = cfg.gazel_capacity if cfg else 10.0
    fura_cap = cfg.fura_capacity if cfg else 40.0

    free_gazel_q = await session.execute(
        select(func.count())
        .where(VehicleState.warehouse_id == warehouse_id)
        .where(VehicleState.vehicle_type == "gazel")
        .where(VehicleState.status == "free")
    )
    free_gazel = free_gazel_q.scalar() or 0

    free_fura_q = await session.execute(
        select(func.count())
        .where(VehicleState.warehouse_id == warehouse_id)
        .where(VehicleState.vehicle_type == "fura")
        .where(VehicleState.status == "free")
    )
    free_fura = free_fura_q.scalar() or 0

    profile: dict[int, float] = {}
    for h in range(1, 11):
        delta = timedelta(minutes=h * 30)
        horizon_ts = now + delta

        returning_gazel_q = await session.execute(
            select(func.count())
            .where(VehicleState.warehouse_id == warehouse_id)
            .where(VehicleState.vehicle_type == "gazel")
            .where(VehicleState.status == "busy")
            .where(VehicleState.eta_return <= horizon_ts)
        )
        returning_gazel = returning_gazel_q.scalar() or 0

        returning_fura_q = await session.execute(
            select(func.count())
            .where(VehicleState.warehouse_id == warehouse_id)
            .where(VehicleState.vehicle_type == "fura")
            .where(VehicleState.status == "busy")
            .where(VehicleState.eta_return <= horizon_ts)
        )
        returning_fura = returning_fura_q.scalar() or 0

        avail_gazel = free_gazel + returning_gazel
        avail_fura = free_fura + returning_fura
        profile[h] = avail_gazel * gazel_cap + avail_fura * fura_cap

    return profile


async def dispatch_vehicles(
    session: AsyncSession,
    warehouse_id: str,
    vehicle_type: str,
    count: int,
    now: datetime,
) -> list[UUID]:
    """
    Pick `count` free vehicles of given type from warehouse pool.
    Set status='busy', dispatched_at=now, eta_return = now + avg_route_duration_min.
    """
    cfg_result = await session.execute(
        select(WarehouseConfig).where(WarehouseConfig.warehouse_id == warehouse_id)
    )
    cfg = cfg_result.scalar_one_or_none()
    duration_min = cfg.avg_route_duration_min if cfg else 120.0

    result = await session.execute(
        select(VehicleState.id)
        .where(VehicleState.warehouse_id == warehouse_id)
        .where(VehicleState.vehicle_type == vehicle_type)
        .where(VehicleState.status == "free")
        .limit(count)
    )
    vehicle_ids = [row[0] for row in result.all()]

    if len(vehicle_ids) < count:
        raise ValueError(
            f"Insufficient free {vehicle_type} vehicles at {warehouse_id}: "
            f"need {count}, have {len(vehicle_ids)}"
        )

    eta = now + timedelta(minutes=duration_min)
    await session.execute(
        update(VehicleState)
        .where(VehicleState.id.in_(vehicle_ids))
        .values(
            status="busy",
            dispatched_at=now,
            eta_return=eta,
            updated_at=now,
        )
    )
    await session.commit()

    logger.info(
        "Dispatched %d %s vehicles from %s, ETA return %s",
        count,
        vehicle_type,
        warehouse_id,
        eta.isoformat(),
        extra={"warehouse_id": warehouse_id},
    )
    return vehicle_ids


async def return_vehicle(session: AsyncSession, vehicle_id: UUID) -> None:
    """Set status='free', clear dispatched_at, eta_return."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(VehicleState)
        .where(VehicleState.id == vehicle_id)
        .values(
            status="free",
            dispatched_at=None,
            eta_return=None,
            updated_at=now,
        )
    )
    await session.commit()
    logger.info("Vehicle %s returned to free", vehicle_id)


async def release_vehicles(
    session: AsyncSession,
    warehouse_id: str,
    vehicle_type: str,
    count: int,
) -> int:
    """
    Free `count` busy vehicles of given type at warehouse.
    Returns actual number freed.
    """
    if count <= 0:
        return 0

    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(VehicleState.id)
        .where(VehicleState.warehouse_id == warehouse_id)
        .where(VehicleState.vehicle_type == vehicle_type)
        .where(VehicleState.status == "busy")
        .limit(count)
    )
    ids = [row[0] for row in result.all()]

    if ids:
        await session.execute(
            update(VehicleState)
            .where(VehicleState.id.in_(ids))
            .values(status="free", dispatched_at=None, eta_return=None, updated_at=now)
        )

    logger.info(
        "Released %d/%d %s vehicles at %s",
        len(ids), count, vehicle_type, warehouse_id,
    )
    return len(ids)


async def return_overdue_vehicles(session: AsyncSession) -> int:
    """Free all busy vehicles whose eta_return has passed."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(VehicleState.id)
        .where(VehicleState.status == "busy")
        .where(VehicleState.eta_return <= now)
    )
    ids = [row[0] for row in result.all()]

    if ids:
        await session.execute(
            update(VehicleState)
            .where(VehicleState.id.in_(ids))
            .values(status="free", dispatched_at=None, eta_return=None, updated_at=now)
        )
        await session.commit()
        logger.info("Auto-returned %d overdue vehicles", len(ids))

    return len(ids)
