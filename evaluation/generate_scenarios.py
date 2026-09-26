"""Generate the incident benchmark.

Builds a healthy simulated system, injects one fault per case (plus optional
red-herring signals), and writes:

  scenarios/case_XXX.json   observable data only (what the MCP server serves)
  evaluation/labels.json    ground truth, dev/eval split and key evidence

The two outputs are deliberately separate files so that the agent and tool
layer can never read the answer.

Usage:  python -m evaluation.generate_scenarios
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = ROOT / "scenarios"
LABELS_PATH = ROOT / "evaluation" / "labels.json"

SEED = 7
DATE = "2026-09-25"
TIMES = [f"14:{m:02d}" for m in range(10)]
N = len(TIMES)


# ---------------------------------------------------------------------------
# Time-series helpers
# ---------------------------------------------------------------------------

class Series:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def _jitter(self, value: float, noise: float) -> float:
        return value * (1 + self.rng.uniform(-noise, noise))

    def flat(self, base: float, noise: float = 0.03) -> list[float]:
        return [self._jitter(base, noise) for _ in range(N)]

    def step(self, base: float, peak: float, onset: int, noise: float = 0.03) -> list[float]:
        return [self._jitter(base if i < onset else peak, noise) for i in range(N)]

    def ramp(self, base: float, peak: float, onset: int, noise: float = 0.02) -> list[float]:
        """Flat until onset, then linear growth to peak at the last point."""
        out = []
        for i in range(N):
            if i < onset:
                v = base
            else:
                v = base + (peak - base) * (i - onset + 1) / (N - onset)
            out.append(self._jitter(v, noise))
        return out

    def grow(self, start: float, end: float, noise: float = 0.01) -> list[float]:
        return [self._jitter(start + (end - start) * i / (N - 1), noise) for i in range(N)]


def _round(series: list[float | None], unit: str) -> list[float | int | None]:
    out = []
    for v in series:
        if v is None:
            out.append(None)
        elif unit in ("ms", "MB", "count", "rps", "ops/s", "per_min"):
            out.append(int(round(v)))
        else:
            out.append(round(v, 1))
    return out


# ---------------------------------------------------------------------------
# Healthy world
# ---------------------------------------------------------------------------

METRIC_UNITS = {
    "latency_p95_ms": "ms",
    "error_rate_pct": "%",
    "rps": "rps",
    "cpu_pct": "%",
    "memory_mb": "MB",
    "db_pool_utilization_pct": "%",
    "cache_hit_rate_pct": "%",
    "instances_up": "count",
    "restarts": "count",
    "query_latency_p95_ms": "ms",
    "active_connections": "count",
    "slow_queries_per_min": "per_min",
    "ops_per_sec": "ops/s",
    "evictions_per_min": "per_min",
    "rejected_requests_pct": "%",
}


def healthy_world(s: Series) -> dict:
    def svc(depends_on, metrics, env, trace=None, kind="service"):
        return {
            "kind": kind,
            "depends_on": depends_on,
            "metrics": metrics,
            "logs": [],
            "trace": trace,
            "config": {"env": env, "deploys": []},
        }

    w = {
        "api-gateway": svc(
            ["checkout", "inventory"],
            {
                "latency_p95_ms": s.flat(210), "error_rate_pct": s.flat(0.2, 0.2),
                "rps": s.flat(120), "cpu_pct": s.flat(22), "memory_mb": s.flat(310, 0.01),
                "rejected_requests_pct": s.flat(0.1, 0.2), "instances_up": [3] * N,
            },
            {"CHECKOUT_UPSTREAM": "http://checkout:8080", "INVENTORY_UPSTREAM": "http://inventory:8080",
             "RATE_LIMIT_RPS_PER_CLIENT": "500", "JWT_ISSUER": "https://id.shop.example"},
            {"endpoint": "POST /api/checkout", "spans": [
                {"name": "route_match", "service": "api-gateway", "ms": 1},
                {"name": "auth.verify_jwt", "service": "api-gateway", "ms": 4},
                {"name": "proxy -> checkout", "service": "checkout", "ms": 182},
            ]},
        ),
        "checkout": svc(
            ["payment", "inventory", "orders-db", "redis"],
            {
                "latency_p95_ms": s.flat(180), "error_rate_pct": s.flat(0.3, 0.2),
                "rps": s.flat(40), "cpu_pct": s.flat(30), "memory_mb": s.flat(420, 0.01),
                "db_pool_utilization_pct": s.flat(35), "cache_hit_rate_pct": s.flat(94, 0.01),
                "instances_up": [3] * N, "restarts": [0] * N,
            },
            {"DB_POOL_SIZE": "20", "DB_URL": "postgres://orders-db:5432/orders", "REDIS_URL": "redis://redis:6379",
             "PAYMENT_URL": "http://payment:8080", "INVENTORY_URL": "http://inventory:8080",
             "PAYMENT_TIMEOUT_MS": "3000", "ORDER_EVENTS_TOPIC": "orders.created.v1", "MEMORY_LIMIT_MB": "2048"},
            {"endpoint": "POST /checkout", "spans": [
                {"name": "validate_cart", "service": "checkout", "ms": 8},
                {"name": "cache.get pricing", "service": "redis", "ms": 1},
                {"name": "inventory.reserve", "service": "inventory", "ms": 45},
                {"name": "db.acquire_connection", "service": "checkout", "ms": 1},
                {"name": "db.query select_recent_orders", "service": "orders-db", "ms": 9},
                {"name": "db.query insert_order", "service": "orders-db", "ms": 7},
                {"name": "publish order_created", "service": "checkout", "ms": 3},
                {"name": "payment.charge", "service": "payment", "ms": 110},
            ]},
        ),
        "inventory": svc(
            ["orders-db", "supplier-api (external)"],
            {
                "latency_p95_ms": s.flat(60), "error_rate_pct": s.flat(0.1, 0.2),
                "rps": s.flat(70), "cpu_pct": s.flat(18), "memory_mb": s.flat(380, 0.01),
                "db_pool_utilization_pct": s.flat(25), "instances_up": [3] * N, "restarts": [0] * N,
            },
            {"DB_POOL_SIZE": "15", "DB_URL": "postgres://orders-db:5432/orders",
             "SUPPLIER_API_URL": "https://supplier.example/api", "MEMORY_LIMIT_MB": "2048",
             "SUPPLIER_CLIENT_CERT": "/etc/certs/supplier-client.pem (not_after 2027-03-01T00:00:00Z)"},
            {"endpoint": "POST /inventory/reserve", "spans": [
                {"name": "parse_request", "service": "inventory", "ms": 2},
                {"name": "normalize_sku", "service": "inventory", "ms": 3},
                {"name": "supplier.check_availability", "service": "supplier-api (external)", "ms": 18},
                {"name": "db.acquire_connection", "service": "inventory", "ms": 1},
                {"name": "db.query select_stock", "service": "orders-db", "ms": 6},
                {"name": "db.query update_reservation", "service": "orders-db", "ms": 5},
            ]},
        ),
        "payment": svc(
            ["payprovider-api (external)"],
            {
                "latency_p95_ms": s.flat(240), "error_rate_pct": s.flat(0.2, 0.2),
                "rps": s.flat(38), "cpu_pct": s.flat(15), "memory_mb": s.flat(350, 0.01),
                "instances_up": [3] * N, "restarts": [0] * N,
            },
            {"PAYMENT_PROVIDER_URL": "https://api.payprovider.example/v1",
             "PAYMENT_PROVIDER_TOKEN": "****a91f (expires_at 2026-12-24T00:00:00Z)",
             "MERCHANT_ID": "shop-prod-01"},
            {"endpoint": "POST /charge", "spans": [
                {"name": "load_merchant_config", "service": "payment", "ms": 3},
                {"name": "provider.create_charge", "service": "payprovider-api (external)", "ms": 220},
            ]},
        ),
        "orders-db": svc(
            [],
            {
                "cpu_pct": s.flat(25), "query_latency_p95_ms": s.flat(12),
                "active_connections": s.flat(40), "slow_queries_per_min": [0] * N,
            },
            {"engine": "PostgreSQL 16", "max_connections": "200"},
            kind="datastore",
        ),
        "redis": svc(
            [],
            {"cpu_pct": s.flat(8), "memory_mb": s.flat(900, 0.01), "ops_per_sec": s.flat(5200),
             "evictions_per_min": [0] * N},
            {"maxmemory": "2gb", "maxmemory-policy": "allkeys-lru"},
            kind="datastore",
        ),
    }
    # Benign baseline logs so that "search everything" is never trivially empty.
    for name, svc_ in w.items():
        svc_["logs"].append({"time": "14:00", "level": "INFO", "message": "health check ok", "count": 120})
        if svc_["kind"] == "service":
            svc_["config"]["deploys"].append(
                {"version": "baseline", "time": f"{DATE[:8]}21 10:12", "change": "Routine dependency updates", "diff": {}}
            )
    return w


# ---------------------------------------------------------------------------
# World mutation helpers
# ---------------------------------------------------------------------------

def setm(w, svc, metric, series):
    w[svc]["metrics"][metric] = series


def log(w, svc, time, level, message, count):
    w[svc]["logs"].append({"time": time, "level": level, "message": message, "count": count})


def span(w, svc, name, ms=None, status=None, error=None):
    for sp in w[svc]["trace"]["spans"]:
        if sp["name"] == name:
            if ms is not None:
                sp["ms"] = ms
            if status:
                sp["status"] = status
            if error:
                sp["error"] = error
            return sp
    raise KeyError(f"{svc} has no span {name}")


def add_span(w, svc, name, service, ms, index=None, **extra):
    sp = {"name": name, "service": service, "ms": ms, **extra}
    spans = w[svc]["trace"]["spans"]
    spans.insert(len(spans) if index is None else index, sp)


def set_self_time(w, svc, ms):
    w[svc]["trace"]["self_time_ms"] = ms


def deploy(w, svc, version, time, change, diff):
    w[svc]["config"]["deploys"].append({"version": version, "time": f"{DATE} {time}", "change": change, "diff": diff})


def propagate(w, s: Series, svc, onset, latency_peak=None, error_peak=None):
    """Push symptoms of `svc` up to its callers (checkout <- inventory/payment, gateway <- checkout)."""
    callers = {"payment": ["checkout"], "inventory": ["checkout"], "checkout": ["api-gateway"]}
    for caller in callers.get(svc, []):
        base_lat = w[caller]["metrics"]["latency_p95_ms"][0]
        base_err = w[caller]["metrics"]["error_rate_pct"][0]
        if latency_peak is not None:
            setm(w, caller, "latency_p95_ms", s.step(base_lat, max(base_lat, latency_peak + base_lat * 0.3), onset))
        if error_peak is not None:
            setm(w, caller, "error_rate_pct", s.step(base_err, error_peak, onset))
        if caller == "checkout":
            propagate(w, s, "checkout", onset, latency_peak, error_peak * 0.9 if error_peak else None)


# ---------------------------------------------------------------------------
# Faults
# ---------------------------------------------------------------------------

def fault_db_pool_exhaustion(w, s, onset, svc="checkout", cause="traffic_spike"):
    pool = w[svc]["config"]["env"]["DB_POOL_SIZE"]
    if cause == "connection_leak":
        setm(w, svc, "db_pool_utilization_pct", [min(100, v) for v in s.ramp(35, 100, max(1, onset - 4), 0)])
        log(w, svc, TIMES[max(0, onset - 3)], "WARN",
            f"Connection leak detection triggered for conn-{17 if svc == 'checkout' else 9}, "
            "stack: OrderRepository.findPending, held for 61000ms", 23)
    else:
        setm(w, svc, "db_pool_utilization_pct", [min(100, v) for v in s.step(35, 100, onset, 0)])
        base_rps = w[svc]["metrics"]["rps"][0]
        setm(w, svc, "rps", s.step(base_rps, base_rps * 2.1, onset - 1))
        setm(w, "api-gateway", "rps", s.step(120, 205, onset - 1))
    base_lat = w[svc]["metrics"]["latency_p95_ms"][0]
    setm(w, svc, "latency_p95_ms", s.step(base_lat, 3300, onset))
    setm(w, svc, "error_rate_pct", s.step(0.3, 8.5, onset))
    log(w, svc, TIMES[onset], "ERROR",
        f"HikariPool-1 - Connection is not available, request timed out after 3000ms "
        f"(total={pool}, active={pool}, idle=0, waiting=57)", 640)
    span(w, svc, "db.acquire_connection", 3000, "error", "Connection is not available, request timed out after 3000ms")
    if svc == "inventory":
        span(w, "checkout", "inventory.reserve", 3060, "error", "HTTP 503 from inventory")
        log(w, "checkout", TIMES[onset], "ERROR", "inventory.reserve failed: HTTP 503 Service Unavailable from inventory", 590)
    else:
        span(w, "api-gateway", "proxy -> checkout", 3290, "error", "HTTP 500 from checkout")
    propagate(w, s, svc, onset, 3300, 7.5)


def fault_slow_db_query(w, s, onset, svc="checkout", confounded=False):
    setm(w, "orders-db", "cpu_pct", s.step(25, 93, onset))
    setm(w, "orders-db", "query_latency_p95_ms", s.step(12, 2700, onset))
    setm(w, "orders-db", "slow_queries_per_min", s.step(0.01, 140, onset, 0.05))
    setm(w, "orders-db", "active_connections", s.step(40, 78, onset))
    if svc == "checkout":
        stmt = "SELECT * FROM orders WHERE customer_email = $1 AND created_at > now() - interval '30 days'"
        table, rows, span_name = "orders", "4210334", "db.query select_recent_orders"
    else:
        stmt = "SELECT qty FROM stock WHERE lower(sku) = lower($1) FOR UPDATE"
        table, rows, span_name = "stock", "2873110", "db.query select_stock"
    log(w, "orders-db", TIMES[onset], "WARN", f"duration: 2843.117 ms  statement: {stmt}", 1350)
    log(w, "orders-db", TIMES[onset], "INFO",
        f"auto_explain: Seq Scan on {table} (cost=0.00..418232.10 rows={rows}) Filter removed {rows} rows", 1350)
    base_lat = w[svc]["metrics"]["latency_p95_ms"][0]
    setm(w, svc, "latency_p95_ms", s.step(base_lat, 3100, onset))
    setm(w, svc, "error_rate_pct", s.step(0.3, 6.0 if confounded else 3.2, onset))
    setm(w, svc, "db_pool_utilization_pct", [min(100, v) for v in s.step(35, 100 if confounded else 71, onset, 0.02)])
    log(w, svc, TIMES[onset], "WARN", f"slow query: {span_name.split()[-1]} took 2811ms", 900)
    if confounded:
        pool = w[svc]["config"]["env"]["DB_POOL_SIZE"]
        log(w, svc, TIMES[onset + 1], "ERROR",
            f"HikariPool-1 - Connection is not available, request timed out after 3000ms "
            f"(total={pool}, active={pool}, idle=0, waiting=12)", 110)
    span(w, svc, "db.acquire_connection", 240 if confounded else 3)
    span(w, svc, span_name, 2830, "slow")
    if svc == "inventory":
        span(w, "checkout", "inventory.reserve", 2900, "slow")
    propagate(w, s, svc, onset, 3100, 4.0)


def fault_missing_env_var(w, s, onset, svc="payment"):
    if svc == "payment":
        var, route = "PAYMENT_PROVIDER_URL", "POST /charge"
    else:
        var, route = "ORDER_EVENTS_TOPIC", "POST /checkout"
    w[svc]["config"]["env"].pop(var)
    deploy(w, svc, "v2.4.0" if svc == "payment" else "v5.0.0", TIMES[onset - 1],
           "Migrate configuration to new settings loader (app/config/settings.py)", {"settings_loader": "env -> settings.py"})
    log(w, svc, TIMES[onset], "ERROR",
        f"Unhandled exception on {route}: KeyError: '{var}' (app/config/settings.py:41 in require_env)", 700)
    setm(w, svc, "error_rate_pct", s.step(0.2, 97 if svc == "payment" else 88, onset))
    if svc == "payment":
        setm(w, svc, "latency_p95_ms", s.step(240, 14, onset))
        span(w, "payment", "load_merchant_config", 2, "error", f"KeyError: '{var}'")
        span(w, "payment", "provider.create_charge", 0, "skipped")
        span(w, "checkout", "payment.charge", 16, "error", "HTTP 500 Internal Server Error from payment")
        log(w, "checkout", TIMES[onset], "ERROR", "payment.charge failed: HTTP 500 Internal Server Error from payment", 690)
        setm(w, "checkout", "error_rate_pct", s.step(0.3, 46, onset))
        propagate(w, s, "checkout", onset, None, 40)
    else:
        span(w, "checkout", "publish order_created", 1, "error", f"KeyError: '{var}'")
        propagate(w, s, "checkout", onset, None, 80)


def fault_dependency_unavailable(w, s, onset, dep="payment"):
    op = {"payment": "payment.charge", "inventory": "inventory.reserve"}[dep]
    setm(w, dep, "instances_up", [3 if i < onset else 0 for i in range(N)])
    for m in ("rps", "cpu_pct", "memory_mb", "latency_p95_ms", "error_rate_pct", "db_pool_utilization_pct"):
        if m in w[dep]["metrics"]:
            setm(w, dep, m, [v if i < onset else None for i, v in enumerate(w[dep]["metrics"][m])])
    log(w, dep, TIMES[onset], "INFO", "Received SIGTERM, starting graceful shutdown", 3)
    log(w, dep, TIMES[onset], "WARN", "Readiness probe failed: dial tcp :8080: connect: connection refused", 18)
    w[dep]["trace"] = None
    log(w, "checkout", TIMES[onset], "ERROR", f"{op} failed: connect ECONNREFUSED {dep}:8080 (attempt 3/3)", 720)
    log(w, "checkout", TIMES[onset], "WARN", f"circuit breaker '{dep}' state CLOSED -> OPEN", 4)
    span(w, "checkout", op, 910, "error", f"connect ECONNREFUSED {dep}:8080 after 3 retries")
    setm(w, "checkout", "error_rate_pct", s.step(0.3, 52, onset))
    setm(w, "checkout", "latency_p95_ms", s.step(180, 950, onset))
    propagate(w, s, "checkout", onset, 950, 47)


def fault_memory_leak(w, s, onset, svc="checkout", recent_deploy=False):
    limit = 2048
    setm(w, svc, "memory_mb", s.grow(w[svc]["metrics"]["memory_mb"][0] * 2.4, limit * 0.97))
    setm(w, svc, "restarts", [0] * (N - 2) + [1, 2])
    setm(w, svc, "cpu_pct", s.ramp(w[svc]["metrics"]["cpu_pct"][0], 58, onset))
    base_lat = w[svc]["metrics"]["latency_p95_ms"][0]
    setm(w, svc, "latency_p95_ms", s.ramp(base_lat, 1450, onset))
    setm(w, svc, "error_rate_pct", s.ramp(0.3, 5.5, onset))
    log(w, svc, TIMES[onset], "WARN", "Full GC pause 870ms, heap 1.9GiB/2.0GiB after collection", 64)
    log(w, svc, TIMES[N - 2], "ERROR", f"Container {svc}-7d9f-2 terminated: OOMKilled (memory limit {limit}Mi)", 2)
    set_self_time(w, svc, 1180)
    if recent_deploy:
        deploy(w, svc, "v1.9.0" if svc == "inventory" else "v5.1.0", "08:02",
               "Add in-process LRU cache for product detail responses", {})
    if svc == "inventory":
        span(w, "checkout", "inventory.reserve", 1260, "slow")
    propagate(w, s, svc, onset, 1450, 4.5)


def fault_cpu_hot_loop(w, s, onset, svc="inventory"):
    setm(w, svc, "cpu_pct", s.step(w[svc]["metrics"]["cpu_pct"][0], 99, onset, 0.01))
    base_lat = w[svc]["metrics"]["latency_p95_ms"][0]
    setm(w, svc, "latency_p95_ms", s.step(base_lat, 2600, onset))
    setm(w, svc, "error_rate_pct", s.step(0.2, 4.0, onset))
    if svc == "inventory":
        log(w, svc, TIMES[onset - 1], "INFO", "Imported 18,240 SKUs from supplier feed 'acme-weekly'", 1)
        log(w, svc, TIMES[onset], "WARN", "Slow handler: normalize_sku() took 2412ms (sku='ACME-XL-00-...-R')", 810)
        span(w, svc, "normalize_sku", 2410, "slow")
        span(w, "checkout", "inventory.reserve", 2480, "slow")
        propagate(w, s, svc, onset, 2600, 3.5)
    else:
        log(w, svc, TIMES[onset - 1], "INFO", "JWKS refreshed from identity provider: 4096 keys", 1)
        log(w, svc, TIMES[onset], "WARN", "auth.verify_jwt took 1930ms (tried 4096 candidate keys)", 1500)
        span(w, svc, "auth.verify_jwt", 1930, "slow")


def fault_expired_credential(w, s, onset, svc="payment"):
    if svc == "payment":
        w[svc]["config"]["env"]["PAYMENT_PROVIDER_TOKEN"] = f"****a91f (expires_at {DATE}T14:03:00Z)"
        log(w, svc, TIMES[onset], "ERROR",
            'provider.create_charge failed: POST https://api.payprovider.example/v1/charges -> 401 Unauthorized '
            '{"error":"invalid_token","error_description":"The access token expired"}', 650)
        setm(w, svc, "error_rate_pct", s.step(0.2, 94, onset))
        setm(w, svc, "latency_p95_ms", s.step(240, 90, onset))
        span(w, svc, "provider.create_charge", 70, "error", "401 Unauthorized")
        span(w, "checkout", "payment.charge", 95, "error", "HTTP 502 from payment")
        log(w, "checkout", TIMES[onset], "ERROR", "payment.charge failed: HTTP 502 Bad Gateway from payment: upstream provider error", 640)
        setm(w, "checkout", "error_rate_pct", s.step(0.3, 44, onset))
        propagate(w, s, "checkout", onset, None, 40)
    else:
        w[svc]["config"]["env"]["SUPPLIER_CLIENT_CERT"] = f"/etc/certs/supplier-client.pem (not_after {DATE}T13:59:59Z)"
        log(w, svc, TIMES[onset], "ERROR",
            "supplier.check_availability failed: TLS handshake failed: remote error: tls: expired certificate", 780)
        setm(w, svc, "error_rate_pct", s.step(0.1, 71, onset))
        span(w, svc, "supplier.check_availability", 9, "error", "tls: expired certificate")
        span(w, "checkout", "inventory.reserve", 30, "error", "HTTP 502 from inventory")
        log(w, "checkout", TIMES[onset], "ERROR", "inventory.reserve failed: HTTP 502 Bad Gateway from inventory", 560)
        propagate(w, s, svc, onset, None, 60)


def fault_bad_config_deploy(w, s, onset, variant="timeout"):
    if variant == "timeout":
        w["checkout"]["config"]["env"]["PAYMENT_TIMEOUT_MS"] = "50"
        deploy(w, "checkout", "v5.2.0", TIMES[onset - 1], "Tune outbound HTTP timeouts",
               {"PAYMENT_TIMEOUT_MS": "3000 -> 50", "INVENTORY_TIMEOUT_MS": "2000 -> 1500"})
        log(w, "checkout", TIMES[onset], "ERROR", "payment.charge failed: request timed out after 50ms", 810)
        log(w, "payment", TIMES[onset], "WARN", "client closed request before response was sent (499)", 780)
        span(w, "checkout", "payment.charge", 50, "error", "timeout after 50ms")
        setm(w, "checkout", "error_rate_pct", s.step(0.3, 71, onset))
        setm(w, "checkout", "latency_p95_ms", s.step(180, 95, onset))
        propagate(w, s, "checkout", onset, None, 64)
    elif variant == "upstream":
        w["api-gateway"]["config"]["env"]["INVENTORY_UPSTREAM"] = "http://inventory-svc.prod:8080"
        deploy(w, "api-gateway", "v3.7.0", TIMES[onset - 1], "Point inventory route at new service discovery name",
               {"INVENTORY_UPSTREAM": "http://inventory:8080 -> http://inventory-svc.prod:8080"})
        log(w, "api-gateway", TIMES[onset], "ERROR",
            "upstream connect error for GET /api/inventory/*: lookup inventory-svc.prod: no such host (502)", 900)
        setm(w, "api-gateway", "error_rate_pct", s.step(0.2, 38, onset))
        setm(w, "inventory", "rps", s.step(70, 28, onset))
        w["api-gateway"]["trace"] = {"endpoint": "GET /api/inventory/{sku}", "spans": [
            {"name": "route_match", "service": "api-gateway", "ms": 1},
            {"name": "auth.verify_jwt", "service": "api-gateway", "ms": 4},
            {"name": "proxy -> inventory", "service": "inventory-svc.prod", "ms": 2, "status": "error",
             "error": "lookup inventory-svc.prod: no such host"},
        ]}
    else:  # rate_limit
        w["api-gateway"]["config"]["env"]["RATE_LIMIT_RPS_PER_CLIENT"] = "5"
        deploy(w, "api-gateway", "v3.8.0", TIMES[onset - 1], "Update rate limiting policy",
               {"RATE_LIMIT_RPS_PER_CLIENT": "500 -> 5"})
        log(w, "api-gateway", TIMES[onset], "WARN",
            "rate limit exceeded for client 'web-frontend' (limit 5 rps), responding 429", 4100)
        setm(w, "api-gateway", "rejected_requests_pct", s.step(0.1, 64, onset))
        for svc_, base in (("checkout", 40), ("inventory", 70)):
            setm(w, svc_, "rps", s.step(base, base * 0.3, onset))


# ---------------------------------------------------------------------------
# Red herrings (unrelated anomalies)
# ---------------------------------------------------------------------------

def rh_cache_miss(w, s, onset):
    setm(w, "checkout", "cache_hit_rate_pct", s.step(94, 71, max(1, onset - 2), 0.01))
    log(w, "checkout", TIMES[max(1, onset - 2)], "WARN", "cache miss rate elevated (hit ratio 0.71, key prefix pricing:*)", 45)


def rh_unrelated_deploy(w, s, onset, svc="inventory"):
    deploy(w, svc, "v1.8.2" if svc == "inventory" else "v2.3.9", TIMES[max(0, onset - 2)],
           "Switch log output to structured JSON format", {"LOG_FORMAT": "text -> json"})
    w[svc]["config"]["env"]["LOG_FORMAT"] = "json"


def rh_noisy_warn(w, s, onset):
    log(w, "api-gateway", TIMES[0], "WARN", "client 'mobile-ios/4.2' using deprecated API version v1", 560)


def rh_gc_warn(w, s, onset):
    log(w, "checkout", TIMES[2], "WARN", "GC pause 140ms (young generation)", 9)


def rh_db_cpu_mild(w, s, onset):
    setm(w, "orders-db", "cpu_pct", s.step(25, 46, onset))
    log(w, "orders-db", TIMES[onset], "INFO", "checkpoint complete: wrote 18234 buffers (11.1%)", 2)


def rh_redis_evictions(w, s, onset):
    setm(w, "redis", "evictions_per_min", s.step(0.01, 32, onset - 1, 0.1))
    log(w, "redis", TIMES[onset - 1], "WARN", "maxmemory reached, evicting keys (allkeys-lru)", 30)


FAULTS = {
    "db_pool_exhaustion": fault_db_pool_exhaustion,
    "slow_db_query": fault_slow_db_query,
    "missing_env_var": fault_missing_env_var,
    "dependency_unavailable": fault_dependency_unavailable,
    "memory_leak": fault_memory_leak,
    "cpu_hot_loop": fault_cpu_hot_loop,
    "expired_credential": fault_expired_credential,
    "bad_config_deploy": fault_bad_config_deploy,
}

RED_HERRINGS = {
    "cache_miss": rh_cache_miss,
    "unrelated_deploy": rh_unrelated_deploy,
    "noisy_warn": rh_noisy_warn,
    "gc_warn": rh_gc_warn,
    "db_cpu_mild": rh_db_cpu_mild,
    "redis_evictions": rh_redis_evictions,
}


# ---------------------------------------------------------------------------
# Benchmark definition
# ---------------------------------------------------------------------------

def any_of(*pairs):
    return {"any_of": [list(p) for p in pairs]}


# (variant name, fault, fault params, red herrings, alert service, key evidence, split)
VARIANTS = [
    # --- db_pool_exhaustion ---
    ("pool-checkout-traffic", "db_pool_exhaustion", {"svc": "checkout", "cause": "traffic_spike"}, [], "checkout",
     [any_of(("get_service_metrics", "checkout"), ("search_logs", "checkout")),
      any_of(("get_trace", "checkout"), ("get_service_metrics", "orders-db"))], "dev"),
    ("pool-inventory-leak", "db_pool_exhaustion", {"svc": "inventory", "cause": "connection_leak"},
     ["cache_miss", {"unrelated_deploy": {"svc": "payment"}}], "checkout",
     [any_of(("get_service_metrics", "inventory"), ("search_logs", "inventory")),
      any_of(("get_trace", "inventory"), ("get_service_metrics", "orders-db"))], "eval"),
    ("pool-checkout-leak-dbcpu", "db_pool_exhaustion", {"svc": "checkout", "cause": "connection_leak"},
     ["db_cpu_mild", "unrelated_deploy"], "api-gateway",
     [any_of(("get_service_metrics", "checkout"), ("search_logs", "checkout")),
      any_of(("get_trace", "checkout"), ("get_service_metrics", "orders-db"))], "eval"),
    # --- slow_db_query ---
    ("slowq-checkout", "slow_db_query", {"svc": "checkout"}, ["gc_warn"], "checkout",
     [any_of(("get_trace", "checkout"), ("get_service_metrics", "orders-db"), ("search_logs", "orders-db"))], "dev"),
    ("slowq-inventory-confounded", "slow_db_query", {"svc": "inventory", "confounded": True}, ["noisy_warn"], "checkout",
     [any_of(("get_trace", "inventory"), ("get_service_metrics", "orders-db"), ("search_logs", "orders-db"))], "eval"),
    ("slowq-checkout-confounded", "slow_db_query", {"svc": "checkout", "confounded": True}, ["cache_miss"], "api-gateway",
     [any_of(("get_trace", "checkout"), ("get_service_metrics", "orders-db"), ("search_logs", "orders-db"))], "eval"),
    # --- missing_env_var ---
    ("envvar-payment", "missing_env_var", {"svc": "payment"}, ["noisy_warn"], "checkout",
     [any_of(("search_logs", "payment"), ("get_service_config", "payment"), ("get_trace", "payment"))], "dev"),
    ("envvar-checkout", "missing_env_var", {"svc": "checkout"}, ["cache_miss", "unrelated_deploy"], "api-gateway",
     [any_of(("search_logs", "checkout"), ("get_service_config", "checkout"), ("get_trace", "checkout"))], "eval"),
    # --- dependency_unavailable ---
    ("dep-payment", "dependency_unavailable", {"dep": "payment"}, [], "checkout",
     [any_of(("get_service_metrics", "payment"), ("search_logs", "payment"))], "dev"),
    ("dep-inventory", "dependency_unavailable", {"dep": "inventory"}, ["noisy_warn", "redis_evictions"], "api-gateway",
     [any_of(("get_service_metrics", "inventory"), ("search_logs", "inventory"))], "eval"),
    ("dep-payment-gc", "dependency_unavailable", {"dep": "payment"}, ["gc_warn", "unrelated_deploy"], "api-gateway",
     [any_of(("get_service_metrics", "payment"), ("search_logs", "payment"))], "eval"),
    # --- memory_leak ---
    ("leak-checkout", "memory_leak", {"svc": "checkout"}, ["redis_evictions"], "checkout",
     [any_of(("get_service_metrics", "checkout"), ("search_logs", "checkout"))], "dev"),
    ("leak-inventory-deploy", "memory_leak", {"svc": "inventory", "recent_deploy": True}, ["noisy_warn", "db_cpu_mild"],
     "checkout", [any_of(("get_service_metrics", "inventory"), ("search_logs", "inventory"))], "eval"),
    # --- cpu_hot_loop ---
    ("cpu-inventory", "cpu_hot_loop", {"svc": "inventory"}, ["cache_miss"], "checkout",
     [any_of(("get_service_metrics", "inventory"),),
      any_of(("get_trace", "inventory"), ("search_logs", "inventory"))], "dev"),
    ("cpu-gateway", "cpu_hot_loop", {"svc": "api-gateway"}, ["redis_evictions", "unrelated_deploy"], "api-gateway",
     [any_of(("get_service_metrics", "api-gateway"),),
      any_of(("get_trace", "api-gateway"), ("search_logs", "api-gateway"))], "eval"),
    # --- expired_credential ---
    ("cred-payment", "expired_credential", {"svc": "payment"}, ["gc_warn"], "checkout",
     [any_of(("search_logs", "payment"), ("get_service_config", "payment"), ("get_trace", "payment"))], "dev"),
    ("cred-inventory-cert", "expired_credential", {"svc": "inventory"}, ["db_cpu_mild", {"unrelated_deploy": {"svc": "payment"}}],
     "checkout", [any_of(("search_logs", "inventory"), ("get_service_config", "inventory"), ("get_trace", "inventory"))], "eval"),
    # --- bad_config_deploy ---
    ("config-timeout", "bad_config_deploy", {"variant": "timeout"}, ["noisy_warn"], "checkout",
     [any_of(("get_service_config", "checkout"),)], "dev"),
    ("config-upstream", "bad_config_deploy", {"variant": "upstream"}, ["cache_miss"], "api-gateway",
     [any_of(("get_service_config", "api-gateway"),)], "eval"),
    ("config-ratelimit", "bad_config_deploy", {"variant": "rate_limit"}, ["redis_evictions", "unrelated_deploy"], "api-gateway",
     [any_of(("get_service_config", "api-gateway"),)], "eval"),
]


def build_alert(services, svc, onset) -> str:
    m = {name: metric["series"] for name, metric in services[svc]["metrics"].items()}
    parts = []
    lat = m["latency_p95_ms"]
    if lat[-1] is not None and abs(lat[-1] - lat[0]) > 0.3 * lat[0]:
        parts.append(f"p95 latency {lat[0]:,} ms -> {lat[-1]:,} ms")
    err = m["error_rate_pct"]
    if err[-1] is not None and err[-1] - err[0] > 1:
        parts.append(f"5xx rate {err[0]}% -> {err[-1]}%")
    rej = m.get("rejected_requests_pct")
    if rej and rej[-1] - rej[0] > 1:
        parts.append(f"rejected (4xx) requests {rej[0]}% -> {rej[-1]}%")
    if not parts:
        parts.append(f"p95 latency {lat[0]:,} ms -> {lat[-1]:,} ms")
    return f"[ALERT {DATE} {TIMES[min(N - 1, onset + 1)]} UTC] {svc}: " + "; ".join(parts)


def finalize(w) -> dict:
    """Round numbers and attach units / timestamps."""
    services = {}
    for name, svc in w.items():
        metrics = {
            metric: {"unit": METRIC_UNITS[metric], "series": _round(series, METRIC_UNITS[metric])}
            for metric, series in svc["metrics"].items()
        }
        trace = None
        if svc["trace"]:
            trace = copy.deepcopy(svc["trace"])
            spans_ms = sum(sp["ms"] for sp in trace["spans"])
            trace["total_ms"] = spans_ms + trace.pop("self_time_ms", 6)
        services[name] = {
            "kind": svc["kind"],
            "depends_on": svc["depends_on"],
            "metrics": metrics,
            "logs": svc["logs"],
            "trace": trace,
            "config": svc["config"],
        }
    return services


def generate() -> None:
    rng = random.Random(SEED)
    order = list(range(len(VARIANTS)))
    rng.shuffle(order)  # case ids carry no information about the fault type

    SCENARIO_DIR.mkdir(exist_ok=True)
    for old in SCENARIO_DIR.glob("case_*.json"):
        old.unlink()

    labels = {}
    for case_num, variant_idx in enumerate(order, start=1):
        name, fault, params, herrings, alert_svc, key_evidence, split = VARIANTS[variant_idx]
        case_id = f"case_{case_num:03d}"
        s = Series(random.Random(f"{SEED}-{name}"))
        onset = s.rng.choice([4, 5, 6])
        w = healthy_world(s)
        FAULTS[fault](w, s, onset, **params)
        for rh in herrings:
            if isinstance(rh, dict):
                (rh_name, rh_params), = rh.items()
            else:
                rh_name, rh_params = rh, {}
            RED_HERRINGS[rh_name](w, s, onset, **rh_params)

        services = finalize(w)
        scenario = {
            "case_id": case_id,
            "alert": build_alert(services, alert_svc, onset),
            "window": {"date": DATE, "times": TIMES, "timezone": "UTC"},
            "services": services,
        }
        (SCENARIO_DIR / f"{case_id}.json").write_text(json.dumps(scenario, indent=2), encoding="utf-8")
        labels[case_id] = {
            "root_cause": fault,
            "split": split,
            "variant": name,
            "red_herrings": [next(iter(r)) if isinstance(r, dict) else r for r in herrings],
            "key_evidence": key_evidence,
        }

    LABELS_PATH.write_text(json.dumps(dict(sorted(labels.items())), indent=2), encoding="utf-8")
    dev = sum(1 for v in labels.values() if v["split"] == "dev")
    print(f"Wrote {len(labels)} scenarios to {SCENARIO_DIR} ({dev} dev / {len(labels) - dev} eval)")
    print(f"Wrote ground truth to {LABELS_PATH}")


if __name__ == "__main__":
    generate()
