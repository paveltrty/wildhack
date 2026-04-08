from datetime import datetime

from pydantic import BaseModel


class FeatureRow(BaseModel):
    route_id: str
    office_from_id: str
    timestamp: datetime
    status_1: float
    status_2: float
    status_3: float
    status_4: float
    status_5: float
    status_6: float
    status_7: float
    status_8: float
    target_2h: float | None = None
    pipeline_velocity: float
    hour_of_day: int
    day_of_week: int
    rolling_mean_2h: float
    rolling_std_2h: float


class PredictRequest(BaseModel):
    rows: list[FeatureRow]


class HorizonPrediction(BaseModel):
    horizon: int
    minutes_ahead: int
    y_hat: float
    confidence: float
    y_hat_low: float
    y_hat_high: float


class RoutePrediction(BaseModel):
    route_id: str
    office_from_id: str
    timestamp: datetime
    horizons: list[HorizonPrediction]


class PredictResponse(BaseModel):
    predictions: list[RoutePrediction]
