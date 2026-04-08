"""Feature engineering pipeline extracted from train_models.py.

Replicates the full make_features() logic using Polars for the inference service.
"""

import gc

import numpy as np
import pandas as pd
import polars as pl

TARGET_COL = "target_2h"
TIME_COL = "timestamp"
ROUTE_COL = "route_id"
OFFICE_COL = "office_from_id"
USE_OFFICE = True
FORECAST_POINTS = 10

FLOAT = pl.Float32
I8, I16, I32, I64 = pl.Int8, pl.Int16, pl.Int32, pl.Int64

STATUS_COLS = [f"status_{i}" for i in range(1, 9)]
HIGH_CORR_STATUSES = ["status_5", "status_6", "status_7", "status_8"]

LAG_SET = {1, 2, 3, 4, 6, 8, 10, 12, 24, 48, 96, 168, 336}
ROLL_WINDOWS = [3, 6, 12, 24, 48, 96, 168]
EWM_SPANS = [12, 48, 168]
ROLL_STD_WINS = [48, 168]

DROP_COLS = [
    "route_mean_target2", "route_std_target2",
    "target_velocity_30m", "target_velocity_1h",
    "target_velocity_2h", "target_velocity_4h",
    "status_sum_velocity_1h", "status_sum_velocity_2h",
    "status_sum_roll_mean_4", "status_sum_roll_mean_8",
    "status_sum_roll_mean_48",
    "office_roll_mean_48", "office_roll_std_48", "office_roll_mean_8",
]

