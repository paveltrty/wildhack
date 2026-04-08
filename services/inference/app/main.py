"""Inference microservice: FastAPI application with /health and /predict endpoints."""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from prometheus_client import Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pythonjsonlogger import jsonlogger

from .model_registry import registry
from .predict import run_inference
from .schemas import PredictRequest, PredictResponse

log_level = os.getenv("LOG_LEVEL", "info").upper()
logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(getattr(logging, log_level, logging.INFO))

INFERENCE_DURATION = Histogram(
    "inference_duration_seconds",
    "Predict endpoint latency in seconds",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
INFERENCE_BATCH_SIZE = Histogram(
    "inference_batch_size",
    "Number of rows per predict request",
    buckets=[1, 5, 10, 50, 100, 500, 1000],
)
MODEL_MAE_BY_HORIZON = Gauge(
    "model_mae_by_horizon",
    "MAE per horizon (updated externally)",
    ["horizon"],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry.load_all()
    yield


app = FastAPI(title="Inference Service", version="1.0.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health():
    return {"status": "ok", "models_loaded": registry.models_loaded}


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    if not request.rows:
        raise HTTPException(status_code=400, detail="No rows provided")

    INFERENCE_BATCH_SIZE.observe(len(request.rows))
    start = time.perf_counter()

    try:
        response = run_inference(request.rows, registry)
    except Exception as e:
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail=str(e))

    duration = time.perf_counter() - start
    INFERENCE_DURATION.observe(duration)
    logger.info("Inference completed", extra={
        "duration_s": round(duration, 3),
        "batch_size": len(request.rows),
        "predictions": len(response.predictions),
    })

    return response
