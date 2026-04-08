"""Compute and log business metrics, with optional MLflow integration."""

import logging
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transport_order import TransportOrder
from app.models.actuals import Actual
from app.models.vehicle_state import VehicleState

logger = logging.getLogger(__name__)


class BusinessMetrics(BaseModel):
    fleet_utilization_rate: float
    miss_rate: float
    idle_vehicle_rate: float
    return_eta_error_min: float
    lead_time_adherence: float
    total_orders: int


async def compute_business_metrics(
    session: AsyncSession,
    warehouse_id: str,
    period_days: int = 7,
) -> BusinessMetrics:
    """
    Join transport_orders (completed) with actuals for same time windows.
    """
    cutoff = datetime.utcnow() - timedelta(days=period_days)

    orders_q = select(TransportOrder).where(
        and_(
            TransportOrder.warehouse_id == warehouse_id,
            TransportOrder.status == "completed",
            TransportOrder.updated_at >= cutoff,
        )
    )
    result = await session.execute(orders_q)
    orders = result.scalars().all()

    total = len(orders)
    if total == 0:
        return BusinessMetrics(
            fleet_utilization_rate=0.0,
            miss_rate=0.0,
            idle_vehicle_rate=0.0,
            return_eta_error_min=0.0,
            lead_time_adherence=0.0,
            total_orders=0,
        )

    actuals_q = select(Actual).where(
        and_(
            Actual.office_from_id == warehouse_id,
            Actual.created_at >= cutoff,
        )
    )
    result = await session.execute(actuals_q)
    actuals = result.scalars().all()
    actuals_by_window: dict[str, float] = {}
    for a in actuals:
        key = f"{a.window_start.isoformat()}_{a.window_end.isoformat()}"
        actuals_by_window[key] = a.actual_shipments

    miss_count = 0
    idle_count = 0
    total_utilization = 0.0

    for order in orders:
        capacity = order.capacity_units
        window_key = f"{order.scheduled_departure.isoformat()}_{(order.scheduled_departure + timedelta(hours=2)).isoformat()}"
        actual_val = actuals_by_window.get(window_key, 0.0)

        if capacity > 0:
            util = actual_val / capacity
            total_utilization += util
            if actual_val > capacity:
                miss_count += 1
            if util < 0.5:
                idle_count += 1

    lead_count = sum(
        1 for o in orders
        if (o.scheduled_departure - o.created_at).total_seconds() >= 3600
    )

    return BusinessMetrics(
        fleet_utilization_rate=round(total_utilization / total, 4) if total else 0.0,
        miss_rate=round(miss_count / total, 4) if total else 0.0,
        idle_vehicle_rate=round(idle_count / total, 4) if total else 0.0,
        return_eta_error_min=0.0,
        lead_time_adherence=round(lead_count / total, 4) if total else 0.0,
        total_orders=total,
    )


async def log_metrics_to_mlflow(
    warehouse_id: str,
    metrics: BusinessMetrics,
    mlflow_uri: str,
) -> None:
    """Log business metrics to MLflow if available."""
    try:
        import mlflow
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment("transport_dispatch")
        with mlflow.start_run(run_name=f"metrics_{warehouse_id}_{datetime.utcnow().isoformat()}"):
            mlflow.set_tag("warehouse_id", warehouse_id)
            mlflow.log_metric("fleet_utilization_rate", metrics.fleet_utilization_rate)
            mlflow.log_metric("miss_rate", metrics.miss_rate)
            mlflow.log_metric("idle_vehicle_rate", metrics.idle_vehicle_rate)
            mlflow.log_metric("lead_time_adherence", metrics.lead_time_adherence)
            mlflow.log_metric("total_orders", metrics.total_orders)
        logger.info("Logged metrics to MLflow for warehouse %s", warehouse_id)
    except Exception:
        logger.warning("Failed to log metrics to MLflow", exc_info=True)
