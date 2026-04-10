import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.vehicle_state import VehicleState
from ..models.warehouse_config import WarehouseConfig
from ..services import vehicle_tracker
from ..services.draft_reviewer import review_warehouse_drafts

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateVehiclesRequest(BaseModel):
    warehouse_id: str
    vehicle_type: str
    count: int


class SetFleetRequest(BaseModel):
    warehouse_id: str
    gazel_count: int
    fura_count: int


@router.get("/vehicles")
async def get_vehicles(
    warehouse_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    q = select(VehicleState)
    if warehouse_id:
        q = q.where(VehicleState.warehouse_id == warehouse_id)

    result = await session.execute(q)
    vehicles = result.scalars().all()

    return [
        {
            "id": str(v.id),
            "warehouse_id": v.warehouse_id,
            "vehicle_type": v.vehicle_type,
            "status": v.status,
            "dispatched_at": v.dispatched_at.isoformat() if v.dispatched_at else None,
            "eta_return": v.eta_return.isoformat() if v.eta_return else None,
            "updated_at": v.updated_at.isoformat() if v.updated_at else None,
        }
        for v in vehicles
    ]


@router.get("/vehicles/summary")
async def fleet_summary(
    session: AsyncSession = Depends(get_session),
):
    """Per-warehouse counts: free/busy × gazel/fura."""
    result = await session.execute(
        select(
            VehicleState.warehouse_id,
            VehicleState.vehicle_type,
            VehicleState.status,
            func.count(),
        )
        .group_by(VehicleState.warehouse_id, VehicleState.vehicle_type, VehicleState.status)
        .order_by(VehicleState.warehouse_id)
    )

    warehouses: dict[str, dict] = {}
    for wid, vtype, vstatus, cnt in result.all():
        if wid not in warehouses:
            warehouses[wid] = {
                "warehouse_id": wid,
                "gazel_free": 0, "gazel_busy": 0, "gazel_total": 0,
                "fura_free": 0, "fura_busy": 0, "fura_total": 0,
            }
        w = warehouses[wid]
        key = f"{vtype}_{vstatus}"
        w[key] = cnt
        w[f"{vtype}_total"] = w.get(f"{vtype}_free", 0) + w.get(f"{vtype}_busy", 0)

    for w in warehouses.values():
        w["gazel_total"] = w["gazel_free"] + w["gazel_busy"]
        w["fura_total"] = w["fura_free"] + w["fura_busy"]

    def _num_key(item: dict) -> tuple:
        wid = item["warehouse_id"]
        try:
            return (0, int(wid), wid)
        except ValueError:
            return (1, 0, wid)

    return sorted(warehouses.values(), key=_num_key)


@router.post("/vehicles")
async def create_vehicles(
    body: CreateVehiclesRequest,
    session: AsyncSession = Depends(get_session),
):
    if body.vehicle_type not in ("gazel", "fura"):
        raise HTTPException(status_code=400, detail="vehicle_type must be 'gazel' or 'fura'")
    if body.count < 1:
        raise HTTPException(status_code=400, detail="count must be >= 1")

    created = []
    for _ in range(body.count):
        v = VehicleState(
            warehouse_id=body.warehouse_id,
            vehicle_type=body.vehicle_type,
            status="free",
        )
        session.add(v)
        created.append(v)

    await session.commit()

    return {
        "created": len(created),
        "warehouse_id": body.warehouse_id,
        "vehicle_type": body.vehicle_type,
    }


@router.post("/vehicles/set-fleet")
async def set_fleet(
    body: SetFleetRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Set the desired fleet size for a warehouse.
    Adds free vehicles to reach target, or removes free vehicles if over target.
    Never removes busy vehicles.
    """
    wid = body.warehouse_id
    changes = {}

    for vtype, desired in [("gazel", body.gazel_count), ("fura", body.fura_count)]:
        total_q = await session.execute(
            select(func.count()).where(VehicleState.warehouse_id == wid).where(VehicleState.vehicle_type == vtype)
        )
        current_total = total_q.scalar() or 0

        if desired > current_total:
            to_add = desired - current_total
            for _ in range(to_add):
                session.add(VehicleState(warehouse_id=wid, vehicle_type=vtype, status="free"))
            changes[vtype] = {"action": "added", "count": to_add}
        elif desired < current_total:
            to_remove = current_total - desired
            free_q = await session.execute(
                select(VehicleState.id)
                .where(VehicleState.warehouse_id == wid)
                .where(VehicleState.vehicle_type == vtype)
                .where(VehicleState.status == "free")
                .limit(to_remove)
            )
            free_ids = [row[0] for row in free_q.all()]
            if free_ids:
                await session.execute(
                    delete(VehicleState).where(VehicleState.id.in_(free_ids))
                )
            changes[vtype] = {"action": "removed", "count": len(free_ids)}
        else:
            changes[vtype] = {"action": "unchanged", "count": 0}

    await session.commit()

    warnings = await review_warehouse_drafts(session, wid)
    await session.commit()

    return {"warehouse_id": wid, "changes": changes, "draft_warnings": warnings}


@router.post("/vehicles/{vehicle_id}/return")
async def return_vehicle_endpoint(
    vehicle_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    check = await session.execute(
        select(VehicleState).where(VehicleState.id == vehicle_id)
    )
    if not check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Vehicle not found")

    await vehicle_tracker.return_vehicle(session, vehicle_id)
    return {"status": "ok", "vehicle_id": str(vehicle_id)}
