import json
import logging
from datetime import datetime, timezone

import httpx
import redis.asyncio as redis
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import async_session
from .models.raw_events import RawEvent
from .models.route_forecast import RouteForecast
from .models.warehouse_config import WarehouseConfig
from .services import vehicle_tracker
from .services.feature_store import get_features
from .services.horizon_decomposer import decompose_route_forecasts
from .services.optimizer import compute_route_decision
from .services.transport_planner import create_orders_for_warehouse

logger = logging.getLogger(__name__)

redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(settings.REDIS_URL)
    return redis_client


async def run_forecast_cycle(session: AsyncSession | None = None) -> dict:
    """Full forecast → optimize → plan cycle for all warehouses."""
    own_session = session is None
    if own_session:
        session = async_session()

    try:
        now = datetime.now(timezone.utc)
        summary: dict = {"run_ts": now.isoformat(), "warehouses": {}}

        wh_result = await session.execute(
            select(distinct(RawEvent.office_from_id))
        )
        warehouse_ids = [row[0] for row in wh_result.all()]

        if not warehouse_ids:
            logger.warning("No warehouses found in raw_events")
            return summary

        for warehouse_id in warehouse_ids:
            wh_summary = await _process_warehouse(session, warehouse_id, now)
            summary["warehouses"][warehouse_id] = wh_summary

        r = await get_redis()
        for wid, ws in summary["warehouses"].items():
            await r.set(
                f"scheduler:latest:{wid}",
                json.dumps(ws, default=str),
                ex=3600,
            )

        logger.info(
            "Forecast cycle completed for %d warehouses",
            len(warehouse_ids),
            extra={"run_ts": now.isoformat()},
        )
        return summary

    finally:
        if own_session:
            await session.close()


async def _process_warehouse(
    session: AsyncSession,
    warehouse_id: str,
    now: datetime,
) -> dict:
    wh_summary: dict = {
        "routes_processed": 0,
        "orders_created": 0,
        "decisions": [],
    }

    features = await get_features(session, warehouse_id, now)
    if not features:
        return wh_summary

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.INFERENCE_URL}/predict",
                json={"rows": features},
            )
            resp.raise_for_status()
            pred_data = resp.json()
    except Exception as exc:
        logger.error(
            "Inference call failed for warehouse %s: %s",
            warehouse_id,
            exc,
            extra={"warehouse_id": warehouse_id},
        )
        return wh_summary

    predictions = pred_data.get("predictions", [])

    cfg_result = await session.execute(
        select(WarehouseConfig).where(WarehouseConfig.warehouse_id == warehouse_id)
    )
    config = cfg_result.scalar_one_or_none()
    if not config:
        config = WarehouseConfig(warehouse_id=warehouse_id)
        session.add(config)
        await session.commit()

    availability = await vehicle_tracker.get_availability_profile(
        session, warehouse_id, now
    )

    decisions = []
    for pred in predictions:
        route_id = pred["route_id"]
        raw_preds = [h["y_hat"] for h in pred["horizons"]]
        confidences = [h["confidence"] for h in pred["horizons"]]

        future_increments = await decompose_route_forecasts(
            session, route_id, now, raw_preds
        )

        from sqlalchemy.dialects.postgresql import insert

        for h_idx, horizon_data in enumerate(pred["horizons"]):
            h = horizon_data["horizon"]
            stmt = insert(RouteForecast).values(
                route_id=route_id,
                office_from_id=warehouse_id,
                run_ts=now,
                horizon=h,
                y_hat_raw=horizon_data["y_hat"],
                y_hat_future=future_increments[h_idx],
                confidence=horizon_data["confidence"],
                y_hat_low=horizon_data.get("y_hat_low"),
                y_hat_high=horizon_data.get("y_hat_high"),
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_forecast_route_run_h",
                set_={
                    "y_hat_raw": stmt.excluded.y_hat_raw,
                    "y_hat_future": stmt.excluded.y_hat_future,
                    "confidence": stmt.excluded.confidence,
                    "y_hat_low": stmt.excluded.y_hat_low,
                    "y_hat_high": stmt.excluded.y_hat_high,
                },
            )
            await session.execute(stmt)

        decision = await compute_route_decision(
            session,
            route_id,
            warehouse_id,
            future_increments,
            confidences,
            availability,
            config,
            now,
        )
        if decision:
            decisions.append(decision)

        wh_summary["routes_processed"] += 1

    await session.commit()

    new_orders = await create_orders_for_warehouse(session, warehouse_id, decisions)
    wh_summary["orders_created"] = len(new_orders)
    wh_summary["decisions"] = [
        {
            "route_id": d.route_id,
            "optimal_horizon": d.optimal_horizon,
            "optimal_score": d.optimal_score,
            "y_hat_future": d.y_hat_future,
            "fura_count": d.fura_count,
            "gazel_count": d.gazel_count,
            "total_capacity": d.total_capacity,
        }
        for d in decisions
    ]

    return wh_summary


async def check_vehicle_returns() -> None:
    """Auto-return overdue vehicles whose eta_return has passed."""
    async with async_session() as session:
        freed = await vehicle_tracker.return_overdue_vehicles(session)
        if freed:
            logger.info("Auto-returned %d overdue vehicles", freed)
