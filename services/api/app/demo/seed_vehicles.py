"""
For each warehouse discovered in the database:
  POST /vehicles {"warehouse_id": wid, "vehicle_type": "gazel", "count": DEMO_VEHICLES_GAZEL}
  POST /vehicles {"warehouse_id": wid, "vehicle_type": "fura",  "count": DEMO_VEHICLES_FURA}
"""
import os

import httpx

API_BASE = os.getenv("API_BASE", "http://api:8000")
DEMO_VEHICLES_GAZEL = int(os.getenv("DEMO_VEHICLES_GAZEL", "4"))
DEMO_VEHICLES_FURA = int(os.getenv("DEMO_VEHICLES_FURA", "2"))


async def seed(warehouse_ids: list[str]) -> None:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
        for wid in warehouse_ids:
            for vtype, count in [
                ("gazel", DEMO_VEHICLES_GAZEL),
                ("fura", DEMO_VEHICLES_FURA),
            ]:
                resp = await client.post(
                    "/vehicles",
                    json={
                        "warehouse_id": wid,
                        "vehicle_type": vtype,
                        "count": count,
                    },
                )
                resp.raise_for_status()
                print(f"  Seeded {count} {vtype} at {wid}")
