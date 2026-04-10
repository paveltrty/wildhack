"""
Entry point for docker-compose.demo.yml.
1. Wait for API healthy (poll /health every 5s, timeout 120s)
2. generate_data.py → upload via POST /upload
3. seed_vehicles.py
4. Loop every DEMO_CYCLE_INTERVAL_SEC:
   a. POST /internal/trigger-cycle
   b. Simulate returns: randomly pick 1-2 busy vehicles and POST /vehicles/{id}/return
   c. Print summary to stdout
"""
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timezone

import httpx

from .generate_data import generate

API_BASE = os.getenv("API_BASE", "http://api:8000")
CYCLE_INTERVAL = int(os.getenv("DEMO_CYCLE_INTERVAL_SEC", "10"))


async def wait_for_api() -> None:
    print("Waiting for API to be healthy...")
    for attempt in range(24):
        try:
            async with httpx.AsyncClient(base_url=API_BASE, timeout=5.0) as client:
                resp = await client.get("/health")
                if resp.status_code == 200:
                    print(f"API healthy after {(attempt + 1) * 5}s")
                    return
        except Exception:
            pass
        await asyncio.sleep(5)
    print("ERROR: API not healthy after 120s", file=sys.stderr)
    sys.exit(1)


async def upload_data(parquet_path: str) -> dict:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=120.0) as client:
        with open(parquet_path, "rb") as f:
            resp = await client.post(
                "/upload",
                files={"file": ("demo_train.parquet", f, "application/octet-stream")},
            )
            resp.raise_for_status()
            return resp.json()


async def get_busy_vehicles() -> list[dict]:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
        resp = await client.get("/vehicles")
        resp.raise_for_status()
        return [v for v in resp.json() if v["status"] == "busy"]


async def return_vehicle(vehicle_id: str) -> None:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
        resp = await client.post(f"/vehicles/{vehicle_id}/return")
        resp.raise_for_status()


async def trigger_cycle() -> dict:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=60.0) as client:
        resp = await client.post("/internal/trigger-cycle")
        resp.raise_for_status()
        return resp.json()


async def get_network() -> dict:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
        resp = await client.get("/network")
        resp.raise_for_status()
        return resp.json()


async def main() -> None:
    await wait_for_api()

    print("\n=== Generating demo data ===")
    parquet_path = generate()

    print("\n=== Uploading data ===")
    upload_result = await upload_data(parquet_path)
    warehouses = upload_result.get("warehouses", [])
    print(f"  Uploaded: {upload_result['rows_inserted']} rows, "
          f"{upload_result['actuals_inserted']} actuals, "
          f"warehouses: {warehouses}")

    print("\n=== Seeding vehicles ===")
    from .seed_vehicles import seed
    await seed(warehouses)

    print("\n=== Starting demo cycle loop ===")
    cycle_num = 0
    while True:
        cycle_num += 1
        now = datetime.now(timezone.utc)
        print(f"\n=== Cycle {cycle_num} at {now.isoformat()} ===")

        try:
            summary = await trigger_cycle()
            wh_data = summary.get("warehouses", {})

            network = await get_network()
            wh_nodes = [n for n in network.get("nodes", []) if n["type"] == "warehouse"]
            route_nodes = [n for n in network.get("nodes", []) if n["type"] == "route"]

            for wh_node in wh_nodes:
                wid = wh_node["id"]
                free_g = wh_node["free_gazel"]
                busy_g = wh_node["busy_gazel"]
                free_f = wh_node["free_fura"]
                busy_f = wh_node["busy_fura"]

                wh_routes = [r for r in route_nodes if r.get("office_from_id") == wid]
                wh_info = wh_data.get(wid, {})
                new_orders = wh_info.get("orders_created", 0)

                print(
                    f"  {wid}: gazel {free_g} free / {busy_g} busy | "
                    f"fura {free_f} free / {busy_f} busy | "
                    f"Routes: {len(wh_routes)} | New orders: {new_orders}"
                )

            busy = await get_busy_vehicles()
            if busy:
                to_return = random.sample(busy, min(random.randint(1, 2), len(busy)))
                for v in to_return:
                    await return_vehicle(v["id"])
                    print(f"  ↩ Returned vehicle {v['id'][:8]}... ({v['vehicle_type']})")

        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)

        await asyncio.sleep(CYCLE_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
