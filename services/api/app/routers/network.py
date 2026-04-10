import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.route_forecast import RouteForecast
from ..models.route_metadata import RouteMetadata
from ..models.transport_order import TransportOrder
from ..models.vehicle_state import VehicleState
from ..models.warehouse_config import WarehouseConfig

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/network")
async def get_network(session: AsyncSession = Depends(get_session)):
    nodes = []
    edges = []

    wh_result = await session.execute(select(WarehouseConfig))
    warehouses = wh_result.scalars().all()

    for wh in warehouses:
        wid = wh.warehouse_id

        vehicle_counts = {}
        for vtype in ("gazel", "fura"):
            for status in ("free", "busy"):
                q = await session.execute(
                    select(func.count())
                    .where(VehicleState.warehouse_id == wid)
                    .where(VehicleState.vehicle_type == vtype)
                    .where(VehicleState.status == status)
                )
                vehicle_counts[f"{status}_{vtype}"] = q.scalar() or 0

        nodes.append(
            {
                "id": wid,
                "type": "warehouse",
                "label": f"Warehouse {wid}",
                "free_gazel": vehicle_counts["free_gazel"],
                "busy_gazel": vehicle_counts["busy_gazel"],
                "free_fura": vehicle_counts["free_fura"],
                "busy_fura": vehicle_counts["busy_fura"],
            }
        )

    routes_result = await session.execute(select(RouteMetadata))
    routes = routes_result.scalars().all()

    for route in routes:
        latest_forecast_q = await session.execute(
            select(RouteForecast.y_hat_future, RouteForecast.horizon, RouteForecast.confidence)
            .where(RouteForecast.route_id == route.route_id)
            .order_by(RouteForecast.run_ts.desc(), RouteForecast.horizon.asc())
            .limit(1)
        )
        latest = latest_forecast_q.first()

        y_hat_future = latest[0] if latest else 0.0
        latest_horizon = latest[1] if latest else 0
        latest_confidence = latest[2] if latest else 0.0

        active_orders_q = await session.execute(
            select(func.count())
            .select_from(TransportOrder)
            .where(TransportOrder.route_id == route.route_id)
            .where(TransportOrder.status.in_(["draft", "approved"]))
        )
        active_orders = active_orders_q.scalar() or 0

        wh_cfg_q = await session.execute(
            select(WarehouseConfig)
            .where(WarehouseConfig.warehouse_id == route.office_from_id)
        )
        wh_cfg = wh_cfg_q.scalar_one_or_none()
        gazel_cap = wh_cfg.gazel_capacity if wh_cfg else 10.0
        fura_cap = wh_cfg.fura_capacity if wh_cfg else 40.0

        if y_hat_future <= 0:
            urgency = "none"
        elif y_hat_future < 0.3 * gazel_cap:
            urgency = "low"
        elif y_hat_future < fura_cap:
            urgency = "medium"
        else:
            urgency = "high"

        draft_orders_q = await session.execute(
            select(func.count())
            .select_from(TransportOrder)
            .where(TransportOrder.route_id == route.route_id)
            .where(TransportOrder.status == "draft")
        )
        has_pending = (draft_orders_q.scalar() or 0) > 0

        truck_q = await session.execute(
            select(
                func.coalesce(func.sum(TransportOrder.fura_count), 0),
                func.coalesce(func.sum(TransportOrder.gazel_count), 0),
            )
            .where(TransportOrder.route_id == route.route_id)
            .where(TransportOrder.status.in_(["approved", "dispatched"]))
        )
        truck_row = truck_q.first()
        trucks = []
        if truck_row and truck_row[0] > 0:
            trucks.append({"type": "fura", "count": int(truck_row[0])})
        if truck_row and truck_row[1] > 0:
            trucks.append({"type": "gazel", "count": int(truck_row[1])})

        nodes.append(
            {
                "id": route.route_id,
                "type": "route",
                "office_from_id": route.office_from_id,
                "avg_duration_min": route.avg_duration_min,
                "latest_y_hat_future": y_hat_future,
                "latest_horizon": latest_horizon,
                "latest_confidence": latest_confidence,
                "active_orders": active_orders,
                "urgency": urgency,
                "trucks": trucks,
            }
        )

        edges.append(
            {
                "source": route.route_id,
                "target": route.office_from_id,
                "has_pending_orders": has_pending,
            }
        )

    return {"nodes": nodes, "edges": edges}
