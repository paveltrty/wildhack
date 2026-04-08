"""APScheduler jobs: forecast cycle every 30 min, vehicle return check every 5 min."""

import json
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select, distinct, and_, func

from app.config import settings
from app.database import async_session
from app.models.raw_events import RawEvent
from app.metrics import ROUTES_UTILIZED_RATIO
from app.models.route_metadata import RouteMetadata
from app.models.warehouse_config import WarehouseConfig
from app.models.warehouse_forecast import WarehouseForecast
from app.models.vehicle_state import VehicleState
from app.services.feature_store import get_features_for_inference, get_actual_shipments
from app.services.vehicle_tracker import get_availability_profile, assign_free_vehicles_to_routes
from app.services.optimizer import compute_dispatch_decision
from app.services.transport_planner import create_order_from_decision

logger = logging.getLogger(__name__)


async def run_forecast_cycle():
    """Every 30 minutes: run inference for all warehouses, optimize, create orders."""
    logger.info("Starting forecast cycle")
    # Use the most recent timestamp in the loaded data as the run timestamp.
    # This keeps the system consistent when replaying historical parquet data.
    async with async_session() as session:
        ts_res = await session.execute(select(func.max(RawEvent.timestamp)))
        max_ts = ts_res.scalar_one_or_none()
    now = max_ts or datetime.utcnow()

    async with async_session() as session:
        result = await session.execute(
            select(distinct(RawEvent.office_from_id))
        )
        warehouse_ids = [r[0] for r in result.fetchall()]

    if not warehouse_ids:
        logger.info("No warehouses found, skipping forecast cycle")
        return

    for wh_id in warehouse_ids:
        try:
            await _forecast_for_warehouse(wh_id, now)
        except Exception:
            logger.exception("Forecast cycle failed for warehouse %s", wh_id)


