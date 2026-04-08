"""Load and serve all model artifacts on startup."""

import json
import logging
import os
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models"))
FORECAST_POINTS = 10
FUTURE_TARGET_COLS = [f"target_step_{s}" for s in range(1, FORECAST_POINTS + 1)]
OOF_CHAIN_STEPS = 4


class ModelRegistry:
    def __init__(self) -> None:
        self.ridge_pipeline = None
        self.ridge_calib: tuple | None = None
        self.catboost_v1_models: dict = {}
        self.catboost_v1_calib: dict = {}
        self.catboost_v2_models: dict = {}
        self.catboost_v2_calib: dict = {}
        self.blend_weights: dict[str, float] = {}
        self.confidence_curve: dict[str, float] = {}
        self._loaded = False

    @property
    def models_loaded(self) -> int:
        count = 0
        if self.ridge_pipeline is not None:
            count += 1
        count += len(self.catboost_v1_models)
        count += len(self.catboost_v2_models)
        return count

    def load_all(self) -> None:
        self._load_ridge()
        self._load_catboost("catboost_v1.pkl", is_v2=False)
        self._load_catboost("catboost_v2.pkl", is_v2=True)
        self._load_blend_weights()
        self._load_confidence_curve()
        self._loaded = True
        logger.info("All models loaded. Total: %d", self.models_loaded)

    def _load_ridge(self) -> None:
        path = MODEL_DIR / "ridge.pkl"
        if not path.exists():
            logger.warning("Ridge model not found at %s", path)
            return
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.ridge_pipeline = data["models"]
        self.ridge_calib = data["calib"]
        logger.info("Ridge model loaded from %s", path)

    def _load_catboost(self, filename: str, *, is_v2: bool) -> None:
        path = MODEL_DIR / filename
        if not path.exists():
            logger.warning("CatBoost model not found at %s", path)
            return
        with open(path, "rb") as f:
            data = pickle.load(f)
        if is_v2:
            self.catboost_v2_models = data["models"]
            self.catboost_v2_calib = data["calib"]
        else:
            self.catboost_v1_models = data["models"]
            self.catboost_v1_calib = data["calib"]
        logger.info("CatBoost model loaded from %s (%d horizons)", path, len(data["models"]))

    def _load_blend_weights(self) -> None:
        path = MODEL_DIR / "blend_weights.json"
        if not path.exists():
            self.blend_weights = {"cat": 0.35, "cat_improved": 0.45, "ridge": 0.20}
            logger.warning("blend_weights.json not found, using defaults")
            return
        with open(path) as f:
            self.blend_weights = json.load(f)
        logger.info("Blend weights loaded: %s", self.blend_weights)

    def _load_confidence_curve(self) -> None:
        path = MODEL_DIR / "confidence_curve.json"
        if not path.exists():
            self.confidence_curve = {
                f"h{i}": max(0.95 - 0.06 * (i - 1), 0.40)
                for i in range(1, FORECAST_POINTS + 1)
            }
            logger.warning("confidence_curve.json not found, using heuristic defaults")
            return
        with open(path) as f:
            self.confidence_curve = json.load(f)
        logger.info("Confidence curve loaded: %s", self.confidence_curve)


registry = ModelRegistry()
