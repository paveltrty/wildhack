"""Vehicle management endpoints."""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.vehicle_state import VehicleState
from app.services import vehicle_tracker

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateVehicleRequest(BaseModel):
    warehouse_id: str
    vehicle_type: str


class DispatchRequest(BaseModel):
    route_id: str


@router.get("/vehicles")
async def list_vehicles(
    warehouse_id: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    q = select(VehicleState)
    if warehouse_id:
        q = q.where(VehicleState.warehouse_id == warehouse_id)
    q = q.order_by(VehicleState.warehouse_id, VehicleState.vehicle_type)

    result = await session.execute(q)
    vehicles = result.scalars().all()

    return [
        {
            "id": str(v.id),
            "warehouse_id": v.warehouse_id,
            "vehicle_type": v.vehicle_type,
            "status": v.status,
            "route_id": v.route_id,
            "dispatched_at": v.dispatched_at.isoformat() if v.dispatched_at else None,
            "eta_return": v.eta_return.isoformat() if v.eta_return else None,
            "updated_at": v.updated_at.isoformat() if v.updated_at else None,
        }
        for v in vehicles
    ]


@router.post("/vehicles")
async def create_vehicle(
    body: CreateVehicleRequest,
    session: AsyncSession = Depends(get_session),
):
    if body.vehicle_type not in ("gazel", "fura"):
        raise HTTPException(status_code=400, detail="vehicle_type must be 'gazel' or 'fura'")

    vehicle = VehicleState(
        warehouse_id=body.warehouse_id,
        vehicle_type=body.vehicle_type,
        status="free",
    )
    session.add(vehicle)
    await session.commit()
    await session.refresh(vehicle)

    return {
        "id": str(vehicle.id),
        "warehouse_id": vehicle.warehouse_id,
        "vehicle_type": vehicle.vehicle_type,
        "status": vehicle.status,
    }


@router.post("/vehicles/{vehicle_id}/dispatch")
async def dispatch(
    vehicle_id: uuid.UUID,
    body: DispatchRequest,
    session: AsyncSession = Depends(get_session),
):
    vehicle = await vehicle_tracker.dispatch_vehicle(
        session, vehicle_id, body.route_id, datetime.utcnow()
    )
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return {
        "id": str(vehicle.id),
        "status": vehicle.status,
        "route_id": vehicle.route_id,
        "eta_return": vehicle.eta_return.isoformat() if vehicle.eta_return else None,
    }


@router.post("/vehicles/{vehicle_id}/return")
async def return_vehicle(
    vehicle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    vehicle = await vehicle_tracker.return_vehicle(session, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return {"id": str(vehicle.id), "status": vehicle.status}
