"""Inference logic: feature engineering, multi-model prediction, blending."""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from .feature_engineering import (
    DROP_COLS,
    FORECAST_POINTS,
    FUTURE_TARGET_COLS,
    OFFICE_COL,
    ROUTE_COL,
    TARGET_COL,
    TIME_COL,
    make_features,
)
from .model_registry import ModelRegistry, OOF_CHAIN_STEPS
from .schemas import (
    FeatureRow,
    HorizonPrediction,
    PredictResponse,
    RoutePrediction,
)

logger = logging.getLogger(__name__)


def _rows_to_dataframe(rows: list[FeatureRow]) -> pd.DataFrame:
    records = []
    for r in rows:
        records.append({
            ROUTE_COL: r.route_id,
            OFFICE_COL: r.office_from_id,
            TIME_COL: r.timestamp,
            "status_1": r.status_1,
            "status_2": r.status_2,
            "status_3": r.status_3,
            "status_4": r.status_4,
            "status_5": r.status_5,
            "status_6": r.status_6,
            "status_7": r.status_7,
            "status_8": r.status_8,
            TARGET_COL: r.target_2h if r.target_2h is not None else 0.0,
            "pipeline_velocity": r.pipeline_velocity,
        })
    df = pd.DataFrame(records)
    df[TIME_COL] = pd.to_datetime(df[TIME_COL])
    df = df.sort_values([ROUTE_COL, TIME_COL]).reset_index(drop=True)
    return df


def _predict_catboost(
    X: pd.DataFrame,
    models: dict,
    calib: dict,
    oof_chain_steps: int,
) -> pd.DataFrame:
    """Per-horizon CatBoost prediction with OOF chaining and calibration."""
    cat_id_cols = [ROUTE_COL]
    if OFFICE_COL in X.columns:
        cat_id_cols.append(OFFICE_COL)

    out: dict[str, np.ndarray] = {}
    prev_preds: dict[str, np.ndarray] = {}

    for i, tgt in enumerate(FUTURE_TARGET_COLS):
        Xi = X.copy()
        for prev_tgt, arr in prev_preds.items():
            Xi[f"pred_{prev_tgt}"] = arr
        h = i + 1
        Xi["horizon"] = h
        Xi["horizon_sq"] = h ** 2
        Xi["horizon_log"] = np.log1p(h)

        raw = np.expm1(models[tgt].predict(Xi)).clip(0)
        a, b = calib[tgt]
        yhat = np.clip(a * raw + b, 0, None)
        out[tgt] = yhat
        if i < oof_chain_steps:
            prev_preds[tgt] = yhat

    return pd.DataFrame(out)


def _predict_ridge(
    X: pd.DataFrame,
    pipeline,
    calib_tuple: tuple,
) -> pd.DataFrame:
    """Ridge prediction across all horizons at once, with per-horizon calibration."""
    raw = pd.DataFrame(pipeline.predict(X), columns=FUTURE_TARGET_COLS)
    calib_a, calib_b = calib_tuple
    for i, tgt in enumerate(FUTURE_TARGET_COLS):
        a, b = calib_a[i], calib_b[i]
        raw[tgt] = np.clip(a * raw[tgt].values + b, 0, None)
    return raw


