import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.actuals import Actual
from ..models.route_metadata import RouteMetadata
from ..models.transport_order import TransportOrder
from ..models.warehouse_config import WarehouseConfig
from ..services import vehicle_tracker
from ..services.draft_reviewer import review_warehouse_drafts

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_order(o: TransportOrder) -> dict:
    fura_count = o.fura_count or 0
    gazel_count = o.gazel_count or 0
    return {
        "id": str(o.id),
        "route_id": o.route_id,
        "office_from_id": o.office_from_id,
        "scheduled_departure": o.scheduled_departure.isoformat(),
        "fura_count": fura_count,
        "gazel_count": gazel_count,
        "vehicle_type": o.vehicle_type,
        "vehicle_count": o.vehicle_count,
        "capacity_units": o.capacity_units,
        "planned_volume": o.planned_volume or o.y_hat_future,
        "chosen_horizon": o.chosen_horizon,
        "optimizer_score": o.optimizer_score,
        "y_hat_future": o.y_hat_future,
        "status": o.status,
        "notes": o.notes,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "updated_at": o.updated_at.isoformat() if o.updated_at else None,
    }


class UpdateOrderRequest(BaseModel):
    fura_count: Optional[int] = None
    gazel_count: Optional[int] = None
    planned_volume: Optional[float] = None
    notes: Optional[str] = None


class ApproveOrderRequest(BaseModel):
    fura_count: Optional[int] = None
    gazel_count: Optional[int] = None
    planned_volume: Optional[float] = None
    notes: Optional[str] = None


class CompleteOrderRequest(BaseModel):
    actual_shipments: Optional[float] = None


@router.get("/orders")
async def get_orders(
    office_from_id: Optional[str] = Query(None),
    route_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    q = select(TransportOrder)

    if office_from_id:
        q = q.where(TransportOrder.office_from_id == office_from_id)
    if route_id:
        q = q.where(TransportOrder.route_id == route_id)
    if status:
        q = q.where(TransportOrder.status == status)
    if date:
        try:
            d = datetime.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
        q = q.where(TransportOrder.scheduled_departure >= d)
        q = q.where(TransportOrder.scheduled_departure < d + timedelta(days=1))

    q = q.order_by(TransportOrder.scheduled_departure.desc())
    result = await session.execute(q)
    orders = result.scalars().all()

    return [_serialize_order(o) for o in orders]


def _num_sort_key(val: str) -> tuple:
    try:
        return (0, int(val), val)
    except ValueError:
        return (1, 0, val)


@router.get("/orders/warehouses")
async def list_warehouses(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(WarehouseConfig.warehouse_id))
    ids = [row[0] for row in result.all()]
    ids.sort(key=_num_sort_key)
    return ids


@router.get("/orders/routes")
async def list_routes(
    office_from_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    q = select(RouteMetadata.route_id, RouteMetadata.office_from_id)
    if office_from_id:
        q = q.where(RouteMetadata.office_from_id == office_from_id)
    result = await session.execute(q)
    rows = [{"route_id": row[0], "office_from_id": row[1]} for row in result.all()]
    rows.sort(key=lambda r: _num_sort_key(r["route_id"]))
    return rows


@router.patch("/orders/{order_id}")
async def update_order(
    order_id: UUID,
    body: UpdateOrderRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(TransportOrder).where(TransportOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Only draft orders can be edited, current status: '{order.status}'",
        )

    cfg_result = await session.execute(
        select(WarehouseConfig).where(
            WarehouseConfig.warehouse_id == order.office_from_id
        )
    )
    cfg = cfg_result.scalar_one_or_none()
    fura_cap = cfg.fura_capacity if cfg else 40.0
    gazel_cap = cfg.gazel_capacity if cfg else 10.0

    if body.fura_count is not None:
        order.fura_count = body.fura_count
    if body.gazel_count is not None:
        order.gazel_count = body.gazel_count
    if body.planned_volume is not None:
        order.planned_volume = body.planned_volume
    if body.notes is not None:
        order.notes = body.notes

    order.capacity_units = order.fura_count * fura_cap + order.gazel_count * gazel_cap
    order.updated_at = datetime.now(timezone.utc)

    await session.commit()
    return _serialize_order(order)


@router.post("/orders/{order_id}/approve")
async def approve_order(
    order_id: UUID,
    body: ApproveOrderRequest = ApproveOrderRequest(),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(TransportOrder).where(TransportOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Order status is '{order.status}', expected 'draft'",
        )

    cfg_result = await session.execute(
        select(WarehouseConfig).where(
            WarehouseConfig.warehouse_id == order.office_from_id
        )
    )
    cfg = cfg_result.scalar_one_or_none()
    fura_cap = cfg.fura_capacity if cfg else 40.0
    gazel_cap = cfg.gazel_capacity if cfg else 10.0

    if body.fura_count is not None:
        order.fura_count = body.fura_count
    if body.gazel_count is not None:
        order.gazel_count = body.gazel_count
    if body.planned_volume is not None:
        order.planned_volume = body.planned_volume
    if body.notes is not None:
        order.notes = body.notes

    order.capacity_units = (order.fura_count or 0) * fura_cap + (order.gazel_count or 0) * gazel_cap

    now = datetime.now(timezone.utc)
    fura_count = order.fura_count or 0
    gazel_count = order.gazel_count or 0

    try:
        if fura_count > 0:
            await vehicle_tracker.dispatch_vehicles(
                session, order.office_from_id, "fura", fura_count, now,
            )
        if gazel_count > 0:
            await vehicle_tracker.dispatch_vehicles(
                session, order.office_from_id, "gazel", gazel_count, now,
            )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    order.status = "approved"
    order.updated_at = now

    old_notes = order.notes or ""
    if old_notes.startswith("⚠️"):
        clean = old_notes.split(" | ", 1)[1] if " | " in old_notes else ""
        order.notes = clean or None

    await session.commit()

    warnings = await review_warehouse_drafts(session, order.office_from_id)
    await session.commit()

    result_data = _serialize_order(order)
    result_data["draft_warnings"] = warnings
    return result_data


@router.post("/orders/{order_id}/complete")
async def complete_order(
    order_id: UUID,
    body: CompleteOrderRequest = CompleteOrderRequest(),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(TransportOrder).where(TransportOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in ("approved", "dispatched"):
        raise HTTPException(
            status_code=400,
            detail=f"Order status is '{order.status}', expected 'approved' or 'dispatched'",
        )

    now = datetime.now(timezone.utc)
    order.status = "completed"
    order.updated_at = now

    fura_count = order.fura_count or 0
    gazel_count = order.gazel_count or 0
    if fura_count > 0:
        await vehicle_tracker.release_vehicles(
            session, order.office_from_id, "fura", fura_count,
        )
    if gazel_count > 0:
        await vehicle_tracker.release_vehicles(
            session, order.office_from_id, "gazel", gazel_count,
        )

    shipments = body.actual_shipments if body.actual_shipments is not None else (order.planned_volume or order.y_hat_future)

    actual = Actual(
        route_id=order.route_id,
        office_from_id=order.office_from_id,
        window_start=order.scheduled_departure,
        window_end=order.scheduled_departure + timedelta(minutes=30),
        shipments=shipments,
    )
    session.add(actual)
    await session.commit()

    warnings = await review_warehouse_drafts(session, order.office_from_id)
    await session.commit()

    return _serialize_order(order)
