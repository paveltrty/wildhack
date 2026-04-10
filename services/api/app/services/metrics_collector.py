import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.actuals import Actual
from ..models.route_metadata import RouteMetadata
from ..models.transport_order import TransportOrder
from ..models.warehouse_config import WarehouseConfig

logger = logging.getLogger(__name__)


@dataclass
class BusinessMetrics:
    warehouse_id: str
    period_days: int
    fleet_utilization_rate: float = 0.0
    miss_rate: float = 0.0
    idle_vehicle_rate: float = 0.0
    return_eta_error_min: float = 0.0
    forecast_mae: float = 0.0
    naive_mae: float = 0.0
    orders_total: int = 0
    orders_completed: int = 0


@dataclass
class SystemMetrics:
    period_days: int
    orders_total: int = 0
    orders_completed: int = 0
    orders_approved: int = 0
    orders_draft: int = 0
    fleet_utilization_rate: float = 0.0
    miss_rate: float = 0.0
    idle_vehicle_rate: float = 0.0
    total_shipments: float = 0.0
    total_capacity: float = 0.0
    avg_planned_volume: float = 0.0
    avg_actual_shipments: float = 0.0
    warehouse_breakdown: list = field(default_factory=list)
    orders_by_day: list = field(default_factory=list)
    forecast_mae: float = 0.0
    naive_mae: float = 0.0


@dataclass
class RouteMetrics:
    route_id: str
    office_from_id: str
    period_days: int
    orders_total: int = 0
    orders_completed: int = 0
    avg_planned_volume: float = 0.0
    avg_actual_shipments: float = 0.0
    avg_capacity_units: float = 0.0
    utilization_rate: float = 0.0
    miss_rate: float = 0.0
    idle_rate: float = 0.0
    forecast_mae: float = 0.0
    shipments_history: list = field(default_factory=list)


async def _compute_order_stats(session, orders):
    """Shared logic for fleet utilization / miss / idle from completed orders."""
    total_actual = 0.0
    total_capacity = 0.0
    miss_count = 0
    idle_count = 0
    actual_values = []

    for order in orders:
        actual_q = await session.execute(
            select(Actual.shipments)
            .where(Actual.route_id == order.route_id)
            .where(Actual.window_start >= order.scheduled_departure - timedelta(minutes=30))
            .where(Actual.window_start <= order.scheduled_departure + timedelta(minutes=30))
            .limit(1)
        )
        actual_val = actual_q.scalar_one_or_none()

        if actual_val is not None:
            total_actual += actual_val
            total_capacity += order.capacity_units
            actual_values.append(actual_val)
            if actual_val > order.capacity_units:
                miss_count += 1
            if actual_val < 0.5 * order.capacity_units:
                idle_count += 1

    n = len(orders)
    utilization = total_actual / total_capacity if total_capacity > 0 else 0.0
    miss = miss_count / n if n > 0 else 0.0
    idle = idle_count / n if n > 0 else 0.0
    return utilization, miss, idle, total_actual, total_capacity, actual_values


def _proposal_vs_actual_mae_query(cutoff: datetime):
    """
    MAE между прогнозом из черновика (y_hat_future на заявке) и фактом отгрузки (actuals),
    только для завершённых заявок с сопоставимой записью actuals.
    """
    win_lo = TransportOrder.scheduled_departure - timedelta(minutes=30)
    win_hi = TransportOrder.scheduled_departure + timedelta(minutes=30)
    return (
        select(func.avg(func.abs(TransportOrder.y_hat_future - Actual.shipments)))
        .select_from(TransportOrder)
        .join(
            Actual,
            (TransportOrder.route_id == Actual.route_id)
            & (Actual.window_start >= win_lo)
            & (Actual.window_start <= win_hi),
        )
        .where(TransportOrder.status == "completed")
        .where(TransportOrder.created_at >= cutoff)
    )


