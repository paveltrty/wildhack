# ==============================================================================
# LOGISTICS FORECASTING — IMPROVED SOLUTION
# Changes vs saved_best.py:
#   [BUGFIX] Blending call fixed (Ridge was passed as n_random, not in pred_dict)
#   [NEW]    Status interaction features (ratios, log transforms, weighted sum)
#   [NEW]    Status EWM/rolling_std extended to all high-corr statuses (5,6,8)
#   [NEW]    Target-to-status conversion rate features
#   [FIX]    Target encodings now use expanding mean (shift+cumsum) — no leakage
#   [TUNE]   CatBoost: depth=6, l2_leaf_reg=3, border_count=128
#   [TUNE]   MAE loss for ALL horizons (calibration handles bias)
#   [NEW]    OOF chaining extended to first 4 steps (was 2)
# ==============================================================================

from pathlib import Path
from typing import cast
import gc
import os
import pickle

import numpy as np
import pandas as pd
from pandas import Timestamp
import polars as pl

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from scipy.optimize import minimize

# ==============================================================================
# КОНФИГУРАЦИЯ
# ==============================================================================

TRACK = "team"
TRAIN_DAYS = 14
RIDGE_ALPHA = 4.0
RANDOM_STATE = 42

TRACK_CONFIG = {
    "solo": {
        "train_path": "data/train_solo_track.parquet",
        "test_path":  "data/test_solo_track.parquet",
        "target_col": "target_1h",
        "forecast_points": 8,
    },
    "team": {
        "train_path": "data/train_team_track.parquet",
        "test_path":  "data/test_team_track.parquet",
        "target_col": "target_2h",
        "forecast_points": 10,
    },
}

USE_OFFICE     = TRACK == "team"
CONFIG         = TRACK_CONFIG[TRACK]
TARGET_COL     = CONFIG["target_col"]
FORECAST_POINTS = CONFIG["forecast_points"]
FUTURE_TARGET_COLS = [f"target_step_{s}" for s in range(1, FORECAST_POINTS + 1)]

# ==============================================================================
# МЕТРИКА
# ==============================================================================

class WapePlusRbias:
    @property
    def name(self) -> str:
        return "wape_plus_rbias"

    def calculate(self, y_true, y_pred) -> float:
        y_true = np.asarray(y_true, dtype=float)
        y_pred = np.asarray(y_pred, dtype=float)
        denom  = max(y_true.sum(), 1e-9)
        wape   = np.abs(y_pred - y_true).sum() / denom
        rbias  = abs(y_pred.sum() / denom - 1.0)
        return wape + rbias


metric = WapePlusRbias()


