"""Transport order management endpoints."""

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.transport_order import TransportOrder
from app.models.actuals import Actual
from app.models.vehicle_state import VehicleState
from app.services import vehicle_tracker

logger = logging.getLogger(__name__)
router = APIRouter()


class CompleteRequest(BaseModel):
    actual_shipments: float


@router.get("/orders")
async def list_orders(
    warehouse_id: str | None = Query(None),
    date: str | None = Query(None),
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    conditions = []
    if warehouse_id:
        conditions.append(TransportOrder.warehouse_id == warehouse_id)
    if status:
        conditions.append(TransportOrder.status == status)
    if date:
        try:
            d = datetime.fromisoformat(date)
            conditions.append(TransportOrder.scheduled_departure >= d)
            conditions.append(TransportOrder.scheduled_departure < d + timedelta(days=1))
        except ValueError:
            pass

    q = select(TransportOrder)
    if conditions:
        q = q.where(and_(*conditions))
    q = q.order_by(TransportOrder.scheduled_departure.asc())

    result = await session.execute(q)
    orders = result.scalars().all()

    return [
        {
            "id": str(o.id),
            "warehouse_id": o.warehouse_id,
            "scheduled_departure": o.scheduled_departure.isoformat(),
            "vehicle_type": o.vehicle_type,
            "vehicle_count": o.vehicle_count,
            "capacity_units": o.capacity_units,
            "chosen_horizon": o.chosen_horizon,
            "optimizer_score": o.optimizer_score,
            "status": o.status,
            "notes": o.notes,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "updated_at": o.updated_at.isoformat() if o.updated_at else None,
        }
        for o in orders
    ]


@router.post("/orders/{order_id}/approve")
async def approve_order(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(TransportOrder).where(TransportOrder.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot approve order in status '{order.status}'")

    order.status = "approved"

    free_q = select(VehicleState).where(
        and_(
            VehicleState.warehouse_id == order.warehouse_id,
            VehicleState.status == "free",
        )
    ).limit(order.vehicle_count)
    result = await session.execute(free_q)
    free_vehicles = result.scalars().all()

    for v in free_vehicles:
        if v.route_id is None:
            v.status = "busy"
            v.dispatched_at = datetime.utcnow()
            v.eta_return = order.scheduled_departure + timedelta(hours=2)

    if free_vehicles:
        order.status = "dispatched"

    await session.commit()
    return {"id": str(order.id), "status": order.status, "vehicles_dispatched": len(free_vehicles)}


@router.post("/orders/{order_id}/complete")
async def complete_order(
    order_id: uuid.UUID,
    body: CompleteRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(TransportOrder).where(TransportOrder.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = "completed"

    actual = Actual(
        route_id=order.warehouse_id,
        office_from_id=order.warehouse_id,
        window_start=order.scheduled_departure,
        window_end=order.scheduled_departure + timedelta(hours=2),
        actual_shipments=body.actual_shipments,
    )
    session.add(actual)
    await session.commit()

    return {"id": str(order.id), "status": order.status, "actual_shipments": body.actual_shipments}