async def compute_metrics(
    session: AsyncSession,
    warehouse_id: str,
    period_days: int = 7,
) -> BusinessMetrics:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=period_days)

    metrics = BusinessMetrics(warehouse_id=warehouse_id, period_days=period_days)

    total_q = await session.execute(
        select(func.count())
        .select_from(TransportOrder)
        .where(TransportOrder.office_from_id == warehouse_id)
        .where(TransportOrder.created_at >= cutoff)
    )
    metrics.orders_total = total_q.scalar() or 0

    completed_q = await session.execute(
        select(func.count())
        .select_from(TransportOrder)
        .where(TransportOrder.office_from_id == warehouse_id)
        .where(TransportOrder.status == "completed")
        .where(TransportOrder.created_at >= cutoff)
    )
    metrics.orders_completed = completed_q.scalar() or 0

    if metrics.orders_completed > 0:
        completed_orders = await session.execute(
            select(TransportOrder)
            .where(TransportOrder.office_from_id == warehouse_id)
            .where(TransportOrder.status == "completed")
            .where(TransportOrder.created_at >= cutoff)
        )
        orders = completed_orders.scalars().all()

        util, miss, idle, _, _, _ = await _compute_order_stats(session, orders)
        metrics.fleet_utilization_rate = util
        metrics.miss_rate = miss
        metrics.idle_vehicle_rate = idle

    mae_q = await session.execute(
        _proposal_vs_actual_mae_query(cutoff).where(
            TransportOrder.office_from_id == warehouse_id
        )
    )
    mae_val = mae_q.scalar()
    metrics.forecast_mae = float(mae_val) if mae_val is not None else 0.0

    naive_q = await session.execute(
        select(
            func.avg(
                func.abs(
                    Actual.shipments
                    - select(Actual.shipments)
                    .where(Actual.route_id == Actual.route_id)
                    .correlate(Actual)
                    .scalar_subquery()
                )
            )
        )
        .where(Actual.office_from_id == warehouse_id)
        .where(Actual.created_at >= cutoff)
    )
    naive_val = naive_q.scalar()
    metrics.naive_mae = float(naive_val) if naive_val else 0.0

    return metrics


