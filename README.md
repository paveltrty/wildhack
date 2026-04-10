# Transport Dispatch Service

Automatic transport dispatching system for warehouses based on ML-forecasted shipment volumes.

## Architecture

- **Inference Service** — FastAPI microservice serving CatBoost/Ridge blended predictions across 10 horizons (30-min steps)
- **API Backend** — FastAPI orchestrator with SQLAlchemy async, APScheduler, horizon decomposition, optimizer, and transport planning
- **Frontend** — React 18 SPA with D3 network graph, Recharts analytics, and TanStack Query
- **PostgreSQL 16** — primary storage for events, forecasts, orders, vehicle state
- **Redis 7** — caching scheduler state
- **Nginx** — reverse proxy

## Quick start — production

```bash
git clone <repo> && cd transport-dispatch
cp .env.example .env
# Set POSTGRES_PASSWORD and SECRET_KEY in .env

make build
make up
make migrate
# → http://localhost

# Upload data
curl -X POST http://localhost/api/upload -F "file=@train.parquet"

# Add vehicles
curl -X POST http://localhost/api/vehicles \
  -H "Content-Type: application/json" \
  -d '{"warehouse_id": "wh_01", "vehicle_type": "gazel", "count": 4}'
```

## Quick start — demo (no real data or models needed)

```bash
cp .env.example .env
make build
make demo
# → http://localhost
# The demo runner auto-generates 3 warehouses × 5 routes,
# seeds vehicles, and runs scheduler cycles every 10 seconds.
# The Network graph updates in real time.
```

## Business assumptions

| Assumption | Reason |
|---|---|
| Vehicles return to their origin warehouse | Simplifies pool tracking; cross-depot transfers in v2 |
| All vehicles of same type have equal capacity | Operator sets capacity per type; per-vehicle config in v2 |
| `avg_route_duration` is constant | MVP; v2 adds time-of-day traffic multiplier |
| Vehicles assigned to warehouse pool, not a specific route | Any free vehicle serves any route from that warehouse |
| Decomposed `y_hat_future` clipped to 0 if negative | Model noise; negative demand is physically impossible |
| Miss penalized more than overflow (`alpha > beta`) | Missed delivery costs more than idle truck; configurable |
| Orders require manual approval | Safety; auto-dispatch opt-in in v2 |
| One draft order per route per 15-min window | Avoids duplicate orders from repeated scheduler runs |

## Configuration reference

| Parameter | Default | Description |
|---|---|---|
| `gazel_capacity` | 10.0 | Shipment units per gazel trip |
| `fura_capacity` | 40.0 | Shipment units per fura trip |
| `lead_time_min` | 60 | Submit order N minutes before departure |
| `safety_factor` | 1.05 | Multiply forecast when sizing vehicles |
| `alpha` | 0.7 | Weight of miss penalty in score |
| `beta` | 0.3 | Weight of overflow penalty in score |
| `travel_buffer_min` | 15 | Subtract from departure time for vehicle travel |
| `avg_route_duration_min` | 120 | Default round-trip time for new routes |

## Makefile commands

| Command | Description |
|---|---|
| `make build` | Build all containers |
| `make up` | Start services in background |
| `make down` | Stop and remove volumes |
| `make migrate` | Run Alembic migrations |
| `make demo` | Start with demo runner (foreground) |
| `make demo-d` | Start with demo runner (background) |
| `make logs` | Follow container logs |
| `make ps` | Show container status |
| `make trigger-cycle` | Manually trigger forecast cycle |
| `make shell-api` | Shell into API container |
| `make shell-db` | PostgreSQL shell |

## Core math: Horizon decomposition

The model predicts `target_2h` (total shipments in a rolling 2-hour window). We decompose these overlapping windows into future 30-minute increments:

```
f5       = t1 - f2 - f3 - f4
f(4 + k) = t(k) - t(k-1) + f(k)    for k = 2..10
```

Where `f1..f4` are historical 30-min actuals and `f5..f14` are future increments driving dispatch decisions.

## API endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/upload` | Upload parquet data |
| GET | `/network` | D3 graph data |
| GET | `/forecasts` | Route forecasts |
| GET/POST | `/vehicles` | Vehicle management |
| POST | `/vehicles/{id}/return` | Return vehicle |
| GET | `/orders` | List orders |
| POST | `/orders/{id}/approve` | Approve draft order |
| POST | `/orders/{id}/complete` | Complete with actuals |
| GET | `/analytics/metrics` | Business metrics |
| GET | `/analytics/score-profile` | Optimizer decisions |
| GET/PUT | `/config/{warehouse_id}` | Warehouse config |
| POST | `/internal/trigger-cycle` | Manual cycle trigger |
| GET | `/health` | Health check |