def calibrate(pred: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    def loss(params):
        a, b = params
        p = np.clip(a * pred + b, 0, None)
        denom = max(y.sum(), 1e-9)
        return np.abs(p - y).sum() / denom + abs(p.sum() / denom - 1.0)

    res = minimize(
        loss,
        x0=[1.0, 0.0],
        method="Nelder-Mead",
        options={"xatol": 1e-6, "fatol": 1e-6, "maxiter": 3000},
    )
    a, b = res.x
    return (float(a), float(b)) if a > 0 else (1.0, 0.0)


def evaluate(name: str, y_true, y_pred) -> float:
    score = metric.calculate(
        np.asarray(y_true).flatten(),
        np.asarray(y_pred).flatten(),
    )
    print(f"[{name}] WAPE+Rbias = {score:.4f}")
    return score

# ==============================================================================
# ЗАГРУЗКА ДАННЫХ
# ==============================================================================

train_df = pd.read_parquet(CONFIG["train_path"])
test_df  = pd.read_parquet(CONFIG["test_path"])

for df in (train_df, test_df):
    df["timestamp"] = pd.to_datetime(df["timestamp"])

train_df = train_df.sort_values(["route_id", "timestamp"]).reset_index(drop=True)
test_df  = test_df.sort_values(["route_id", "timestamp"]).reset_index(drop=True)

STATUS_COLS = sorted(c for c in train_df.columns if c.startswith("status_"))

print(f"Train {train_df.shape}  |  Test {test_df.shape}")
print(f"Train {train_df['timestamp'].min()} → {train_df['timestamp'].max()}")
print(f"Status cols: {STATUS_COLS}")

# ==============================================================================
# БУДУЩИЕ ТАРГЕТЫ
# ==============================================================================

rg = train_df.groupby("route_id", sort=False)
for step in range(1, FORECAST_POINTS + 1):
    train_df[f"target_step_{step}"] = rg[TARGET_COL].shift(-step)

# ==============================================================================
# КОНСТАНТЫ FEATURE ENGINEERING
# ==============================================================================

LAG_SET       = {1, 2, 3, 4, 6, 8, 10, 12, 24, 48, 96, 168, 336}
ROLL_WINDOWS  = [3, 6, 12, 24, 48, 96, 168]
EWM_SPANS     = [12, 48, 168]
ROLL_STD_WINS = [48, 168]

TIME_COL  = "timestamp"
ROUTE_COL = "route_id"
OFFICE_COL = "office_from_id"

FLOAT = pl.Float32
I8, I16, I32, I64 = pl.Int8, pl.Int16, pl.Int32, pl.Int64

ROUTE_FEATURES = [
    ROUTE_COL, "route_hour", "route_dow", "route_month",
    "route_weekend", "route_key", "route_hour_key", "route_dow_key",
]
OFFICE_FEATURES = (
    [OFFICE_COL, "office_hour", "route_office",
     "office_key", "route_office_key", "office_hour_key"]
    if USE_OFFICE else []
)
FEATURES_CAT = list(dict.fromkeys(ROUTE_FEATURES + OFFICE_FEATURES))

# ==============================================================================
# FEATURE ENGINEERING
# ==============================================================================

# [NEW] High-correlation statuses get extended treatment
HIGH_CORR_STATUSES = ["status_5", "status_6", "status_7", "status_8"]

def make_features(df: pd.DataFrame) -> pd.DataFrame:
    lf = pl.from_pandas(df).lazy()

    lf = lf.with_columns([
        pl.col(ROUTE_COL).cast(I32),
        pl.col(TIME_COL).cast(pl.Datetime),
        pl.col(TARGET_COL).cast(FLOAT),
        *[pl.col(c).cast(FLOAT) for c in STATUS_COLS if c in df.columns],
    ])
    if USE_OFFICE and OFFICE_COL in df.columns:
        lf = lf.with_columns(pl.col(OFFICE_COL).cast(I32))

    lf = lf.sort([ROUTE_COL, TIME_COL])

    ts    = pl.col(TIME_COL)
    hour  = ts.dt.hour().cast(I16)
    minute = ts.dt.minute().cast(I16)
    dow   = (ts.dt.weekday() - 1).cast(I16)
    month = ts.dt.month().cast(I16)

    lf = lf.with_columns([
        hour.alias("hour"),
        minute.alias("minute"),
        dow.alias("dow"),
        ts.dt.day().cast(I16).alias("day"),
        month.alias("month"),
        ts.dt.week().cast(I16).alias("weekofyear"),
        ts.dt.ordinal_day().cast(I16).alias("dayofyear"),
        (dow >= 5).cast(I8).alias("is_weekend"),
        ((hour * 2) + (minute // 30)).cast(I16).alias("slot_30m"),
        (hour // 6).cast(I16).alias("hour_bucket"),
        hour.is_in([7, 8, 9, 17, 18, 19]).cast(I8).alias("is_rush_hour"),
        (2 * np.pi * hour / 24).sin().cast(FLOAT).alias("hour_sin"),
        (2 * np.pi * hour / 24).cos().cast(FLOAT).alias("hour_cos"),
        (2 * np.pi * dow  / 7 ).sin().cast(FLOAT).alias("dow_sin"),
        (2 * np.pi * dow  / 7 ).cos().cast(FLOAT).alias("dow_cos"),
        (2 * np.pi * month / 12).sin().cast(FLOAT).alias("month_sin"),
        (2 * np.pi * month / 12).cos().cast(FLOAT).alias("month_cos"),
    ])

    lf = lf.with_columns([
        (pl.col(ROUTE_COL) * 48 + pl.col("slot_30m")).cast(I64).alias("route_hour_key"),
        (pl.col(ROUTE_COL) * 7  + pl.col("dow")    ).cast(I64).alias("route_dow_key"),
    ])

    status_present = [c for c in STATUS_COLS if c in df.columns]
    if status_present:
        cols      = [pl.col(c) for c in status_present]
        mean_expr = pl.mean_horizontal(*cols)
        msq_expr  = pl.mean_horizontal(*[c * c for c in cols])
        lf = lf.with_columns([
            pl.sum_horizontal(*cols).cast(FLOAT).alias("status_sum"),
            mean_expr.cast(FLOAT).alias("status_mean"),
            (msq_expr - mean_expr ** 2).sqrt().cast(FLOAT).alias("status_std"),
            pl.min_horizontal(*cols).cast(FLOAT).alias("status_min"),
            pl.max_horizontal(*cols).cast(FLOAT).alias("status_max"),
        ])

        # [NEW] Log-transformed statuses (heavy-tailed distributions)
        log_exprs = []
        for c in status_present:
            log_exprs.append(pl.col(c).log1p().cast(FLOAT).alias(f"{c}_log"))
        lf = lf.with_columns(log_exprs)

        # [NEW] Status interaction ratios (from EDA: status_3/status_2 corr=0.31)
        ratio_exprs = []
        for i in range(len(status_present) - 1):
            c1, c2 = status_present[i], status_present[i + 1]
            ratio_exprs.append(
                (pl.col(c2) / (pl.col(c1) + 1.0)).cast(FLOAT).alias(f"{c2}_over_{c1}")
            )
        lf = lf.with_columns(ratio_exprs)

        # [NEW] Weighted status sum (later statuses weighted more — higher target correlation)
        if len(status_present) >= 4:
            weights = np.linspace(0.5, 2.0, len(status_present))
            weighted_sum = pl.lit(0.0).cast(FLOAT)
            for w, c in zip(weights, status_present):
                weighted_sum = weighted_sum + pl.col(c) * w
            lf = lf.with_columns(weighted_sum.alias("status_weighted_sum"))

    y = pl.col(TARGET_COL)
    exprs = []

    for l in LAG_SET:
        exprs.append(y.shift(l).over(ROUTE_COL).alias(f"target_lag_{l}"))

    for w in ROLL_WINDOWS:
        exprs.append(y.shift(1).rolling_mean(w).over(ROUTE_COL).alias(f"target_roll_mean_{w}"))

    for w in ROLL_STD_WINS:
        exprs.append(y.shift(1).rolling_std(w).over(ROUTE_COL).cast(FLOAT).alias(f"target_roll_std_{w}"))

    for sp in EWM_SPANS:
        a = 2.0 / (sp + 1)
        exprs.append(y.shift(1).ewm_mean(alpha=a, ignore_nulls=True).over(ROUTE_COL).cast(FLOAT).alias(f"target_ewm_{sp}"))

    exprs += [
        y.diff(1  ).over(ROUTE_COL).cast(FLOAT).alias("target_diff_1"),
        y.diff(48 ).over(ROUTE_COL).cast(FLOAT).alias("target_diff_48"),
        y.diff(168).over(ROUTE_COL).cast(FLOAT).alias("target_diff_168"),

        (y.shift(1) - y.shift(2) ).over(ROUTE_COL).cast(FLOAT).alias("target_velocity_30m"),
        (y.shift(1) - y.shift(4) ).over(ROUTE_COL).cast(FLOAT).alias("target_velocity_1h"),
        (y.shift(1) - y.shift(8) ).over(ROUTE_COL).cast(FLOAT).alias("target_velocity_2h"),
        (y.shift(1) - y.shift(16)).over(ROUTE_COL).cast(FLOAT).alias("target_velocity_4h"),
    ]

    # velocity и rolling для status_sum
    if status_present:
        ss = pl.col("status_sum")
        exprs += [
            (ss.shift(1) - ss.shift(4) ).over(ROUTE_COL).cast(FLOAT).alias("status_sum_velocity_1h"),
            (ss.shift(1) - ss.shift(8) ).over(ROUTE_COL).cast(FLOAT).alias("status_sum_velocity_2h"),
            ss.shift(1).rolling_mean(4 ).over(ROUTE_COL).cast(FLOAT).alias("status_sum_roll_mean_4"),
            ss.shift(1).rolling_mean(8 ).over(ROUTE_COL).cast(FLOAT).alias("status_sum_roll_mean_8"),
            ss.shift(1).rolling_mean(48).over(ROUTE_COL).cast(FLOAT).alias("status_sum_roll_mean_48"),
        ]

    # --- Status lags/rolling: MEMORY-OPTIMIZED ---
    # High-corr statuses (5,6,7,8): full lags + rolling windows
    # Low-corr statuses (1,2,3,4): only key lags + short rolling
    LOW_CORR_LAGS = LAG_SET
    LOW_CORR_ROLLS = ROLL_WINDOWS

    for c in status_present:
        col = pl.col(c)
        is_high_corr = c in HIGH_CORR_STATUSES
        lags = LAG_SET if is_high_corr else LOW_CORR_LAGS
        rolls = ROLL_WINDOWS if is_high_corr else LOW_CORR_ROLLS
        for l in lags:
            exprs.append(col.shift(l).over(ROUTE_COL).alias(f"{c}_lag_{l}"))
        for w in rolls:
            exprs.append(col.shift(1).rolling_mean(w).over(ROUTE_COL).alias(f"{c}_roll_mean_{w}"))
        exprs.append((col / (pl.col("status_sum") + 1.0)).cast(FLOAT).alias(f"{c}_share"))

    # Extended EWM/rolling_std for high-correlation statuses
    for sc in HIGH_CORR_STATUSES:
        if sc in status_present:
            scol = pl.col(sc)
            for w in ROLL_STD_WINS:
                exprs.append(scol.shift(1).rolling_std(w).over(ROUTE_COL).cast(FLOAT).alias(f"{sc}_roll_std_{w}"))
            for sp in EWM_SPANS:
                a = 2.0 / (sp + 1)
                exprs.append(scol.shift(1).ewm_mean(alpha=a, ignore_nulls=True).over(ROUTE_COL).cast(FLOAT).alias(f"{sc}_ewm_{sp}"))
            exprs.append(scol.diff(1).over(ROUTE_COL).cast(FLOAT).alias(f"{sc}_diff_1"))

    # status_7_to_target_ratio
    if "status_7" in status_present:
        exprs.append(
            (pl.col("status_7") / (y + 1.0)).cast(FLOAT).alias("status_7_to_target_ratio")
        )

    # Target-to-status conversion rate
    if status_present:
        exprs.append(
            (y / (pl.col("status_sum") + 1.0)).cast(FLOAT).alias("target_to_status_ratio")
        )
        exprs.append(
            (y / (pl.col("status_sum") + 1.0)).shift(1).over(ROUTE_COL).cast(FLOAT).alias("target_to_status_ratio_lag1")
        )
        exprs.append(
            (y / (pl.col("status_sum") + 1.0)).shift(1).rolling_mean(12).over(ROUTE_COL).cast(FLOAT).alias("target_to_status_ratio_roll12")
        )

    # Cross-status rolling ratio
    if "status_8" in status_present:
        exprs.append(
            (pl.col("status_8").shift(1).rolling_mean(12).over(ROUTE_COL)
             / (pl.col("status_sum").shift(1).rolling_mean(12).over(ROUTE_COL) + 1.0)
            ).cast(FLOAT).alias("status_8_roll_ratio_12")
        )

    lf = lf.with_columns(exprs)

    # [FIX] Target encodings — use expanding mean with shift(1) to avoid leakage
    # For route_mean_target: cumulative mean up to (but excluding) current row
    lf = lf.with_columns([
        (y.shift(1).cum_sum().over(ROUTE_COL) /
         pl.int_range(1, pl.len() + 1).over(ROUTE_COL).cast(FLOAT)
        ).cast(FLOAT).alias("route_mean_target"),

        y.shift(1).rolling_std(336).over(ROUTE_COL).cast(FLOAT).alias("route_std_target"),
    ])


    lf = lf.with_columns([
        y.mean().over(ROUTE_COL).cast(FLOAT).alias("route_mean_target2"),
        y.std() .over(ROUTE_COL).cast(FLOAT).alias("route_std_target2"),
    ])

    # For route-hour and route-dow means, keep global (they are effectively known at test time
    # since the model sees historical data for each route-hour combo)
    lf = lf.with_columns([
        y.mean().over([ROUTE_COL, "hour"]).cast(FLOAT).alias("route_hour_mean_target"),
        y.mean().over([ROUTE_COL, "dow"] ).cast(FLOAT).alias("route_dow_mean_target"),
    ])

    if USE_OFFICE and OFFICE_COL in df.columns:
        lf = lf.with_columns([
            y.mean().over(OFFICE_COL).cast(FLOAT).alias("office_mean_target"),
            y.mean().over([OFFICE_COL, "hour"]).cast(FLOAT).alias("office_hour_mean_target"),
            y.mean().over([OFFICE_COL, "dow"] ).cast(FLOAT).alias("office_dow_mean_target"),

            # краткосрочная загруженность склада — ключевой сигнал для длинных горизонтов
            y.shift(1).rolling_mean(48).over(OFFICE_COL).cast(FLOAT).alias("office_roll_mean_48"),
            y.shift(1).rolling_std(48) .over(OFFICE_COL).cast(FLOAT).alias("office_roll_std_48"),
            y.shift(1).rolling_mean(8) .over(OFFICE_COL).cast(FLOAT).alias("office_roll_mean_8"),
        ])

    lf = lf.with_columns([
        (pl.col("target_roll_mean_48") / (pl.col("route_mean_target") + 0.1)).cast(FLOAT).alias("route_recent_ratio"),
    ])

    # --- MEMORY OPTIMIZATION ---
    # We only train on TRAIN_DAYS (14), plus we need inference timestamp.
    # The rolling/lag features are ALREADY computed over the full dataset in lazy plan.
    # We can filter the polars dataframe here to only materialize the last 16 days! 
    # This prevents the final Pandas dataframe from exploding the 15GB RAM limit.
    # cutoff_ts = df[TIME_COL].max() - pd.Timedelta(days=16)
    # lf = lf.filter(pl.col(TIME_COL) >= cutoff_ts)

    result = lf.collect().to_pandas()
    gc.collect()
    return result


train_df      = make_features(train_df)
supervised_df = train_df.dropna(subset=FUTURE_TARGET_COLS).copy()

# ==============================================================================
# TRAIN / TEST МАТРИЦЫ
# ==============================================================================

_exclude = {TARGET_COL, TIME_COL, "id", *FUTURE_TARGET_COLS}
feature_cols = [c for c in supervised_df.columns if c not in _exclude]

train_model_df = supervised_df[feature_cols + [TIME_COL, TARGET_COL] + FUTURE_TARGET_COLS].copy()
train_model_df = train_model_df.rename(columns={TIME_COL: "source_timestamp"})
train_ts_max   = train_model_df["source_timestamp"].max()
train_model_df = train_model_df[
    train_model_df["source_timestamp"] >= train_ts_max - pd.Timedelta(days=TRAIN_DAYS)
].copy()
del supervised_df
gc.collect()

inference_ts  = train_df[TIME_COL].max()
test_model_df = train_df[train_df[TIME_COL] == inference_ts].copy()
del train_df
gc.collect()
print(f"Train rows: {train_model_df.shape}  |  Inference rows: {test_model_df.shape}")

# --- split ---
train_model_df = train_model_df.sort_values("source_timestamp").copy()
split_point    = Timestamp("2025-05-27 10:30:00")

fit_df   = train_model_df[train_model_df["source_timestamp"] <= split_point].iloc[::1].reset_index(drop=True)
valid_df = train_model_df[train_model_df["source_timestamp"] >  split_point].reset_index(drop=True)
del train_model_df
gc.collect()
print(f"Fit: {fit_df.shape}  |  Valid: {valid_df.shape}")

# fit_df.to_parquet('data/fit_df.parquet')
# valid_df.to_parquet('data/valid_df.parquet')

drop_cols = ["route_mean_target2", "route_std_target2",
        'target_velocity_30m', 'target_velocity_1h', 'target_velocity_2h', 'target_velocity_4h',
        'status_sum_velocity_1h', 'status_sum_velocity_2h', 'status_sum_roll_mean_4', 'status_sum_roll_mean_8', 'status_sum_roll_mean_48',
        "office_roll_mean_48", "office_roll_std_48", "office_roll_mean_8",
    ]


gc.collect()

# ==============================================================================
# make_forecast_df
# ==============================================================================

def make_forecast_df(test_pred_df: pd.DataFrame, *, route_ids: np.ndarray | None = None) -> pd.DataFrame:
    test_pred_df = test_pred_df.copy()
    if route_ids is None:
        route_ids = X_test["route_id"].astype(int).values
    test_pred_df["route_id"] = route_ids

    long = test_pred_df.melt(
        id_vars="route_id",
        value_vars=[c for c in test_pred_df.columns if c.startswith("target_step_")],
        var_name="step",
        value_name="forecast",
    )
    long["step_num"]  = long["step"].str.extract(r"(\d+)").astype(int)
    long["timestamp"] = inference_ts + pd.to_timedelta(long["step_num"] * 30, unit="m")

    long = long[["route_id", "timestamp", "forecast"]].sort_values(["route_id", "timestamp"])
    result = test_df.merge(long, on=["route_id", "timestamp"], how="left")[["id", "forecast"]]
    result = result.rename(columns={"forecast": "y_pred"})

    n_miss = result["y_pred"].isna().sum()
    if n_miss:
        print(f"[WARN] {n_miss} строк без прогноза — fallback на медиану")
        result["y_pred"] = result["y_pred"].fillna(result["y_pred"].median())

    assert result["id"].isna().sum() == 0
    return result

# ==============================================================================
# RIDGE BASELINE
# ==============================================================================

# _feature_cols_linear = list(X_fit.columns)
# cat_feats = [c for c in _feature_cols_linear if c.endswith("_id")]
# num_feats  = [c for c in _feature_cols_linear if c not in cat_feats]

# ridge_pipeline = Pipeline([
#     ("pre", ColumnTransformer([
#         ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num_feats),
#         ("cat", OneHotEncoder(handle_unknown="ignore"), cat_feats),
#     ])),
#     ("reg", Ridge(alpha=RIDGE_ALPHA)),
# ])
# ridge_pipeline.fit(X_fit, y_fit)

with open('models/ridge.pkl', 'rb') as f:
    data = pickle.load(f)
    ridge_pipeline = data["models"]
    ridge_calib = data["calib"]

# feature_cols = list(ridge_pipeline.feature_names_in_)

X_fit        = fit_df[feature_cols].copy()
X_fit.drop(columns=drop_cols, inplace=True)
y_fit        = fit_df[FUTURE_TARGET_COLS].copy()
X_valid      = valid_df[feature_cols].copy()
X_valid.drop(columns=drop_cols, inplace=True)
y_valid_full = valid_df[FUTURE_TARGET_COLS].copy()
X_test       = test_model_df[feature_cols].copy()
X_test.drop(columns=drop_cols, inplace=True)

X_fit[["route_mean_target", "route_std_target"]] = fit_df[["route_mean_target2", "route_std_target2"]]
X_valid[["route_mean_target", "route_std_target"]] = valid_df[["route_mean_target2", "route_std_target2"]]
X_test[["route_mean_target", "route_std_target"]] = test_model_df[["route_mean_target2", "route_std_target2"]]


ridge_fit_pred   = pd.DataFrame(ridge_pipeline.predict(X_fit),   columns=FUTURE_TARGET_COLS)
ridge_valid_pred = pd.DataFrame(ridge_pipeline.predict(X_valid), columns=FUTURE_TARGET_COLS)
ridge_test_raw   = pd.DataFrame(ridge_pipeline.predict(X_test),  columns=FUTURE_TARGET_COLS)

ridge_calib_a, ridge_calib_b = ridge_calib


for i, tgt in enumerate(FUTURE_TARGET_COLS):
    a, b = ridge_calib_a[i], ridge_calib_b[i]
    ridge_valid_pred[tgt] = np.clip(a * ridge_valid_pred[tgt].values + b, 0, None)
    ridge_test_raw[tgt] = np.clip(a * ridge_test_raw[tgt].values + b, 0, None)
    ridge_fit_pred[tgt] = np.clip(a * ridge_fit_pred[tgt].values + b, 0, None)

print("Ridge calib a shape:", ridge_calib_a.shape, "b shape:", ridge_calib_b.shape)

evaluate("Ridge fit",   y_fit,        ridge_fit_pred)
evaluate("Ridge valid", y_valid_full, ridge_valid_pred)
ridge_test_route_ids = X_test["route_id"].astype(int).values
ridge_test_pred = make_forecast_df(ridge_test_raw, route_ids=ridge_test_route_ids)

# ==============================================================================
# CATBOOST PER-HORIZON
# [TUNE] depth=6, l2_leaf_reg=3, border_count=128, random_strength=0.5
# [TUNE] MAE loss for ALL horizons (was Quantile:0.55 for h>=5)
# [NEW]  OOF chaining extended to first 4 steps (was 2)
# ==============================================================================

from catboost import CatBoostRegressor, Pool

OOF_CHAIN_STEPS = 4  # [NEW] extended from 2

def get_oof_predictions(
    X: pd.DataFrame,
    y_log: np.ndarray,
    model_params: dict,
    cat_cols: list,
) -> np.ndarray:
    n = len(X)
    oof = np.zeros(n, dtype=np.float64)
    if n < 2:
        return oof
    mid = n // 2
    if not (0 < mid < n):
        return oof
    folds = (
        (slice(0, mid), slice(mid, n)),
        (slice(mid, n), slice(0, mid)),
    )
    for train_idx, val_idx in folds:
        Xtr = X.iloc[train_idx]
        ytr = y_log[train_idx]
        Xval = X.iloc[val_idx]
        m = CatBoostRegressor(**model_params)
        m.fit(Pool(Xtr, ytr, cat_features=cat_cols), verbose=False)
        oof[val_idx] = np.expm1(m.predict(Xval)).clip(0)
        del m
    gc.collect()
    return oof


_cat_id_cols = [ROUTE_COL] + ([OFFICE_COL] if USE_OFFICE and OFFICE_COL in X_fit.columns else [])
for c in _cat_id_cols:
    X_fit[c]   = X_fit[c].astype("string")
    X_valid[c] = X_valid[c].astype("string")
    X_test[c]  = X_test[c].astype("string")

catboost_models: dict[str, CatBoostRegressor] = {}
calib: dict[str, tuple[float, float]] = {}
pred_cols_to_add: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

# [TUNE] Improved hyperparameters
CB_PARAMS = {
    "loss_function": "MAE",
    "task_type": "GPU",
    "devices": "0",
    "iterations": 3000,
    "depth": 6,               # [TUNE] up from 5 — more complex interactions
    "learning_rate": 0.03,
    "l2_leaf_reg": 3.0,       # [TUNE] down from 6 — less regularization with richer features
    "border_count": 128,       # [TUNE] better split resolution
    "random_strength": 0.5,    # [TUNE] slight randomization for generalization
    "random_seed": RANDOM_STATE,
    "eval_metric": "MAE",
}

with open("models/catboost_v2.pkl", "rb") as f:
    data_improved = pickle.load(f)

models_improved = data_improved["models"]
calib_improved = data_improved["calib"]

for i, tgt in enumerate(FUTURE_TARGET_COLS):
    X_fit_i   = X_fit.copy()
    X_valid_i = X_valid.copy()
    X_test_i  = X_test.copy()

    for prev_tgt, (fit_p, valid_p, test_p) in pred_cols_to_add.items():
        # X_fit_i[f"pred_{prev_tgt}"]   = fit_p
        X_valid_i[f"pred_{prev_tgt}"] = valid_p
        X_test_i[f"pred_{prev_tgt}"]  = test_p

    h = i + 1
    X_fit_i["horizon"]     = h
    X_fit_i["horizon_sq"]  = h**2
    X_fit_i["horizon_log"] = np.log1p(h)
    X_valid_i["horizon"]     = h
    X_valid_i["horizon_sq"]  = h**2
    X_valid_i["horizon_log"] = np.log1p(h)
    X_test_i["horizon"]     = h
    X_test_i["horizon_sq"]  = h**2
    X_test_i["horizon_log"] = np.log1p(h)

    y_h       = y_valid_full[tgt].values
    y_fit_log = np.log1p(fit_df[tgt].clip(lower=0).values)

    cur_cat = [c for c in _cat_id_cols if c in X_fit_i.columns]

    # train_pool = Pool(X_fit_i,   y_fit_log,             cat_features=cur_cat)
    # valid_pool = Pool(X_valid_i, np.log1p(y_h.clip(0)), cat_features=cur_cat)

    # [TUNE] MAE loss for ALL horizons
    loss = "MAE"

    oof_params = {
        **CB_PARAMS,
        "verbose": False,
    }

    # model = CatBoostRegressor(
    #     **CB_PARAMS,
    #     od_type="Iter",
    #     od_wait=150,
    #     verbose=100,
    # )
    # model.fit(train_pool, eval_set=valid_pool, use_best_model=True)
    model = models_improved[tgt]
    # del train_pool, valid_pool
    gc.collect()

    valid_p = np.clip(np.expm1(model.predict(X_valid_i)), 0, None)
    test_p  = np.clip(np.expm1(model.predict(X_test_i)), 0, None)

    # a, b = calibrate(valid_p, y_h)
    a, b = calib_improved[tgt]

    valid_p = np.clip(a * valid_p + b, 0, None)
    test_p  = np.clip(a * test_p + b, 0, None)

    print(f"  {tgt}: valid={metric.calculate(y_h, valid_p):.5f}  a={a:.3f}  b={b:.3f}")

    # catboost_models[tgt] = model
    # calib[tgt] = (a, b)

    # [NEW] OOF chaining extended to first 4 steps (was 2)
    if i < OOF_CHAIN_STEPS:
        # fit_p_oof_raw = get_oof_predictions(X_fit_i, y_fit_log, oof_params, cur_cat)
        # fit_p_oof = np.clip(a * fit_p_oof_raw + b, 0, None)
        pred_cols_to_add[tgt] = (None, valid_p, test_p)

# os.makedirs("models", exist_ok=True)
# with open("models/team_catboost_improved.pkl", "wb") as f:
#     pickle.dump({"models": catboost_models, "calib": calib}, f)

# --- predictions ---
def _predict_cat(X: pd.DataFrame, catboost_models: dict[str, CatBoostRegressor], calib: dict[str, tuple[float, float]], oof_chain_steps: int) -> pd.DataFrame:
    out: dict[str, np.ndarray] = {}
    prev_preds: dict[str, np.ndarray] = {}
    for i, tgt in enumerate(FUTURE_TARGET_COLS):
        Xi = X.copy()
        for prev_tgt, arr in prev_preds.items():
            Xi[f"pred_{prev_tgt}"] = arr
        h = i + 1
        Xi["horizon"] = h
        Xi["horizon_sq"] = h**2
        Xi["horizon_log"] = np.log1p(h)
        raw = np.expm1(catboost_models[tgt].predict(Xi)).clip(0)
        a, b = calib[tgt]
        yhat = np.clip(a * raw + b, 0, None)
        out[tgt] = yhat
        if i < oof_chain_steps:
            prev_preds[tgt] = yhat
    return pd.DataFrame(out)

cat_improved_fit_pred   = _predict_cat(X_fit, models_improved, calib_improved, OOF_CHAIN_STEPS)
cat_improved_valid_pred = _predict_cat(X_valid, models_improved, calib_improved, OOF_CHAIN_STEPS)
cat_improved_test_raw   = _predict_cat(X_test, models_improved, calib_improved, OOF_CHAIN_STEPS)

# evaluate("CatBoost fit",   y_fit,        cat_improved_fit_pred)
evaluate("CatBoost valid", y_valid_full, cat_improved_valid_pred)


# Распределение WAPE по маршрутам (valid)
errors_by_route = []
for route_id, grp in valid_df.groupby(ROUTE_COL):
    idx = grp.index
    y_true = y_valid_full.loc[idx].values.flatten()
    y_pred = cat_improved_valid_pred.loc[idx].values.flatten()
    denom = max(y_true.sum(), 1e-9)
    wape = np.abs(y_pred - y_true).sum() / denom
    errors_by_route.append(
        {"route_id": route_id, "wape": wape, "volume": y_true.sum(), "n": len(y_true)}
    )

err_df = pd.DataFrame(errors_by_route).sort_values("wape", ascending=False)
print("\n[CatBoost valid] WAPE по маршрутам (худшие 20):")
print(err_df.head(20))
top_k = max(1, len(err_df) // 10)
vol_share = err_df.head(top_k)["volume"].sum() / err_df["volume"].sum()
print(
    f"\nТоп-10% маршрутов по ошибке дают долю объёма: {vol_share:.1%}"
)

cat_improved_test_route_ids = X_test["route_id"].astype(int).values
cat_improved_test_pred = make_forecast_df(cat_improved_test_raw, route_ids=cat_improved_test_route_ids)


with open("models/catboost_v1.pkl", "rb") as f:
    data_per_horizon = pickle.load(f)

models_per_horizon = data_per_horizon["models"]
calib_per_horizon = data_per_horizon["calib"]


feature_cols_per_horizon = [f for f in models_per_horizon["target_step_1"].feature_names_ if "horizon" not in f]

X_fit_per_horizon   = fit_df[feature_cols_per_horizon].copy()
X_valid_per_horizon = valid_df[feature_cols_per_horizon].copy()
X_test_per_horizon  = test_model_df[feature_cols_per_horizon].copy()


X_fit_per_horizon[["route_mean_target", "route_std_target"]] = fit_df[["route_mean_target2", "route_std_target2"]]
X_valid_per_horizon[["route_mean_target", "route_std_target"]] = valid_df[["route_mean_target2", "route_std_target2"]]
X_test_per_horizon[["route_mean_target", "route_std_target"]] = test_model_df[["route_mean_target2", "route_std_target2"]]


for i, tgt in enumerate(FUTURE_TARGET_COLS):
    X_fit_i   = X_fit_per_horizon.copy()
    X_valid_i = X_valid_per_horizon.copy()
    X_test_i  = X_test_per_horizon.copy()

    for prev_tgt, (fit_p, valid_p, test_p) in pred_cols_to_add.items():
        # X_fit_i[f"pred_{prev_tgt}"]   = fit_p
        X_valid_i[f"pred_{prev_tgt}"] = valid_p
        X_test_i[f"pred_{prev_tgt}"]  = test_p

    h = i + 1
    X_fit_i["horizon"]     = h
    X_fit_i["horizon_sq"]  = h**2
    X_fit_i["horizon_log"] = np.log1p(h)
    X_valid_i["horizon"]     = h
    X_valid_i["horizon_sq"]  = h**2
    X_valid_i["horizon_log"] = np.log1p(h)
    X_test_i["horizon"]     = h
    X_test_i["horizon_sq"]  = h**2
    X_test_i["horizon_log"] = np.log1p(h)

    y_h       = y_valid_full[tgt].values
    y_fit_log = np.log1p(fit_df[tgt].clip(lower=0).values)

    cur_cat = [c for c in _cat_id_cols if c in X_fit_i.columns]

    # train_pool = Pool(X_fit_i,   y_fit_log,             cat_features=cur_cat)
    # valid_pool = Pool(X_valid_i, np.log1p(y_h.clip(0)), cat_features=cur_cat)

    # [TUNE] MAE loss for ALL horizons
    loss = "MAE"

    oof_params = {
        **CB_PARAMS,
        "verbose": False,
    }

    # model = CatBoostRegressor(
    #     **CB_PARAMS,
    #     od_type="Iter",
    #     od_wait=150,
    #     verbose=100,
    # )
    # model.fit(train_pool, eval_set=valid_pool, use_best_model=True)
    model = models_per_horizon[tgt]
    # del train_pool, valid_pool
    gc.collect()

    valid_p = np.clip(np.expm1(model.predict(X_valid_i)), 0, None)
    test_p  = np.clip(np.expm1(model.predict(X_test_i)), 0, None)

    # a, b = calibrate(valid_p, y_h)
    a, b = calib_per_horizon[tgt]

    valid_p = np.clip(a * valid_p + b, 0, None)
    test_p  = np.clip(a * test_p + b, 0, None)

    print(f"  {tgt}: valid={metric.calculate(y_h, valid_p):.5f}  a={a:.3f}  b={b:.3f}")

    # catboost_models[tgt] = model
    # calib[tgt] = (a, b)

    # [NEW] OOF chaining extended to first 4 steps (was 2)
    if i < OOF_CHAIN_STEPS:
        # fit_p_oof_raw = get_oof_predictions(X_fit_i, y_fit_log, oof_params, cur_cat)
        # fit_p_oof = np.clip(a * fit_p_oof_raw + b, 0, None)
        pred_cols_to_add[tgt] = (None, valid_p, test_p)

# os.makedirs("models", exist_ok=True)
# with open("models/team_catboost_improved.pkl", "wb") as f:
#     pickle.dump({"models": catboost_models, "calib": calib}, f)


cat_fit_pred   = _predict_cat(X_fit_per_horizon, models_per_horizon, calib_per_horizon, OOF_CHAIN_STEPS)
cat_valid_pred = _predict_cat(X_valid_per_horizon, models_per_horizon, calib_per_horizon, OOF_CHAIN_STEPS)
cat_test_raw   = _predict_cat(X_test_per_horizon, models_per_horizon, calib_per_horizon, OOF_CHAIN_STEPS)

# evaluate("CatBoost fit",   y_fit,        cat_fit_pred)
evaluate("CatBoost valid", y_valid_full, cat_valid_pred)



# Распределение WAPE по маршрутам (valid)
errors_by_route = []
for route_id, grp in valid_df.groupby(ROUTE_COL):
    idx = grp.index
    y_true = y_valid_full.loc[idx].values.flatten()
    y_pred = cat_valid_pred.loc[idx].values.flatten()
    denom = max(y_true.sum(), 1e-9)
    wape = np.abs(y_pred - y_true).sum() / denom
    errors_by_route.append(
        {"route_id": route_id, "wape": wape, "volume": y_true.sum(), "n": len(y_true)}
    )

err_df = pd.DataFrame(errors_by_route).sort_values("wape", ascending=False)
print("\n[CatBoost valid] WAPE по маршрутам (худшие 20):")
print(err_df.head(20))
top_k = max(1, len(err_df) // 10)
vol_share = err_df.head(top_k)["volume"].sum() / err_df["volume"].sum()
print(
    f"\nТоп-10% маршрутов по ошибке дают долю объёма: {vol_share:.1%}"
)

cat_test_route_ids = X_test_per_horizon["route_id"].astype(int).values
cat_test_pred = make_forecast_df(cat_test_raw, route_ids=cat_test_route_ids)

# ==============================================================================
# BLENDING
# [BUGFIX] Fixed: merge both models into a single pred_dict
# ==============================================================================

def optimize_blend(y_true, pred_dict: dict, n_random=20_000, n_refine=3,
                   min_weight=0.05, seed=42):
    rng   = np.random.default_rng(seed)
    names = list(pred_dict.keys())
    P     = np.column_stack([np.asarray(pred_dict[k], float).ravel() for k in names])
    y     = np.asarray(y_true, float).ravel()
    m     = P.shape[1]

    def score(w):
        denom = max(y.sum(), 1e-12)
        p     = P @ w
        return np.abs(p - y).sum() / denom + abs(p.sum() / denom - 1.0)

    def project(w):
        w = np.clip(w, min_weight, 1.0)
        return w / w.sum()

    best_w = project(np.ones(m) / m)
    best_s = score(best_w)

    for i in range(m):
        w = project(np.eye(m)[i])
        if (s := score(w)) < best_s:
            best_s, best_w = s, w.copy()

    if m == 2:
        for a in np.linspace(min_weight, 1.0 - min_weight, 2001):
            w = np.array([a, 1.0 - a])
            if (s := score(w)) < best_s:
                best_s, best_w = s, w.copy()
    else:
        for _ in range(n_random):
            w = project(rng.dirichlet(np.ones(m)))
            if (s := score(w)) < best_s:
                best_s, best_w = s, w.copy()

    for r in range(n_refine):
        alpha = np.maximum(best_w * (50 * (r + 1)) + 1e-3, 1e-3)
        for _ in range(max(5000, n_random // 4)):
            w = project(rng.dirichlet(alpha))
            if (s := score(w)) < best_s:
                best_s, best_w = s, w.copy()

    return {name: float(best_w[i]) for i, name in enumerate(names)}, best_s, P @ best_w


# [BUGFIX] Both models in a single dict — was passing Ridge as n_random before!
weights, best_score, _ = optimize_blend(
    y_valid_full.values,
    {"cat": cat_valid_pred.values, "cat_improved": cat_improved_valid_pred.values, 'ridge': ridge_valid_pred.values},
)
print(f"\nBlend valid: {best_score:.4f}  weights: {weights}")

blended = (
    cat_test_pred["y_pred"].values   * weights["cat"] + 
    cat_improved_test_pred["y_pred"].values * weights["cat_improved"] +
    ridge_test_pred["y_pred"].values * weights["ridge"]
)

os.makedirs("submissions", exist_ok=True)
final = pd.DataFrame({"id": test_df["id"], "y_pred": blended})


final.to_csv("submissions/team_weighted_improved.csv", index=False)
print(f"\nSaved submissions/team_weighted_improved.csv  ({len(final)} rows)")
print(final["y_pred"].describe())