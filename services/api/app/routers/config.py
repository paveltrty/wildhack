import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.warehouse_config import WarehouseConfig

logger = logging.getLogger(__name__)
router = APIRouter()


class WarehouseConfigUpdate(BaseModel):
    gazel_capacity: float | None = None
    fura_capacity: float | None = None
    lead_time_min: int | None = None
    safety_factor: float | None = None
    alpha: float | None = None
    beta: float | None = None
    travel_buffer_min: int | None = None
    avg_route_duration_min: float | None = None


@router.get("/config/{warehouse_id}")
async def get_config(
    warehouse_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(WarehouseConfig).where(WarehouseConfig.warehouse_id == warehouse_id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Warehouse config not found")

    return {
        "warehouse_id": cfg.warehouse_id,
        "gazel_capacity": cfg.gazel_capacity,
        "fura_capacity": cfg.fura_capacity,
        "lead_time_min": cfg.lead_time_min,
        "safety_factor": cfg.safety_factor,
        "alpha": cfg.alpha,
        "beta": cfg.beta,
        "travel_buffer_min": cfg.travel_buffer_min,
        "avg_route_duration_min": cfg.avg_route_duration_min,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.put("/config/{warehouse_id}")
async def update_config(
    warehouse_id: str,
    body: WarehouseConfigUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(WarehouseConfig).where(WarehouseConfig.warehouse_id == warehouse_id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Warehouse config not found")

    update_data = body.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(cfg, key, value)

    cfg.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return {"status": "updated", "warehouse_id": warehouse_id}
