"""API Backend: FastAPI application with lifespan, routers, and middleware."""

import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pythonjsonlogger import jsonlogger

from app.config import settings
from app.database import engine
from app.metrics import OPTIMIZER_SCORE, VEHICLES_AVAILABLE, ROUTES_UTILIZED_RATIO, ORDERS_CREATED, MISS_EVENTS
from app.routers import upload, forecasts, vehicles, orders, analytics, config

log_level = settings.LOG_LEVEL.upper()
logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(getattr(logging, log_level, logging.INFO))

@asynccontextmanager
async def lifespan(app: FastAPI):
    from alembic.config import Config as AlembicConfig
    from alembic import command
    try:
        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("+asyncpg", ""))
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied")
    except Exception:
        logger.warning("Alembic migration failed (may already be applied)", exc_info=True)

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from app.scheduler import run_forecast_cycle, check_vehicle_returns

        scheduler = AsyncIOScheduler()
        scheduler.add_job(run_forecast_cycle, "interval", minutes=30, id="forecast_cycle")
        scheduler.add_job(check_vehicle_returns, "interval", minutes=5, id="vehicle_returns")
        scheduler.start()
        logger.info("APScheduler started")
        app.state.scheduler = scheduler
    except Exception:
        logger.warning("Failed to start scheduler", exc_info=True)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.INFERENCE_URL}/health")
            logger.info("Inference service warm-up: %s", resp.json())
    except Exception:
        logger.warning("Inference service not reachable during startup")

    yield

    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)
    await engine.dispose()


app = FastAPI(title="Transport Dispatch API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

app.include_router(upload.router)
app.include_router(forecasts.router)
app.include_router(vehicles.router)
app.include_router(orders.router)
app.include_router(analytics.router)
app.include_router(config.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": str(exc),
        },
        media_type="application/problem+json",
    )


@app.get("/health")
async def health():
    checks = {}

    try:
        from sqlalchemy import text
        from app.database import async_session
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        checks["redis"] = "ok"
        await r.aclose()
    except Exception as e:
        checks["redis"] = f"error: {e}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.INFERENCE_URL}/health")
            checks["inference"] = resp.json()
    except Exception as e:
        checks["inference"] = f"error: {e}"

    status = "ok" if all(v == "ok" or (isinstance(v, dict) and v.get("status") == "ok") for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
