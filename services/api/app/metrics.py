from prometheus_client import Counter, Gauge

# Keep metrics in a dedicated module to avoid circular imports.

OPTIMIZER_SCORE = Gauge("optimizer_score_chosen", "Latest optimizer score", ["warehouse_id"])
VEHICLES_AVAILABLE = Gauge("vehicles_available", "Free vehicles count", ["warehouse_id"])
ROUTES_UTILIZED_RATIO = Gauge("routes_utilized_ratio", "Fraction of routes with >=1 assigned vehicle", ["warehouse_id"])

ORDERS_CREATED = Counter("orders_created_total", "Total transport orders created")
MISS_EVENTS = Counter("miss_events_total", "Times actual exceeded capacity")