def run_inference(rows: list[FeatureRow], reg: ModelRegistry) -> PredictResponse:
    df = _rows_to_dataframe(rows)

    df_feat = make_features(df)

    inference_ts = df_feat[TIME_COL].max()
    inference_rows = df_feat[df_feat[TIME_COL] == inference_ts].copy()

    if inference_rows.empty:
        inference_rows = df_feat.groupby(ROUTE_COL).tail(1).copy()

    _exclude = {TARGET_COL, TIME_COL, "id", *FUTURE_TARGET_COLS}
    feature_cols = [c for c in inference_rows.columns if c not in _exclude]

    X = inference_rows[feature_cols].copy()
    existing_drop = [c for c in DROP_COLS if c in X.columns]
    X.drop(columns=existing_drop, inplace=True)

    if "route_mean_target2" in inference_rows.columns:
        X["route_mean_target"] = inference_rows["route_mean_target2"].values
    if "route_std_target2" in inference_rows.columns:
        X["route_std_target"] = inference_rows["route_std_target2"].values

    cat_id_cols = [ROUTE_COL]
    if OFFICE_COL in X.columns:
        cat_id_cols.append(OFFICE_COL)
    for c in cat_id_cols:
        if c in X.columns:
            X[c] = X[c].astype("string")

    preds: dict[str, pd.DataFrame] = {}

    if reg.ridge_pipeline is not None and reg.ridge_calib is not None:
        X_ridge = X.copy()
        missing_ridge = set(reg.ridge_pipeline.feature_names_in_) - set(X_ridge.columns)
        for col in missing_ridge:
            X_ridge[col] = 0.0
        X_ridge = X_ridge[list(reg.ridge_pipeline.feature_names_in_)]
        preds["ridge"] = _predict_ridge(X_ridge, reg.ridge_pipeline, reg.ridge_calib)

    if reg.catboost_v2_models:
        first_model = next(iter(reg.catboost_v2_models.values()))
        feature_names = [f for f in first_model.feature_names_ if "horizon" not in f and not f.startswith("pred_")]
        X_cb = X.copy()
        missing_cb = set(feature_names) - set(X_cb.columns)
        for col in missing_cb:
            X_cb[col] = 0.0
        X_cb = X_cb[[c for c in feature_names if c in X_cb.columns]]
        preds["cat_improved"] = _predict_catboost(
            X_cb, reg.catboost_v2_models, reg.catboost_v2_calib, OOF_CHAIN_STEPS
        )

    if reg.catboost_v1_models:
        first_model = next(iter(reg.catboost_v1_models.values()))
        feature_names = [f for f in first_model.feature_names_ if "horizon" not in f and not f.startswith("pred_")]
        X_cb1 = X.copy()
        if "route_mean_target2" in inference_rows.columns:
            X_cb1["route_mean_target"] = inference_rows["route_mean_target2"].values
        if "route_std_target2" in inference_rows.columns:
            X_cb1["route_std_target"] = inference_rows["route_std_target2"].values
        missing_cb1 = set(feature_names) - set(X_cb1.columns)
        for col in missing_cb1:
            X_cb1[col] = 0.0
        X_cb1 = X_cb1[[c for c in feature_names if c in X_cb1.columns]]
        preds["cat"] = _predict_catboost(
            X_cb1, reg.catboost_v1_models, reg.catboost_v1_calib, OOF_CHAIN_STEPS
        )

    weights = reg.blend_weights
    blended = np.zeros((len(inference_rows), FORECAST_POINTS))
    total_weight = 0.0
    for name, pred_df in preds.items():
        w = weights.get(name, 0.0)
        blended += w * pred_df.values
        total_weight += w
    if total_weight > 0:
        blended /= total_weight

    blended = np.clip(blended, 0, None)

    std_estimates = np.std(
        np.stack([p.values for p in preds.values()], axis=0), axis=0
    ) if len(preds) > 1 else np.full_like(blended, blended.mean() * 0.15)

    route_ids = inference_rows[ROUTE_COL].values
    office_ids = inference_rows[OFFICE_COL].values if OFFICE_COL in inference_rows.columns else ["unknown"] * len(inference_rows)
    timestamps = inference_rows[TIME_COL].values

    predictions = []
    for row_idx in range(len(inference_rows)):
        horizons = []
        for h in range(1, FORECAST_POINTS + 1):
            y_hat = float(blended[row_idx, h - 1])
            conf = reg.confidence_curve.get(f"h{h}", 0.5)
            std_val = float(std_estimates[row_idx, h - 1]) if std_estimates is not None else y_hat * 0.15
            spread = 1.5 * std_val
            horizons.append(HorizonPrediction(
                horizon=h,
                minutes_ahead=h * 30,
                y_hat=round(y_hat, 4),
                confidence=conf,
                y_hat_low=round(max(0, y_hat - spread), 4),
                y_hat_high=round(y_hat + spread, 4),
            ))
        ts_val = pd.Timestamp(timestamps[row_idx])
        predictions.append(RoutePrediction(
            route_id=str(route_ids[row_idx]),
            office_from_id=str(office_ids[row_idx]),
            timestamp=ts_val.to_pydantic_datetime() if hasattr(ts_val, "to_pydantic_datetime") else ts_val.to_pydatetime(),
            horizons=horizons,
        ))

    return PredictResponse(predictions=predictions)
