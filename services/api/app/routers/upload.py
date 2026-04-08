"""Upload parquet data into raw_events (bulk insert)."""

import io
import logging
import uuid

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.raw_events import RawEvent
from app.models.route_metadata import RouteMetadata

logger = logging.getLogger(__name__)
router = APIRouter()

BATCH_SIZE = 5000


@router.post("/upload")
async def upload_parquet(file: UploadFile, session: AsyncSession = Depends(get_session)):
    if not file.filename or not file.filename.endswith((".parquet", ".pq")):
        raise HTTPException(status_code=400, detail="File must be a parquet file")

    content = await file.read()
    try:
        df = pd.read_parquet(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid parquet file: {e}")

    required_cols = {"route_id", "office_from_id", "timestamp"}
    status_cols = [f"status_{i}" for i in range(1, 9)]
    missing = required_cols - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {missing}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["route_id"] = df["route_id"].astype(str)
    df["office_from_id"] = df["office_from_id"].astype(str)

    for sc in status_cols:
        if sc not in df.columns:
            df[sc] = 0.0
        else:
            df[sc] = pd.to_numeric(df[sc], errors="coerce").fillna(0.0)

    df["pipeline_velocity"] = df[status_cols].sum(axis=1)

    has_target = "target_2h" in df.columns
    if has_target:
        df["target_2h"] = pd.to_numeric(df["target_2h"], errors="coerce")
    else:
        df["target_2h"] = np.nan

    df["id"] = [uuid.uuid4() for _ in range(len(df))]

    insert_cols = ["id", "route_id", "office_from_id", "timestamp",
                   *status_cols, "pipeline_velocity", "target_2h"]

    rows_inserted = 0
    for start in range(0, len(df), BATCH_SIZE):
        batch = df.iloc[start : start + BATCH_SIZE]
        records = []
        for row in batch.itertuples(index=False):
            t2h = getattr(row, "target_2h", None)
            records.append({
                "id": row.id,
                "route_id": row.route_id,
                "office_from_id": row.office_from_id,
                "timestamp": row.timestamp,
                "status_1": float(row.status_1),
                "status_2": float(row.status_2),
                "status_3": float(row.status_3),
                "status_4": float(row.status_4),
                "status_5": float(row.status_5),
                "status_6": float(row.status_6),
                "status_7": float(row.status_7),
                "status_8": float(row.status_8),
                "pipeline_velocity": float(row.pipeline_velocity),
                "target_2h": float(t2h) if pd.notna(t2h) else None,
            })
        await session.execute(RawEvent.__table__.insert(), records)
        rows_inserted += len(records)
        if rows_inserted % 50000 == 0:
            logger.info("Bulk insert progress: %d / %d", rows_inserted, len(df))

    route_office = df.drop_duplicates(subset=["route_id"])[["route_id", "office_from_id"]]
    for row in route_office.itertuples(index=False):
        existing = await session.get(RouteMetadata, row.route_id)
        if existing is None:
            session.add(RouteMetadata(
                route_id=row.route_id,
                office_from_id=row.office_from_id,
                avg_duration_min=120.0,
            ))

    await session.commit()

    warehouses = df["office_from_id"].unique().tolist()
    routes = df["route_id"].unique().tolist()
    logger.info("Uploaded %d rows, %d warehouses, %d routes", rows_inserted, len(warehouses), len(routes))
    return {
        "rows_inserted": rows_inserted,
        "warehouses": [str(w) for w in warehouses],
        "routes": [str(r) for r in routes],
    }
