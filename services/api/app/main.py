import logging
import sys

import redis.asyncio as redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from pythonjsonlogger import jsonlogger

from .config import settings
from .database import engine, get_session
from .routers import analytics, config, forecasts, network, orders, upload, vehicles
from .scheduler import check_vehicle_returns, run_forecast_cycle

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    jsonlogger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
)
logging.root.handlers = [handler]
logging.root.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

logger = logging.getLogger(__name__)

app = FastAPI(title="Transport Dispatch API", version="0.1.0")

app.include_router(upload.router)
app.include_router(forecasts.router)
app.include_router(vehicles.router)
app.include_router(orders.router)
app.include_router(analytics.router)
app.include_router(network.router)
app.include_router(config.router)

scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def startup() -> None:
    from .database import Base

    scheduler.add_job(
        run_forecast_cycle,
        "interval",
        minutes=settings.SCHEDULER_FORECAST_INTERVAL_MIN,
        id="forecast_cycle",
        replace_existing=True,
    )
    scheduler.add_job(
        check_vehicle_returns,
        "interval",
        minutes=settings.SCHEDULER_VEHICLE_CHECK_INTERVAL_MIN,
        id="vehicle_check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")


@app.on_event("shutdown")
async def shutdown() -> None:
    scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("Shutdown complete")


@app.get("/health")
async def health():
    checks = {"db": "error", "redis": "error", "inference": "error"}

    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        pass

    try:
        r = redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        checks["redis"] = "ok"
    except Exception:
        pass

    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.INFERENCE_URL}/health")
            if resp.status_code == 200:
                checks["inference"] = "ok"
    except Exception:
        pass

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}


@app.post("/internal/trigger-cycle")
async def trigger_cycle():
    """Manually trigger one full scheduler cycle."""
    summary = await run_forecast_cycle()
    return summary
