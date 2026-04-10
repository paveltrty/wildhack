import json
import logging
import os
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_DIR = os.getenv("MODEL_DIR", "/models")

FORECAST_POINTS = 10
FUTURE_TARGET_COLS = [f"target_step_{s}" for s in range(1, FORECAST_POINTS + 1)]
OOF_CHAIN_STEPS = 4

DEFAULT_BLEND_WEIGHTS = {
    "cat": 0.4371186381672598,
    "cat_improved": 0.24215179353593602,
    "ridge": 0.3207295682968041,
}

DEFAULT_CONFIDENCE_CURVE = {
    1: 0.95, 2: 0.88, 3: 0.80, 4: 0.72, 5: 0.63,
    6: 0.55, 7: 0.47, 8: 0.41, 9: 0.36, 10: 0.31,
}


class ModelRegistry:
    def __init__(self) -> None:
        self.cat_models: dict[str, Any] = {}
        self.cat_calib: dict[str, tuple[float, float]] = {}
        self.cat_improved_models: dict[str, Any] = {}
        self.cat_improved_calib: dict[str, tuple[float, float]] = {}
        self.ridge_pipeline: Any = None
        self.ridge_calib_a: np.ndarray | None = None
        self.ridge_calib_b: np.ndarray | None = None
        self.blend_weights: dict[str, float] = DEFAULT_BLEND_WEIGHTS.copy()
        self.confidence_curve: dict[int, float] = DEFAULT_CONFIDENCE_CURVE.copy()

    def load(self) -> None:
        model_dir = Path(MODEL_DIR)

        blend_path = model_dir / "blend_weights.json"
        if blend_path.exists():
            with open(blend_path) as f:
                self.blend_weights = json.load(f)

        conf_path = model_dir / "confidence_curve.json"
        if conf_path.exists():
            with open(conf_path) as f:
                raw = json.load(f)
                self.confidence_curve = {int(k): v for k, v in raw.items()}

        self._load_models(model_dir)
        logger.info("Loaded real models from %s", MODEL_DIR)

    def _load_models(self, model_dir: Path) -> None:
        cat_v1_path = model_dir / "catboost_v1.pkl"
        if not cat_v1_path.exists():
            raise FileNotFoundError(f"catboost_v1.pkl not found in {model_dir}")
        with open(cat_v1_path, "rb") as f:
            data = pickle.load(f)
        self.cat_models = data["models"]
        self.cat_calib = data["calib"]

        cat_v2_path = model_dir / "catboost_v2.pkl"
        if not cat_v2_path.exists():
            raise FileNotFoundError(f"catboost_v2.pkl not found in {model_dir}")
        with open(cat_v2_path, "rb") as f:
            data = pickle.load(f)
        self.cat_improved_models = data["models"]
        self.cat_improved_calib = data["calib"]

        ridge_path = model_dir / "ridge.pkl"
        if not ridge_path.exists():
            raise FileNotFoundError(f"ridge.pkl not found in {model_dir}")
        with open(ridge_path, "rb") as f:
            data = pickle.load(f)
        self.ridge_pipeline = data["models"]
        self.ridge_calib_a, self.ridge_calib_b = data["calib"]

    def _align_features(self, Xi: pd.DataFrame, model: Any) -> pd.DataFrame:
        """Align DataFrame columns to what the model expects, filling gaps with NaN."""
        if not hasattr(model, "feature_names_"):
            return Xi
        expected = list(model.feature_names_)
        missing = [c for c in expected if c not in Xi.columns]
        if missing:
            nan_df = pd.DataFrame(
                np.nan, index=Xi.index, columns=missing, dtype=np.float32
            )
            Xi = pd.concat([Xi, nan_df], axis=1)
        return Xi[expected]

    def predict_cat_family(
        self,
        X: pd.DataFrame,
        models: dict[str, Any],
        calib: dict[str, tuple[float, float]],
    ) -> dict[str, np.ndarray]:
        """
        Predict all 10 horizons for a CatBoost model family.
        Mirrors _predict_cat from train.py: log-space prediction,
        expm1 transform, calibration, OOF chaining for first 4 steps.
        """
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

            model = models[tgt]
            Xi = self._align_features(Xi, model)
            raw = np.clip(np.expm1(model.predict(Xi)), 0, None)

            a, b = calib[tgt]
            yhat = np.clip(a * np.asarray(raw) + b, 0, None)
            out[tgt] = yhat

            if i < OOF_CHAIN_STEPS:
                prev_preds[tgt] = yhat

        return out

    def predict_ridge(self, X: pd.DataFrame) -> dict[str, np.ndarray]:
        """
        Predict all 10 horizons with Ridge pipeline.
        Multi-output prediction + per-horizon calibration.
        """
        if hasattr(self.ridge_pipeline, "feature_names_in_"):
            expected = list(self.ridge_pipeline.feature_names_in_)
            Xi = X.copy()
            missing = [c for c in expected if c not in Xi.columns]
            if missing:
                nan_df = pd.DataFrame(
                    np.nan, index=Xi.index, columns=missing, dtype=np.float32
                )
                Xi = pd.concat([Xi, nan_df], axis=1)
            Xi = Xi[expected]
        else:
            Xi = X

        raw = self.ridge_pipeline.predict(Xi)
        if raw.ndim == 1:
            raw = raw.reshape(-1, FORECAST_POINTS)

        out: dict[str, np.ndarray] = {}
        for i, tgt in enumerate(FUTURE_TARGET_COLS):
            a = float(self.ridge_calib_a[i])
            b = float(self.ridge_calib_b[i])
            out[tgt] = np.clip(a * raw[:, i] + b, 0, None)
        return out

    def predict_blended(self, X: pd.DataFrame) -> dict[str, np.ndarray]:
        """Predict all horizons with the 3-model weighted ensemble."""
        w = self.blend_weights

        cat_preds = self.predict_cat_family(X, self.cat_models, self.cat_calib)
        cat_imp_preds = self.predict_cat_family(
            X, self.cat_improved_models, self.cat_improved_calib
        )
        ridge_preds = self.predict_ridge(X)

        blended: dict[str, np.ndarray] = {}
        w_cat = w.get("cat", 0.0)
        w_imp = w.get("cat_improved", 0.0)
        w_ridge = w.get("ridge", 0.0)

        for tgt in FUTURE_TARGET_COLS:
            blended[tgt] = (
                w_cat * cat_preds[tgt]
                + w_imp * cat_imp_preds[tgt]
                + w_ridge * ridge_preds[tgt]
            )
        return blended

    def get_confidence(self, h: int) -> float:
        return self.confidence_curve.get(h, 0.5)


registry = ModelRegistry()
