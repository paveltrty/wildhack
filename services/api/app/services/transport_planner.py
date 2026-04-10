import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.transport_order import TransportOrder
from ..models.warehouse_config import WarehouseConfig
from .optimizer import RouteDispatchDecision

logger = logging.getLogger(__name__)


async def create_orders_for_warehouse(
    session: AsyncSession,
    warehouse_id: str,
    decisions: list[RouteDispatchDecision],
) -> list[TransportOrder]:
    """
    For each decision create ONE TransportOrder with the full vehicle mix.
    Deduplicates against existing drafts within ±15 min window.
    """
    cfg_result = await session.execute(
        select(WarehouseConfig).where(WarehouseConfig.warehouse_id == warehouse_id)
    )
    cfg = cfg_result.scalar_one_or_none()
    fura_cap = cfg.fura_capacity if cfg else 40.0
    gazel_cap = cfg.gazel_capacity if cfg else 10.0

    new_orders: list[TransportOrder] = []

    for decision in decisions:
        window_start = decision.scheduled_departure - timedelta(minutes=15)
        window_end = decision.scheduled_departure + timedelta(minutes=15)

        existing = await session.execute(
            select(TransportOrder.id)
            .where(TransportOrder.route_id == decision.route_id)
            .where(TransportOrder.status == "draft")
            .where(TransportOrder.scheduled_departure >= window_start)
            .where(TransportOrder.scheduled_departure <= window_end)
            .limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            logger.debug(
                "Skipping duplicate order for route %s at %s",
                decision.route_id,
                decision.scheduled_departure.isoformat(),
            )
            continue

        total_capacity = (
            decision.fura_count * fura_cap + decision.gazel_count * gazel_cap
        )

        order = TransportOrder(
            route_id=decision.route_id,
            office_from_id=decision.office_from_id,
            scheduled_departure=decision.scheduled_departure,
            fura_count=decision.fura_count,
            gazel_count=decision.gazel_count,
            capacity_units=total_capacity,
            planned_volume=decision.y_hat_future,
            chosen_horizon=decision.optimal_horizon,
            optimizer_score=decision.optimal_score,
            y_hat_future=decision.y_hat_future,
            status="draft",
        )
        session.add(order)
        new_orders.append(order)

    if new_orders:
        await session.commit()
        logger.info(
            "Created %d new draft orders for warehouse %s",
            len(new_orders),
            warehouse_id,
            extra={"warehouse_id": warehouse_id},
        )

    return new_orders
