# Transport Dispatch Service

Automatic transport dispatching system for warehouses based on ML-forecasted shipment volumes. The system ingests historical shipment data, runs a multi-model ensemble (CatBoost + Ridge) to forecast volumes across 10 horizons (30-minute intervals), optimizes vehicle dispatch decisions balancing miss-risk and overflow, and presents everything through a modern React dashboard with full fleet management capabilities.

## Architecture

```
Browser ──▶ Nginx :80
              ├── /          ──▶ Frontend (React SPA)
              ├── /api/      ──▶ API Backend (FastAPI :8000)
              ├── /grafana/  ──▶ Grafana :3000
              └── /mlflow/   ──▶ MLflow :5000

API Backend ──▶ PostgreSQL :5432
            ──▶ Redis :6379
            ──▶ Inference Service :8001

APScheduler (inside API) runs forecast cycles every 30 minutes.
Prometheus scrapes /metrics from API and Inference services.
```

## Prerequisites

- Docker >= 24
- Docker Compose v2
- 4 GB RAM minimum

## Quick Start

```bash
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD and SECRET_KEY

make build
make up
make migrate

# Open http://localhost — frontend
# Open http://localhost/grafana — monitoring
# Open http://localhost/mlflow — experiment tracking
```

## Loading Data

Upload a parquet file via the Settings page (drag-and-drop), or via CLI:

```bash
curl -X POST http://localhost/api/upload \
  -F "file=@train.parquet"
```

Required columns: `route_id`, `office_from_id`, `timestamp`, `status_1` through `status_8`.
Optional column: `target_2h` (absent in test/live data).

## Adding Vehicles

```bash
curl -X POST http://localhost/api/vehicles \
  -H "Content-Type: application/json" \
  -d '{"warehouse_id": "42", "vehicle_type": "fura"}'
```

## Business Assumptions

- Forecast horizon: 10 steps x 30 minutes = 5 hours ahead
- Vehicle types: Gazel (10 units capacity) and Fura (40 units capacity)
- Optimizer balances miss penalty (alpha, default 0.7) and overflow penalty (beta, default 0.3)
- Safety factor (default 1.05) applied to vehicle count calculation
- Lead time (default 60 min) — minimum advance notice before departure
- Travel buffer (default 15 min) added to route duration estimates
- Orders require manual operator approval before dispatch

## Configuration Parameters

| Parameter | Default | Description |
|---|---|---|
| `gazel_capacity` | 10.0 | Shipment units per Gazel vehicle |
| `fura_capacity` | 40.0 | Shipment units per Fura vehicle |
| `lead_time_min` | 60 | Minutes of advance notice before departure |
| `safety_factor` | 1.05 | Multiplier on forecasted volume for vehicle planning |
| `alpha` | 0.7 | Miss penalty weight in optimizer scoring |
| `beta` | 0.3 | Overflow penalty weight in optimizer scoring |
| `travel_buffer_min` | 15 | Extra minutes added to route duration estimates |

## API Reference

Interactive API documentation is available at [http://localhost/api/docs](http://localhost/api/docs) (Swagger UI) once the service is running.
