"""Warehouse configuration CRUD."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.warehouse_config import WarehouseConfig
from app.scheduler import run_forecast_cycle

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


@router.get("/config/{warehouse_id}")
async def get_config(
    warehouse_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(WarehouseConfig).where(WarehouseConfig.warehouse_id == warehouse_id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Warehouse config not found")

    return {
        "warehouse_id": config.warehouse_id,
        "gazel_capacity": config.gazel_capacity,
        "fura_capacity": config.fura_capacity,
        "lead_time_min": config.lead_time_min,
        "safety_factor": config.safety_factor,
        "alpha": config.alpha,
        "beta": config.beta,
        "travel_buffer_min": config.travel_buffer_min,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
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
    config = result.scalar_one_or_none()

    if config is None:
        config = WarehouseConfig(warehouse_id=warehouse_id)
        session.add(config)

    update_data = body.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    await session.commit()
    await session.refresh(config)

    return {
        "warehouse_id": config.warehouse_id,
        "gazel_capacity": config.gazel_capacity,
        "fura_capacity": config.fura_capacity,
        "lead_time_min": config.lead_time_min,
        "safety_factor": config.safety_factor,
        "alpha": config.alpha,
        "beta": config.beta,
        "travel_buffer_min": config.travel_buffer_min,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


@router.post("/admin/run-cycle")
async def admin_run_cycle():
    # Run within the API process so Prometheus metrics update.
    asyncio.create_task(run_forecast_cycle())
    return {"status": "started"}