FUTURE_TARGET_COLS = [f"target_step_{s}" for s in range(1, FORECAST_POINTS + 1)]


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """Replicate the full feature engineering pipeline from train_models.py."""
    lf = pl.from_pandas(df).lazy()

    cast_cols = [pl.col(ROUTE_COL).cast(I32), pl.col(TIME_COL).cast(pl.Datetime)]
    if TARGET_COL in df.columns:
        cast_cols.append(pl.col(TARGET_COL).cast(FLOAT))
    cast_cols.extend(pl.col(c).cast(FLOAT) for c in STATUS_COLS if c in df.columns)
    lf = lf.with_columns(cast_cols)

    if USE_OFFICE and OFFICE_COL in df.columns:
        lf = lf.with_columns(pl.col(OFFICE_COL).cast(I32))

    lf = lf.sort([ROUTE_COL, TIME_COL])

    ts = pl.col(TIME_COL)
    hour = ts.dt.hour().cast(I16)
    minute = ts.dt.minute().cast(I16)
    dow = (ts.dt.weekday() - 1).cast(I16)
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
        (2 * np.pi * dow / 7).sin().cast(FLOAT).alias("dow_sin"),
        (2 * np.pi * dow / 7).cos().cast(FLOAT).alias("dow_cos"),
        (2 * np.pi * month / 12).sin().cast(FLOAT).alias("month_sin"),
        (2 * np.pi * month / 12).cos().cast(FLOAT).alias("month_cos"),
    ])

    lf = lf.with_columns([
        (pl.col(ROUTE_COL) * 48 + pl.col("slot_30m")).cast(I64).alias("route_hour_key"),
        (pl.col(ROUTE_COL) * 7 + pl.col("dow")).cast(I64).alias("route_dow_key"),
    ])

    status_present = [c for c in STATUS_COLS if c in df.columns]
    if status_present:
        cols = [pl.col(c) for c in status_present]
        mean_expr = pl.mean_horizontal(*cols)
        msq_expr = pl.mean_horizontal(*[c * c for c in cols])
        lf = lf.with_columns([
            pl.sum_horizontal(*cols).cast(FLOAT).alias("status_sum"),
            mean_expr.cast(FLOAT).alias("status_mean"),
            (msq_expr - mean_expr ** 2).sqrt().cast(FLOAT).alias("status_std"),
            pl.min_horizontal(*cols).cast(FLOAT).alias("status_min"),
            pl.max_horizontal(*cols).cast(FLOAT).alias("status_max"),
        ])

        log_exprs = []
        for c in status_present:
            log_exprs.append(pl.col(c).log1p().cast(FLOAT).alias(f"{c}_log"))
        lf = lf.with_columns(log_exprs)

        ratio_exprs = []
        for i in range(len(status_present) - 1):
            c1, c2 = status_present[i], status_present[i + 1]
            ratio_exprs.append(
                (pl.col(c2) / (pl.col(c1) + 1.0)).cast(FLOAT).alias(f"{c2}_over_{c1}")
            )
        lf = lf.with_columns(ratio_exprs)

        if len(status_present) >= 4:
            weights = np.linspace(0.5, 2.0, len(status_present))
            weighted_sum = pl.lit(0.0).cast(FLOAT)
            for w, c in zip(weights, status_present):
                weighted_sum = weighted_sum + pl.col(c) * w
            lf = lf.with_columns(weighted_sum.alias("status_weighted_sum"))

    y_col_name = TARGET_COL if TARGET_COL in df.columns else None
    if y_col_name is None:
        result = lf.collect().to_pandas()
        gc.collect()
        return result

    y = pl.col(y_col_name)
    exprs: list[pl.Expr] = []

    for lag in LAG_SET:
        exprs.append(y.shift(lag).over(ROUTE_COL).alias(f"target_lag_{lag}"))

    for w in ROLL_WINDOWS:
        exprs.append(
            y.shift(1).rolling_mean(w).over(ROUTE_COL).alias(f"target_roll_mean_{w}")
        )

    for w in ROLL_STD_WINS:
        exprs.append(
            y.shift(1).rolling_std(w).over(ROUTE_COL).cast(FLOAT).alias(f"target_roll_std_{w}")
        )

    for sp in EWM_SPANS:
        a = 2.0 / (sp + 1)
        exprs.append(
            y.shift(1).ewm_mean(alpha=a, ignore_nulls=True).over(ROUTE_COL)
            .cast(FLOAT).alias(f"target_ewm_{sp}")
        )

    exprs += [
        y.diff(1).over(ROUTE_COL).cast(FLOAT).alias("target_diff_1"),
        y.diff(48).over(ROUTE_COL).cast(FLOAT).alias("target_diff_48"),
        y.diff(168).over(ROUTE_COL).cast(FLOAT).alias("target_diff_168"),
        (y.shift(1) - y.shift(2)).over(ROUTE_COL).cast(FLOAT).alias("target_velocity_30m"),
        (y.shift(1) - y.shift(4)).over(ROUTE_COL).cast(FLOAT).alias("target_velocity_1h"),
        (y.shift(1) - y.shift(8)).over(ROUTE_COL).cast(FLOAT).alias("target_velocity_2h"),
        (y.shift(1) - y.shift(16)).over(ROUTE_COL).cast(FLOAT).alias("target_velocity_4h"),
    ]

    if status_present:
        ss = pl.col("status_sum")
        exprs += [
            (ss.shift(1) - ss.shift(4)).over(ROUTE_COL).cast(FLOAT).alias("status_sum_velocity_1h"),
            (ss.shift(1) - ss.shift(8)).over(ROUTE_COL).cast(FLOAT).alias("status_sum_velocity_2h"),
            ss.shift(1).rolling_mean(4).over(ROUTE_COL).cast(FLOAT).alias("status_sum_roll_mean_4"),
            ss.shift(1).rolling_mean(8).over(ROUTE_COL).cast(FLOAT).alias("status_sum_roll_mean_8"),
            ss.shift(1).rolling_mean(48).over(ROUTE_COL).cast(FLOAT).alias("status_sum_roll_mean_48"),
        ]

    for c in status_present:
        col = pl.col(c)
        is_high_corr = c in HIGH_CORR_STATUSES
        lags = LAG_SET if is_high_corr else LAG_SET
        rolls = ROLL_WINDOWS if is_high_corr else ROLL_WINDOWS
        for lag in lags:
            exprs.append(col.shift(lag).over(ROUTE_COL).alias(f"{c}_lag_{lag}"))
        for w in rolls:
            exprs.append(col.shift(1).rolling_mean(w).over(ROUTE_COL).alias(f"{c}_roll_mean_{w}"))
        exprs.append((col / (pl.col("status_sum") + 1.0)).cast(FLOAT).alias(f"{c}_share"))

    for sc in HIGH_CORR_STATUSES:
        if sc in status_present:
            scol = pl.col(sc)
            for w in ROLL_STD_WINS:
                exprs.append(
                    scol.shift(1).rolling_std(w).over(ROUTE_COL)
                    .cast(FLOAT).alias(f"{sc}_roll_std_{w}")
                )
            for sp in EWM_SPANS:
                a = 2.0 / (sp + 1)
                exprs.append(
                    scol.shift(1).ewm_mean(alpha=a, ignore_nulls=True).over(ROUTE_COL)
                    .cast(FLOAT).alias(f"{sc}_ewm_{sp}")
                )
            exprs.append(scol.diff(1).over(ROUTE_COL).cast(FLOAT).alias(f"{sc}_diff_1"))

    if "status_7" in status_present:
        exprs.append(
            (pl.col("status_7") / (y + 1.0)).cast(FLOAT).alias("status_7_to_target_ratio")
        )

    if status_present:
        exprs.append(
            (y / (pl.col("status_sum") + 1.0)).cast(FLOAT).alias("target_to_status_ratio")
        )
        exprs.append(
            (y / (pl.col("status_sum") + 1.0)).shift(1).over(ROUTE_COL)
            .cast(FLOAT).alias("target_to_status_ratio_lag1")
        )
        exprs.append(
            (y / (pl.col("status_sum") + 1.0)).shift(1).rolling_mean(12).over(ROUTE_COL)
            .cast(FLOAT).alias("target_to_status_ratio_roll12")
        )

    if "status_8" in status_present:
        exprs.append(
            (pl.col("status_8").shift(1).rolling_mean(12).over(ROUTE_COL)
             / (pl.col("status_sum").shift(1).rolling_mean(12).over(ROUTE_COL) + 1.0))
            .cast(FLOAT).alias("status_8_roll_ratio_12")
        )

    lf = lf.with_columns(exprs)

    lf = lf.with_columns([
        (y.shift(1).cum_sum().over(ROUTE_COL)
         / pl.int_range(1, pl.len() + 1).over(ROUTE_COL).cast(FLOAT))
        .cast(FLOAT).alias("route_mean_target"),
        y.shift(1).rolling_std(336).over(ROUTE_COL).cast(FLOAT).alias("route_std_target"),
    ])

    lf = lf.with_columns([
        y.mean().over(ROUTE_COL).cast(FLOAT).alias("route_mean_target2"),
        y.std().over(ROUTE_COL).cast(FLOAT).alias("route_std_target2"),
    ])

    lf = lf.with_columns([
        y.mean().over([ROUTE_COL, "hour"]).cast(FLOAT).alias("route_hour_mean_target"),
        y.mean().over([ROUTE_COL, "dow"]).cast(FLOAT).alias("route_dow_mean_target"),
    ])

    if USE_OFFICE and OFFICE_COL in df.columns:
        lf = lf.with_columns([
            y.mean().over(OFFICE_COL).cast(FLOAT).alias("office_mean_target"),
            y.mean().over([OFFICE_COL, "hour"]).cast(FLOAT).alias("office_hour_mean_target"),
            y.mean().over([OFFICE_COL, "dow"]).cast(FLOAT).alias("office_dow_mean_target"),
            y.shift(1).rolling_mean(48).over(OFFICE_COL).cast(FLOAT).alias("office_roll_mean_48"),
            y.shift(1).rolling_std(48).over(OFFICE_COL).cast(FLOAT).alias("office_roll_std_48"),
            y.shift(1).rolling_mean(8).over(OFFICE_COL).cast(FLOAT).alias("office_roll_mean_8"),
        ])

    lf = lf.with_columns([
        (pl.col("target_roll_mean_48") / (pl.col("route_mean_target") + 0.1))
        .cast(FLOAT).alias("route_recent_ratio"),
    ])

    result = lf.collect().to_pandas()
    gc.collect()
    return result
