import io
import logging
from datetime import timedelta

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.actuals import Actual
from ..models.raw_events import RawEvent
from ..models.route_metadata import RouteMetadata
from ..models.warehouse_config import WarehouseConfig

logger = logging.getLogger(__name__)
router = APIRouter()

REQUIRED_COLUMNS = {
    "route_id",
    "office_from_id",
    "timestamp",
    "status_1",
    "status_2",
    "status_3",
    "status_4",
    "status_5",
    "status_6",
    "status_7",
    "status_8",
}


@router.post("/upload")
async def upload_data(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    if not file.filename or not file.filename.endswith(".parquet"):
        raise HTTPException(status_code=400, detail="Only .parquet files accepted")

    content = await file.read()
    df = pd.read_parquet(io.BytesIO(content))

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing columns: {missing}",
        )

    # IDs are stored as text in Postgres; parquet often has them as ints.
    # Normalize early to avoid asyncpg TypeError: expected str, got int.
    df["route_id"] = df["route_id"].astype(str)
    df["office_from_id"] = df["office_from_id"].astype(str)

    if "pipeline_velocity" not in df.columns:
        status_cols = [f"status_{i}" for i in range(1, 9)]
        df["pipeline_velocity"] = df[status_cols].sum(axis=1)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # Make uploaded data "recent" so scheduler (last 2h window) can build features.
    # Otherwise historical parquet won't produce any forecasts/orders.
    # pandas may already return tz-aware UTC here (depends on version)
    now_utc = pd.Timestamp.utcnow()
    if now_utc.tzinfo is None:
        now_utc = now_utc.tz_localize("UTC")
    max_ts = df["timestamp"].max()
    if pd.notna(max_ts):
        df["timestamp"] = df["timestamp"] + (now_utc - max_ts)

    rows_inserted = 0
    for _, row in df.iterrows():
        try:
            await session.execute(
                text("""
                    INSERT INTO raw_events
                        (route_id, timestamp, office_from_id,
                         status_1, status_2, status_3, status_4,
                         status_5, status_6, status_7, status_8,
                         pipeline_velocity, target_2h)
                    VALUES
                        (:route_id, :timestamp, :office_from_id,
                         :s1, :s2, :s3, :s4, :s5, :s6, :s7, :s8,
                         :pv, :t2h)
                    ON CONFLICT (route_id, timestamp) DO NOTHING
                """),
                {
                    "route_id": row["route_id"],
                    "timestamp": row["timestamp"],
                    "office_from_id": row["office_from_id"],
                    "s1": float(row.get("status_1", 0)),
                    "s2": float(row.get("status_2", 0)),
                    "s3": float(row.get("status_3", 0)),
                    "s4": float(row.get("status_4", 0)),
                    "s5": float(row.get("status_5", 0)),
                    "s6": float(row.get("status_6", 0)),
                    "s7": float(row.get("status_7", 0)),
                    "s8": float(row.get("status_8", 0)),
                    "pv": float(row.get("pipeline_velocity", 0)),
                    "t2h": float(row["target_2h"]) if pd.notna(row.get("target_2h")) else None,
                },
            )
            rows_inserted += 1
        except Exception:
            logger.exception("Error inserting row")

    routes = df[["route_id", "office_from_id"]].drop_duplicates()
    for _, r in routes.iterrows():
        await session.execute(
            text("""
                INSERT INTO route_metadata (route_id, office_from_id, avg_duration_min)
                VALUES (:rid, :oid, 120)
                ON CONFLICT (route_id) DO NOTHING
            """),
            {"rid": r["route_id"], "oid": r["office_from_id"]},
        )

    warehouses = df["office_from_id"].unique().tolist()
    for wid in warehouses:
        await session.execute(
            text("""
                INSERT INTO warehouse_config (warehouse_id)
                VALUES (:wid)
                ON CONFLICT (warehouse_id) DO NOTHING
            """),
            {"wid": wid},
        )

    actuals_inserted = 0
    has_target = "target_2h" in df.columns and df["target_2h"].notna().any()
    if has_target:
        for route_id, group in df.groupby("route_id"):
            group = group.sort_values("timestamp")
            office = group["office_from_id"].iloc[0]

            for i in range(len(group)):
                ts = group.iloc[i]["timestamp"]
                t2h = group.iloc[i].get("target_2h")
                if pd.isna(t2h):
                    continue

                if i > 0:
                    prev_ts = group.iloc[i - 1]["timestamp"]
                    prev_t2h = group.iloc[i - 1].get("target_2h")
                    diff = (ts - prev_ts).total_seconds()
                    if abs(diff - 1800) < 60 and pd.notna(prev_t2h):
                        shipments = max(0.0, float(t2h) - float(prev_t2h))
                    else:
                        logger.warning(
                            "Non-consecutive timestamps for %s, using t2h/4",
                            route_id,
                        )
                        shipments = max(0.0, float(t2h) / 4.0)
                else:
                    shipments = max(0.0, float(t2h) / 4.0)

                window_start = ts - timedelta(minutes=30)
                window_end = ts

                await session.execute(
                    text("""
                        INSERT INTO actuals (id, route_id, office_from_id, window_start, window_end, shipments)
                        VALUES (gen_random_uuid(), :rid, :oid, :ws, :we, :sh)
                        ON CONFLICT (route_id, window_start) DO UPDATE SET shipments = :sh
                    """),
                    {
                        "rid": route_id,
                        "oid": office,
                        "ws": window_start,
                        "we": window_end,
                        "sh": shipments,
                    },
                )
                actuals_inserted += 1

    await session.commit()

    return {
        "rows_inserted": rows_inserted,
        "actuals_inserted": actuals_inserted,
        "warehouses": warehouses,
        "routes": routes["route_id"].tolist(),
    }
