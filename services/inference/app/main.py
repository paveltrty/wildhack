import logging
import sys

from fastapi import FastAPI
from pythonjsonlogger import jsonlogger

from .model_registry import registry
from .predict import run_prediction
from .schemas import PredictRequest, PredictResponse

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)

app = FastAPI(title="Inference Service", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    registry.load()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest) -> PredictResponse:
    return run_prediction(request.rows)