async def compute_system_metrics(
    session: AsyncSession,
    period_days: int = 7,
) -> SystemMetrics:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=period_days)
    m = SystemMetrics(period_days=period_days)

    for status_val, attr in [
        (None, "orders_total"),
        ("completed", "orders_completed"),
        ("approved", "orders_approved"),
        ("draft", "orders_draft"),
    ]:
        q = select(func.count()).select_from(TransportOrder).where(TransportOrder.created_at >= cutoff)
        if status_val:
            q = q.where(TransportOrder.status == status_val)
        result = await session.execute(q)
        setattr(m, attr, result.scalar() or 0)

    completed_orders_q = await session.execute(
        select(TransportOrder)
        .where(TransportOrder.status == "completed")
        .where(TransportOrder.created_at >= cutoff)
    )
    completed_orders = completed_orders_q.scalars().all()

    if completed_orders:
        util, miss, idle, total_actual, total_capacity, actuals = await _compute_order_stats(
            session, completed_orders
        )
        m.fleet_utilization_rate = util
        m.miss_rate = miss
        m.idle_vehicle_rate = idle
        m.total_shipments = total_actual
        m.total_capacity = total_capacity
        m.avg_actual_shipments = total_actual / len(completed_orders) if completed_orders else 0.0

    planned_avg_q = await session.execute(
        select(func.avg(func.coalesce(TransportOrder.planned_volume, TransportOrder.y_hat_future)))
        .where(TransportOrder.status == "completed")
        .where(TransportOrder.created_at >= cutoff)
    )
    m.avg_planned_volume = float(planned_avg_q.scalar() or 0.0)

    wh_ids_q = await session.execute(select(WarehouseConfig.warehouse_id))
    wh_ids = [row[0] for row in wh_ids_q.all()]

    for wid in wh_ids:
        total_q = await session.execute(
            select(func.count()).select_from(TransportOrder)
            .where(TransportOrder.office_from_id == wid)
            .where(TransportOrder.created_at >= cutoff)
        )
        wh_total = total_q.scalar() or 0
        comp_q = await session.execute(
            select(func.count()).select_from(TransportOrder)
            .where(TransportOrder.office_from_id == wid)
            .where(TransportOrder.status == "completed")
            .where(TransportOrder.created_at >= cutoff)
        )
        wh_completed = comp_q.scalar() or 0

        wh_orders_q = await session.execute(
            select(TransportOrder)
            .where(TransportOrder.office_from_id == wid)
            .where(TransportOrder.status == "completed")
            .where(TransportOrder.created_at >= cutoff)
        )
        wh_orders = wh_orders_q.scalars().all()
        wh_util = 0.0
        if wh_orders:
            wh_util, _, _, _, _, _ = await _compute_order_stats(session, wh_orders)

        vol_q = await session.execute(
            select(func.sum(Actual.shipments))
            .where(Actual.office_from_id == wid)
            .where(Actual.created_at >= cutoff)
        )
        total_vol = float(vol_q.scalar() or 0.0)

        m.warehouse_breakdown.append({
            "warehouse_id": wid,
            "orders_total": wh_total,
            "orders_completed": wh_completed,
            "utilization_rate": round(wh_util, 4),
            "total_shipments": round(total_vol, 2),
        })

    for day_offset in range(period_days):
        day_start = (now - timedelta(days=period_days - 1 - day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_end = day_start + timedelta(days=1)
        day_q = await session.execute(
            select(
                func.count(),
                func.count().filter(TransportOrder.status == "completed"),
            )
            .select_from(TransportOrder)
            .where(TransportOrder.created_at >= day_start)
            .where(TransportOrder.created_at < day_end)
        )
        row = day_q.first()
        m.orders_by_day.append({
            "date": day_start.strftime("%m-%d"),
            "total": row[0] if row else 0,
            "completed": row[1] if row else 0,
        })

    mae_q = await session.execute(_proposal_vs_actual_mae_query(cutoff))
    mae_val = mae_q.scalar()
    m.forecast_mae = float(mae_val) if mae_val is not None else 0.0

    naive_q = await session.execute(
        select(func.avg(func.abs(
            Actual.shipments
            - select(Actual.shipments)
            .where(Actual.route_id == Actual.route_id)
            .correlate(Actual)
            .scalar_subquery()
        )))
        .where(Actual.created_at >= cutoff)
    )
    m.naive_mae = float(naive_q.scalar() or 0.0)

    return m


async def compute_route_metrics(
    session: AsyncSession,
    route_id: str,
    period_days: int = 7,
) -> RouteMetrics:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=period_days)

    meta_q = await session.execute(
        select(RouteMetadata).where(RouteMetadata.route_id == route_id)
    )
    meta = meta_q.scalar_one_or_none()
    office_from_id = meta.office_from_id if meta else ""

    m = RouteMetrics(route_id=route_id, office_from_id=office_from_id, period_days=period_days)

    total_q = await session.execute(
        select(func.count()).select_from(TransportOrder)
        .where(TransportOrder.route_id == route_id)
        .where(TransportOrder.created_at >= cutoff)
    )
    m.orders_total = total_q.scalar() or 0

    comp_q = await session.execute(
        select(func.count()).select_from(TransportOrder)
        .where(TransportOrder.route_id == route_id)
        .where(TransportOrder.status == "completed")
        .where(TransportOrder.created_at >= cutoff)
    )
    m.orders_completed = comp_q.scalar() or 0

    completed_orders_q = await session.execute(
        select(TransportOrder)
        .where(TransportOrder.route_id == route_id)
        .where(TransportOrder.status == "completed")
        .where(TransportOrder.created_at >= cutoff)
    )
    completed = completed_orders_q.scalars().all()

    if completed:
        m.avg_planned_volume = sum(
            o.planned_volume or o.y_hat_future for o in completed
        ) / len(completed)
        m.avg_capacity_units = sum(o.capacity_units for o in completed) / len(completed)

        util, miss, idle, total_actual, _, actuals = await _compute_order_stats(session, completed)
        m.utilization_rate = util
        m.miss_rate = miss
        m.idle_rate = idle
        if actuals:
            m.avg_actual_shipments = sum(actuals) / len(actuals)

    actuals_q = await session.execute(
        select(Actual)
        .where(Actual.route_id == route_id)
        .where(Actual.created_at >= cutoff)
        .order_by(Actual.window_start.asc())
    )
    for a in actuals_q.scalars().all():
        m.shipments_history.append({
            "window_start": a.window_start.isoformat() if a.window_start else None,
            "shipments": a.shipments,
        })

    mae_q = await session.execute(
        _proposal_vs_actual_mae_query(cutoff).where(TransportOrder.route_id == route_id)
    )
    mae_val = mae_q.scalar()
    m.forecast_mae = float(mae_val) if mae_val is not None else 0.0

    return m


async def compute_all_routes_summary(
    session: AsyncSession,
    period_days: int = 7,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=period_days)

    routes_q = await session.execute(select(RouteMetadata))
    routes = routes_q.scalars().all()

    result = []
    for route in routes:
        total_q = await session.execute(
            select(func.count()).select_from(TransportOrder)
            .where(TransportOrder.route_id == route.route_id)
            .where(TransportOrder.created_at >= cutoff)
        )
        total = total_q.scalar() or 0

        comp_q = await session.execute(
            select(func.count()).select_from(TransportOrder)
            .where(TransportOrder.route_id == route.route_id)
            .where(TransportOrder.status == "completed")
            .where(TransportOrder.created_at >= cutoff)
        )
        completed = comp_q.scalar() or 0

        vol_q = await session.execute(
            select(func.avg(Actual.shipments))
            .where(Actual.route_id == route.route_id)
            .where(Actual.created_at >= cutoff)
        )
        avg_shipments = float(vol_q.scalar() or 0.0)

        result.append({
            "route_id": route.route_id,
            "office_from_id": route.office_from_id,
            "avg_duration_min": route.avg_duration_min,
            "orders_total": total,
            "orders_completed": completed,
            "avg_shipments": round(avg_shipments, 2),
        })

    result.sort(key=lambda r: r["orders_total"], reverse=True)
    return result