async def _forecast_for_warehouse(warehouse_id: str, now: datetime):
    async with async_session() as session:
        # Make sure routes have vehicles assigned (helps analytics/route utilization).
        try:
            await assign_free_vehicles_to_routes(session, warehouse_id)
            # compute route utilization metric: routes with at least one vehicle assigned
            routes_total_res = await session.execute(
                select(func.count(RouteMetadata.route_id)).where(RouteMetadata.office_from_id == warehouse_id)
            )
            routes_total = int(routes_total_res.scalar() or 0)
            if routes_total > 0:
                utilized_res = await session.execute(
                    select(func.count(func.distinct(VehicleState.route_id))).where(
                        and_(
                            VehicleState.warehouse_id == warehouse_id,
                            VehicleState.route_id.is_not(None),
                        )
                    )
                )
                utilized = int(utilized_res.scalar() or 0)
                ROUTES_UTILIZED_RATIO.labels(warehouse_id=str(warehouse_id)).set(utilized / routes_total)
        except Exception:
            logger.warning("Failed to auto-assign vehicles to routes for warehouse %s", warehouse_id, exc_info=True)

        feature_rows = await get_features_for_inference(session, warehouse_id, now)

        if not feature_rows:
            logger.warning("No feature rows for warehouse %s", warehouse_id)
            return

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.INFERENCE_URL}/predict",
                json={"rows": feature_rows},
            )
            resp.raise_for_status()
            predictions = resp.json()["predictions"]

        if not predictions:
            return

        # Idempotency: if this warehouse+run_ts was already processed, replace forecasts.
        await session.execute(
            WarehouseForecast.__table__.delete().where(
                and_(
                    WarehouseForecast.office_from_id == warehouse_id,
                    WarehouseForecast.run_ts == now,
                )
            )
        )

        agg_horizons: dict[int, dict] = {}
        for pred in predictions:
            for h_data in pred["horizons"]:
                h = h_data["horizon"]
                if h not in agg_horizons:
                    agg_horizons[h] = {
                        "horizon": h,
                        "y_hat": 0.0,
                        "confidence": h_data["confidence"],
                        "y_hat_low": 0.0,
                        "y_hat_high": 0.0,
                        "count": 0,
                    }
                agg_horizons[h]["y_hat"] += h_data["y_hat"]
                agg_horizons[h]["y_hat_low"] += h_data["y_hat_low"]
                agg_horizons[h]["y_hat_high"] += h_data["y_hat_high"]
                agg_horizons[h]["count"] += 1

        for h, data in agg_horizons.items():
            forecast = WarehouseForecast(
                run_ts=now,
                office_from_id=warehouse_id,
                horizon=h,
                minutes_ahead=h * 30,
                y_hat=data["y_hat"],
                confidence=data["confidence"],
                y_hat_low=data["y_hat_low"],
                y_hat_high=data["y_hat_high"],
            )
            session.add(forecast)

        await session.commit()

        # Prediction covers a 2h window (4 × 30-min steps).
        # For horizon h the window starts (4−h)*30 min in the past, so part
        # of the prediction is already realised.  Subtract actual shipments
        # for the elapsed portion so the optimizer sees only *remaining* demand.
        PRED_WINDOW_STEPS = 4  # 2 h / 30 min
        for h, data in agg_horizons.items():
            overlap_steps = max(0, PRED_WINDOW_STEPS - h)
            lookback_min = overlap_steps * 30
            actual = await get_actual_shipments(
                session, warehouse_id, now, lookback_min,
            )
            data["actual_shipped"] = actual
            data["y_hat_remaining"] = max(0.0, data["y_hat"] - actual)

        logger.info(
            "Forecast adjustment for warehouse %s: %s",
            warehouse_id,
            {
                h: {
                    "raw": round(d["y_hat"], 2),
                    "actual": round(d["actual_shipped"], 2),
                    "remaining": round(d["y_hat_remaining"], 2),
                }
                for h, d in sorted(agg_horizons.items())
            },
        )

        availability = await get_availability_profile(session, warehouse_id, now)

        config_result = await session.execute(
            select(WarehouseConfig).where(WarehouseConfig.warehouse_id == warehouse_id)
        )
        config = config_result.scalar_one_or_none()
        if config is None:
            config = WarehouseConfig(warehouse_id=warehouse_id)
            session.add(config)
            await session.commit()
            await session.refresh(config)

        forecasts_for_opt = [
            {
                "horizon": h,
                "y_hat": data["y_hat_remaining"],
                "confidence": data["confidence"],
            }
            for h, data in sorted(agg_horizons.items())
        ]

        decision = await compute_dispatch_decision(
            session, warehouse_id, forecasts_for_opt, availability, config
        )

        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL)
            decision_json = decision.model_dump_json()
            await r.set(f"optimizer:latest:{warehouse_id}", decision_json, ex=3600)
            await r.lpush(f"optimizer:history:{warehouse_id}", decision_json)
            await r.ltrim(f"optimizer:history:{warehouse_id}", 0, 19)
            await r.aclose()
        except Exception:
            logger.warning("Failed to cache optimizer decision in Redis", exc_info=True)

        if decision.extra_needed > 0:
            await create_order_from_decision(session, warehouse_id, decision, config)

    logger.info("Forecast cycle completed for warehouse %s", warehouse_id)


async def check_vehicle_returns():
    """Every 5 minutes: check for vehicles approaching ETA."""
    now = datetime.utcnow()
    threshold = now + timedelta(minutes=5)

    async with async_session() as session:
        result = await session.execute(
            select(VehicleState).where(
                and_(
                    VehicleState.status == "busy",
                    VehicleState.eta_return <= threshold,
                )
            )
        )
        approaching = result.scalars().all()

        for v in approaching:
            logger.warning(
                "Vehicle %s (warehouse %s) ETA approaching: %s (now: %s)",
                v.id, v.warehouse_id, v.eta_return, now,
            )
