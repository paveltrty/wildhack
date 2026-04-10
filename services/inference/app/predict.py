import logging

import numpy as np
import pandas as pd

from .model_registry import FUTURE_TARGET_COLS, registry
from .schemas import (
    FeatureRow,
    HorizonPrediction,
    PredictResponse,
    RoutePrediction,
)

logger = logging.getLogger(__name__)

STATUS_COLS = [f"status_{i}" for i in range(1, 9)]


def _enrich_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute derived features from raw input to match train.py's make_features
    as closely as possible with single-row (no-history) data.
    """
    df = df.copy()

    ts = pd.to_datetime(df["timestamp"])
    hour = ts.dt.hour
    minute = ts.dt.minute
    dow = ts.dt.weekday
    month = ts.dt.month

    df["hour"] = hour
    df["minute"] = minute
    df["dow"] = dow
    df["day"] = ts.dt.day
    df["month"] = month
    df["weekofyear"] = ts.dt.isocalendar().week.values.astype(int)
    df["dayofyear"] = ts.dt.dayofyear
    df["is_weekend"] = (dow >= 5).astype(np.int8)
    df["slot_30m"] = (hour * 2 + minute // 30).astype(np.int16)
    df["hour_bucket"] = (hour // 6).astype(np.int16)
    df["is_rush_hour"] = hour.isin([7, 8, 9, 17, 18, 19]).astype(np.int8)
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24).astype(np.float32)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24).astype(np.float32)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7).astype(np.float32)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7).astype(np.float32)
    df["month_sin"] = np.sin(2 * np.pi * month / 12).astype(np.float32)
    df["month_cos"] = np.cos(2 * np.pi * month / 12).astype(np.float32)

    try:
        route_int = df["route_id"].astype(int)
    except (ValueError, TypeError):
        route_int = pd.factorize(df["route_id"])[0]

    df["route_hour_key"] = (route_int * 48 + df["slot_30m"]).astype(np.int64)
    df["route_dow_key"] = (route_int * 7 + df["dow"]).astype(np.int64)

    status_vals = df[STATUS_COLS]
    df["status_sum"] = status_vals.sum(axis=1).astype(np.float32)
    df["status_mean"] = status_vals.mean(axis=1).astype(np.float32)
    df["status_std"] = status_vals.std(axis=1).astype(np.float32)
    df["status_min"] = status_vals.min(axis=1).astype(np.float32)
    df["status_max"] = status_vals.max(axis=1).astype(np.float32)

    for c in STATUS_COLS:
        df[f"{c}_log"] = np.log1p(df[c]).astype(np.float32)

    for i in range(len(STATUS_COLS) - 1):
        c1, c2 = STATUS_COLS[i], STATUS_COLS[i + 1]
        df[f"{c2}_over_{c1}"] = (df[c2] / (df[c1] + 1.0)).astype(np.float32)

    weights = np.linspace(0.5, 2.0, len(STATUS_COLS))
    df["status_weighted_sum"] = sum(
        w * df[c] for w, c in zip(weights, STATUS_COLS)
    ).astype(np.float32)

    for c in STATUS_COLS:
        df[f"{c}_share"] = (df[c] / (df["status_sum"] + 1.0)).astype(np.float32)

    df["route_id"] = df["route_id"].astype("string")
    if "office_from_id" in df.columns:
        df["office_from_id"] = df["office_from_id"].astype("string")

    drop = ["timestamp", "hour_of_day", "day_of_week"]
    df.drop(columns=[c for c in drop if c in df.columns], inplace=True)

    return df


def run_prediction(rows: list[FeatureRow]) -> PredictResponse:
    if not rows:
        return PredictResponse(predictions=[])

    df = pd.DataFrame([r.model_dump() for r in rows])
    X = _enrich_features(df)

    blended = registry.predict_blended(X)

    predictions: list[RoutePrediction] = []
    for idx, row in enumerate(rows):
        horizons: list[HorizonPrediction] = []
        for h in range(1, 11):
            tgt = f"target_step_{h}"
            y_hat = float(blended[tgt][idx])
            conf = registry.get_confidence(h)
            margin = y_hat * (1 - conf)
            horizons.append(
                HorizonPrediction(
                    horizon=h,
                    minutes_ahead=h * 30,
                    y_hat=y_hat,
                    confidence=conf,
                    y_hat_low=max(0.0, y_hat - margin),
                    y_hat_high=y_hat + margin,
                )
            )

        predictions.append(
            RoutePrediction(
                route_id=row.route_id,
                office_from_id=row.office_from_id,
                timestamp=row.timestamp,
                horizons=horizons,
            )
        )

    logger.info(
        "Predicted %d routes × 10 horizons (3-model blend: cat=%.2f, cat_improved=%.2f, ridge=%.2f)",
        len(predictions),
        registry.blend_weights.get("cat", 0),
        registry.blend_weights.get("cat_improved", 0),
        registry.blend_weights.get("ridge", 0),
        extra={"batch_size": len(rows)},
    )
    return PredictResponse(predictions=predictions)
