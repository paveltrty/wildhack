"""
Generates synthetic parquet with:
  - DEMO_WAREHOUSES warehouses (default 3), IDs: "wh_01", "wh_02", "wh_03"
  - DEMO_ROUTES_PER_WAREHOUSE routes each (default 5), IDs: "r_{wh}_{n:02d}"
  - DEMO_HISTORY_DAYS days of 30-min timestamps
  - Realistic patterns: daytime peaks (9-12h, 14-17h), weekend dips
  - status_1..8: correlated Poisson(lam=3..15 depending on time)
  - target_2h: rolling 4-step sum of base shipments + N(0, 1) noise, clipped >= 0
Saves to /tmp/demo_train.parquet
"""
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

NUM_WAREHOUSES = int(os.getenv("DEMO_WAREHOUSES", "3"))
ROUTES_PER_WH = int(os.getenv("DEMO_ROUTES_PER_WAREHOUSE", "5"))
HISTORY_DAYS = int(os.getenv("DEMO_HISTORY_DAYS", "7"))
OUTPUT_PATH = "/tmp/demo_train.parquet"


def _time_of_day_multiplier(hour: int) -> float:
    """Peak at 10-11 and 15-16, low at night."""
    if 9 <= hour <= 12:
        return 2.0
    elif 14 <= hour <= 17:
        return 1.8
    elif 7 <= hour <= 19:
        return 1.2
    else:
        return 0.3


def _weekend_multiplier(dow: int) -> float:
    return 0.4 if dow >= 5 else 1.0


def generate() -> str:
    np.random.seed(42)
    rows = []

    end_ts = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_ts = end_ts - timedelta(days=HISTORY_DAYS)

    timestamps = []
    t = start_ts
    while t <= end_ts:
        timestamps.append(t)
        t += timedelta(minutes=30)

    for wh_idx in range(1, NUM_WAREHOUSES + 1):
        warehouse_id = f"wh_{wh_idx:02d}"

        for r_idx in range(1, ROUTES_PER_WH + 1):
            route_id = f"r_{wh_idx:02d}_{r_idx:02d}"
            base_lam = np.random.uniform(3, 8)

            shipments_history = []
            for ts in timestamps:
                hour = ts.hour
                dow = ts.weekday()
                lam = base_lam * _time_of_day_multiplier(hour) * _weekend_multiplier(dow)

                statuses = [float(np.random.poisson(max(1, lam / 3 + i * 0.5))) for i in range(8)]
                velocity = sum(statuses)
                base_ship = max(0.0, np.random.poisson(lam) + np.random.normal(0, 1))
                shipments_history.append(base_ship)

                target_2h = None
                if len(shipments_history) >= 4:
                    target_2h = float(
                        max(0.0, sum(shipments_history[-4:]) + np.random.normal(0, 1))
                    )

                rows.append(
                    {
                        "route_id": route_id,
                        "office_from_id": warehouse_id,
                        "timestamp": ts,
                        "status_1": statuses[0],
                        "status_2": statuses[1],
                        "status_3": statuses[2],
                        "status_4": statuses[3],
                        "status_5": statuses[4],
                        "status_6": statuses[5],
                        "status_7": statuses[6],
                        "status_8": statuses[7],
                        "pipeline_velocity": velocity,
                        "target_2h": target_2h,
                    }
                )

    df = pd.DataFrame(rows)
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"Generated {len(df)} rows → {OUTPUT_PATH}")
    return OUTPUT_PATH


if __name__ == "__main__":
    generate()
