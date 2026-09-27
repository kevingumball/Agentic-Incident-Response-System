"""Benchmark v2: harder, more discriminating incidents.

Phase 1 showed the v1 benchmark saturates (ReAct 97% on held-out): log lines often
state the answer (e.g. "total=20, active=20"). v2 tests whether an agent is misled
by the FIRST plausible signal. Design principles, fixed before any v2 run:

  1. Subtle evidence  - log lines no longer name the cause; the agent must combine sources
                        (e.g. "base_url must be a string, got None" + config without the variable).
  2. Coincident deploys - a harmless deploy lands in the same minute as the fault, always on a
                        service that is NOT faulty (so labels stay unambiguous).
  3. Misleading first signal - e.g. slow queries where pool-timeout errors dominate the logs.
  4. Missing data     - tracing disabled or a metric not exported on the faulty service.
  5. Distance         - faults surface 1-2 hops away from where the alert fires.
  6. Unknown          - incidents outside the taxonomy (disk full) where the right answer is "unknown".

Every case has a difficulty tier:
  easy   = phase-1 style explicit fault + one weak red herring
  medium = subtle evidence + 1-2 red herrings
  hard   = subtle evidence + coincident deploy + missing data and/or alert far from the fault

Splits: dev (18 = 9 labels x {medium, hard}) is used for ablations and fixes;
heldout (27 = 9 labels x {easy, medium, hard}) is run once, at the very end.

Outputs (separate files, as in v1):
  scenarios_v2/case_XXX.json    observable data only
  evaluation/labels_v2.json     ground truth, split, tier, key evidence

Usage:  python -m evaluation.generate_scenarios_v2
"""

from __future__ import annotations

import json
import random

from evaluation import generate_scenarios as v1
from evaluation.generate_scenarios import (
    DATE, N, ROOT, TIMES, Series, any_of, build_alert, deploy, finalize, healthy_world, log, propagate, setm, span,
)

SCENARIO_DIR = ROOT / "scenarios_v2"
LABELS_PATH = ROOT / "evaluation" / "labels_v2.json"
SEED = 2026

v1.METRIC_UNITS.setdefault("disk_used_pct", "%")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def reword(w, contains: str, new_text: str) -> None:
    """Replace every log message / span error containing `contains` with `new_text`."""
    hit = False
    for svc in w.values():
        for entry in svc["logs"]:
            if contains in entry["message"]:
                entry["message"], hit = new_text, True
        for sp in (svc["trace"] or {}).get("spans", []):
            if contains in sp.get("error", ""):
                sp["error"], hit = new_text, True
    if not hit:
        raise ValueError(f"reword: nothing contains {contains!r}")


def drop_logs(w, svc: str, contains: str) -> None:
    w[svc]["logs"] = [e for e in w[svc]["logs"] if contains not in e["message"]]


def set_log_count(w, svc: str, contains: str, count: int) -> None:
    for e in w[svc]["logs"]:
        if contains in e["message"]:
            e["count"] = count


# ---------------------------------------------------------------------------
# Subtle faults (built on the v1 fault functions, then made less explicit)
# ---------------------------------------------------------------------------

def subtle_pool(w, s, onset, svc="checkout", cause="traffic_spike"):
    v1.fault_db_pool_exhaustion(w, s, onset, svc=svc, cause=cause)
    reword(w, "HikariPool-1 - Connection is not available",
           "Timeout waiting for an idle database connection after 3000ms")
    if cause == "connection_leak":
        reword(w, "Connection leak detection", "Connection held for 61000ms by OrderRepository.findPending")


def subtle_slow_query(w, s, onset, svc="checkout", confounded=False):
    v1.fault_slow_db_query(w, s, onset, svc=svc, confounded=confounded)
    drop_logs(w, "orders-db", "auto_explain")
    if confounded:
        # The first thing in the caller's logs points at the pool, not the query.
        reword(w, "HikariPool-1 - Connection is not available",
               "Timeout waiting for an idle database connection after 3000ms")
        set_log_count(w, svc, "Timeout waiting for an idle database connection", 1400)
        set_log_count(w, svc, "slow query:", 300)


def subtle_missing_env(w, s, onset, svc="payment"):
    v1.fault_missing_env_var(w, s, onset, svc=svc)
    if svc == "payment":
        reword(w, "KeyError: 'PAYMENT_PROVIDER_URL'", "provider client init failed: base_url must be a string, got None")
    else:
        reword(w, "KeyError: 'ORDER_EVENTS_TOPIC'", "publish order_created failed: topic name must be a non-empty string, got None")


def external_provider_down(w, s, onset):
    """dependency_unavailable: payment's external provider is unreachable; payment itself is up."""
    log(w, "payment", TIMES[onset], "ERROR",
        "provider.create_charge failed: connect timeout after 5000ms (api.payprovider.example:443)", 610)
    setm(w, "payment", "error_rate_pct", s.step(0.2, 88, onset))
    setm(w, "payment", "latency_p95_ms", s.step(240, 5010, onset))
    span(w, "payment", "provider.create_charge", 5000, "error", "connect timeout after 5000ms")
    span(w, "checkout", "payment.charge", 5020, "error", "HTTP 504 Gateway Timeout from payment")
    log(w, "checkout", TIMES[onset], "ERROR", "payment.charge failed: HTTP 504 Gateway Timeout from payment", 600)
    propagate(w, s, "payment", onset, 5020, 42)


def reworded_dependency_unavailable(w, s, onset, dep="inventory"):
    v1.fault_dependency_unavailable(w, s, onset, dep=dep)
    op = {"payment": "payment.charge", "inventory": "inventory.reserve"}[dep]
    reword(w, f"{op} failed: connect ECONNREFUSED", f"{op} failed: upstream unavailable (retries exhausted)")
    reword(w, f"connect ECONNREFUSED {dep}:8080 after 3 retries", "upstream unavailable (retries exhausted)")


def subtle_memory_leak(w, s, onset, svc="checkout", keep_heap=True):
    v1.fault_memory_leak(w, s, onset, svc=svc)
    drop_logs(w, svc, "OOMKilled")  # early stage: no OOM kill yet
    setm(w, svc, "restarts", [0] * N)
    if not keep_heap:
        reword(w, "Full GC pause 870ms, heap", "Full GC pause 870ms")


def subtle_cpu(w, s, onset, svc="inventory", keep_log=False):
    v1.fault_cpu_hot_loop(w, s, onset, svc=svc)
    if not keep_log:
        drop_logs(w, svc, "Slow handler") if svc == "inventory" else drop_logs(w, svc, "auth.verify_jwt took")


def subtle_expired_credential(w, s, onset, svc="payment"):
    v1.fault_expired_credential(w, s, onset, svc=svc)
    if svc == "payment":
        reword(w, '"error_description":"The access token expired"',
               'provider.create_charge failed: POST https://api.payprovider.example/v1/charges -> 401 Unauthorized '
               '{"error":"invalid_token"}')
    else:
        reword(w, "tls: expired certificate", "TLS handshake failed: remote error: tls: bad certificate")


def subtle_bad_config(w, s, onset, variant="timeout"):
    if variant == "readonly_db":
        w["checkout"]["config"]["env"]["DB_URL"] = "postgres://orders-db-replica:5432/orders"
        deploy(w, "checkout", "v5.3.0", TIMES[onset - 1], "Route database traffic through new connection endpoint",
               {"DB_URL": "postgres://orders-db:5432/orders -> postgres://orders-db-replica:5432/orders"})
        log(w, "checkout", TIMES[onset], "ERROR",
            "insert_order failed: ERROR: cannot execute INSERT in a read-only transaction (SQLSTATE 25006)", 700)
        span(w, "checkout", "db.query insert_order", 3, "error", "cannot execute INSERT in a read-only transaction")
        setm(w, "checkout", "error_rate_pct", s.step(0.3, 86, onset))
        propagate(w, s, "checkout", onset, None, 78)
        return
    v1.fault_bad_config_deploy(w, s, onset, variant=variant)
    if variant == "timeout":
        reword(w, "request timed out after 50ms", "payment.charge failed: context deadline exceeded")
        reword(w, "timeout after 50ms", "context deadline exceeded")
    elif variant == "upstream":
        reword(w, "no such host (502)", "upstream connect error for GET /api/inventory/*: disconnect/reset before headers (502)")
        reword(w, "lookup inventory-svc.prod: no such host", "upstream connect error")


def disk_full(w, s, onset, explicit=True):
    """Outside the taxonomy: the database volume is full, writes fail. Correct answer: unknown."""
    setm(w, "orders-db", "disk_used_pct", s.step(71, 100, onset, 0.002))
    log(w, "orders-db", TIMES[onset], "ERROR",
        'could not extend file "base/16384/24576": No space left on device', 820)
    msg = ("insert_order failed: ERROR: could not extend file: No space left on device (SQLSTATE 53100)"
           if explicit else "insert_order failed: database error (SQLSTATE 53100)")
    log(w, "checkout", TIMES[onset], "ERROR", msg, 790)
    span(w, "checkout", "db.query insert_order", 4, "error", "SQLSTATE 53100")
    setm(w, "checkout", "error_rate_pct", s.step(0.3, 61, onset))
    propagate(w, s, "checkout", onset, None, 55)


def redis_misconf(w, s, onset):
    """Outside the taxonomy: Redis cannot persist to disk and rejects writes. Correct answer: unknown."""
    log(w, "redis", TIMES[onset], "ERROR",
        "MISCONF Redis is configured to save RDB snapshots, but it's currently unable to persist to disk. "
        "Commands that may modify the data set are disabled", 910)
    log(w, "checkout", TIMES[onset], "ERROR", "cache.set pricing failed: MISCONF errors writing to Redis", 880)
    setm(w, "redis", "ops_per_sec", s.step(5200, 3100, onset))
    span(w, "checkout", "cache.get pricing", 1, "error", "MISCONF")
    setm(w, "checkout", "error_rate_pct", s.step(0.3, 35, onset))
    propagate(w, s, "checkout", onset, None, 31)


FAULTS = {
    "pool": v1.fault_db_pool_exhaustion, "subtle_pool": subtle_pool,
    "slow": v1.fault_slow_db_query, "subtle_slow": subtle_slow_query,
    "env": v1.fault_missing_env_var, "subtle_env": subtle_missing_env,
    "dep": v1.fault_dependency_unavailable, "dep_reworded": reworded_dependency_unavailable,
    "provider_down": external_provider_down,
    "leak": v1.fault_memory_leak, "subtle_leak": subtle_memory_leak,
    "cpu": v1.fault_cpu_hot_loop, "subtle_cpu": subtle_cpu,
    "cred": v1.fault_expired_credential, "subtle_cred": subtle_expired_credential,
    "config": v1.fault_bad_config_deploy, "subtle_config": subtle_bad_config,
    "disk_full": disk_full, "redis_misconf": redis_misconf,
}


# ---------------------------------------------------------------------------
# Red herrings (v1 ones plus a strong coincident deploy)
# ---------------------------------------------------------------------------

def rh_coincident_deploy(w, s, onset, svc="api-gateway"):
    """A harmless deploy in the same minute the fault starts, on a service that is not at fault."""
    deploy(w, svc, "v9.4.1", TIMES[onset - 1], "Enable autumn promo banner", {"PROMO_BANNER_ENABLED": "false -> true"})
    w[svc]["config"]["env"]["PROMO_BANNER_ENABLED"] = "true"


RED_HERRINGS = dict(v1.RED_HERRINGS, coincident_deploy=rh_coincident_deploy)


# ---------------------------------------------------------------------------
# Case definitions
# (label, tier, fault, params, red herrings, missing data, alert service, key evidence)
# Missing data: ("trace", svc) disables tracing, ("metric", svc, name) drops a metric.
# ---------------------------------------------------------------------------

def cd(svc):
    return {"coincident_deploy": {"svc": svc}}


def ud(svc):
    return {"unrelated_deploy": {"svc": svc}}


M, L, T, C = "get_service_metrics", "search_logs", "get_trace", "get_service_config"

DEV = [
    ("db_pool_exhaustion", "medium", "subtle_pool", {"svc": "inventory", "cause": "traffic_spike"},
     ["cache_miss", cd("payment")], [], "checkout",
     [any_of((M, "inventory"), (L, "inventory")), any_of((T, "inventory"), (M, "orders-db"))]),
    ("db_pool_exhaustion", "hard", "subtle_pool", {"svc": "checkout", "cause": "connection_leak"},
     [cd("api-gateway"), "db_cpu_mild"], [("metric", "checkout", "db_pool_utilization_pct")], "api-gateway",
     [any_of((L, "checkout"), (T, "checkout")), any_of((T, "checkout"), (M, "orders-db"))]),
    ("slow_db_query", "medium", "subtle_slow", {"svc": "checkout"},
     ["redis_evictions", cd("inventory")], [], "checkout",
     [any_of((T, "checkout"), (M, "orders-db"), (L, "orders-db"))]),
    ("slow_db_query", "hard", "subtle_slow", {"svc": "inventory", "confounded": True},
     [cd("checkout"), "cache_miss"], [("trace", "inventory")], "api-gateway",
     [any_of((M, "orders-db"), (L, "orders-db"))]),
    ("missing_env_var", "medium", "subtle_env", {"svc": "checkout"},
     ["noisy_warn"], [], "api-gateway",
     [any_of((C, "checkout"),)]),
    ("missing_env_var", "hard", "subtle_env", {"svc": "payment"},
     [ud("inventory"), "cache_miss"], [("trace", "payment")], "api-gateway",
     [any_of((C, "payment"),)]),
    ("dependency_unavailable", "medium", "provider_down", {},
     ["gc_warn"], [], "checkout",
     [any_of((L, "payment"), (T, "payment"))]),
    ("dependency_unavailable", "hard", "dep_reworded", {"dep": "inventory"},
     [cd("checkout"), "redis_evictions"], [], "api-gateway",
     [any_of((M, "inventory"), (L, "inventory"))]),
    ("memory_leak", "medium", "subtle_leak", {"svc": "checkout", "keep_heap": True},
     ["redis_evictions"], [], "checkout",
     [any_of((M, "checkout"),)]),
    ("memory_leak", "hard", "subtle_leak", {"svc": "inventory", "keep_heap": False},
     [cd("checkout"), "db_cpu_mild"], [("trace", "inventory")], "api-gateway",
     [any_of((M, "inventory"),)]),
    ("cpu_hot_loop", "medium", "subtle_cpu", {"svc": "api-gateway"},
     ["cache_miss"], [], "api-gateway",
     [any_of((M, "api-gateway"),), any_of((T, "api-gateway"), (L, "api-gateway"))]),
    ("cpu_hot_loop", "hard", "subtle_cpu", {"svc": "inventory"},
     [cd("checkout"), "redis_evictions"], [("trace", "inventory")], "checkout",
     [any_of((M, "inventory"),)]),
    ("expired_credential", "medium", "subtle_cred", {"svc": "payment"},
     ["noisy_warn"], [], "checkout",
     [any_of((C, "payment"),)]),
    ("expired_credential", "hard", "subtle_cred", {"svc": "inventory"},
     [cd("checkout"), "db_cpu_mild"], [("trace", "inventory")], "api-gateway",
     [any_of((C, "inventory"),)]),
    ("bad_config_deploy", "medium", "subtle_config", {"variant": "timeout"},
     ["cache_miss"], [], "checkout",
     [any_of((C, "checkout"),)]),
    ("bad_config_deploy", "hard", "subtle_config", {"variant": "readonly_db"},
     ["db_cpu_mild", ud("inventory")], [], "api-gateway",
     [any_of((C, "checkout"),)]),
    ("unknown", "medium", "disk_full", {"explicit": True},
     ["noisy_warn"], [], "checkout",
     [any_of((L, "orders-db"), (M, "orders-db"))]),
    ("unknown", "hard", "redis_misconf", {},
     [cd("inventory"), "db_cpu_mild"], [], "api-gateway",
     [any_of((L, "redis"),)]),
]

HELDOUT = [
    ("db_pool_exhaustion", "easy", "pool", {"svc": "checkout", "cause": "traffic_spike"},
     ["noisy_warn"], [], "checkout",
     [any_of((M, "checkout"), (L, "checkout")), any_of((T, "checkout"), (M, "orders-db"))]),
    ("db_pool_exhaustion", "medium", "subtle_pool", {"svc": "checkout", "cause": "traffic_spike"},
     ["redis_evictions", cd("inventory")], [], "api-gateway",
     [any_of((M, "checkout"), (L, "checkout")), any_of((T, "checkout"), (M, "orders-db"))]),
    ("db_pool_exhaustion", "hard", "subtle_pool", {"svc": "inventory", "cause": "connection_leak"},
     [cd("checkout"), "db_cpu_mild"], [("metric", "inventory", "db_pool_utilization_pct")], "api-gateway",
     [any_of((L, "inventory"), (T, "inventory")), any_of((T, "inventory"), (M, "orders-db"))]),
    ("slow_db_query", "easy", "slow", {"svc": "inventory"},
     ["cache_miss"], [], "checkout",
     [any_of((T, "inventory"), (M, "orders-db"), (L, "orders-db"))]),
    ("slow_db_query", "medium", "subtle_slow", {"svc": "inventory"},
     ["noisy_warn", cd("payment")], [], "checkout",
     [any_of((T, "inventory"), (M, "orders-db"), (L, "orders-db"))]),
    ("slow_db_query", "hard", "subtle_slow", {"svc": "checkout", "confounded": True},
     [cd("api-gateway"), "redis_evictions"], [("trace", "checkout")], "api-gateway",
     [any_of((M, "orders-db"), (L, "orders-db"))]),
    ("missing_env_var", "easy", "env", {"svc": "payment"},
     ["gc_warn"], [], "checkout",
     [any_of((L, "payment"), (C, "payment"), (T, "payment"))]),
    ("missing_env_var", "medium", "subtle_env", {"svc": "payment"},
     ["redis_evictions"], [], "checkout",
     [any_of((C, "payment"),)]),
    ("missing_env_var", "hard", "subtle_env", {"svc": "checkout"},
     [cd("inventory"), "db_cpu_mild"], [("trace", "checkout")], "api-gateway",
     [any_of((C, "checkout"),)]),
    ("dependency_unavailable", "easy", "dep", {"dep": "payment"},
     ["noisy_warn"], [], "checkout",
     [any_of((M, "payment"), (L, "payment"))]),
    ("dependency_unavailable", "medium", "dep_reworded", {"dep": "inventory"},
     ["cache_miss"], [], "checkout",
     [any_of((M, "inventory"), (L, "inventory"))]),
    ("dependency_unavailable", "hard", "provider_down", {},
     [cd("checkout"), "gc_warn"], [("trace", "payment")], "api-gateway",
     [any_of((L, "payment"),)]),
    ("memory_leak", "easy", "leak", {"svc": "inventory"},
     ["redis_evictions"], [], "checkout",
     [any_of((M, "inventory"), (L, "inventory"))]),
    ("memory_leak", "medium", "subtle_leak", {"svc": "inventory", "keep_heap": True},
     ["noisy_warn", cd("payment")], [], "checkout",
     [any_of((M, "inventory"),)]),
    ("memory_leak", "hard", "subtle_leak", {"svc": "checkout", "keep_heap": False},
     [cd("api-gateway"), "cache_miss"], [("trace", "checkout")], "api-gateway",
     [any_of((M, "checkout"),)]),
    ("cpu_hot_loop", "easy", "cpu", {"svc": "inventory"},
     ["gc_warn"], [], "checkout",
     [any_of((M, "inventory"),), any_of((T, "inventory"), (L, "inventory"))]),
    ("cpu_hot_loop", "medium", "subtle_cpu", {"svc": "inventory"},
     ["noisy_warn", cd("payment")], [], "checkout",
     [any_of((M, "inventory"),), any_of((T, "inventory"), (L, "inventory"))]),
    ("cpu_hot_loop", "hard", "subtle_cpu", {"svc": "api-gateway"},
     [cd("checkout"), "redis_evictions"], [("trace", "api-gateway")], "api-gateway",
     [any_of((M, "api-gateway"),)]),
    ("expired_credential", "easy", "cred", {"svc": "inventory"},
     ["noisy_warn"], [], "checkout",
     [any_of((L, "inventory"), (C, "inventory"), (T, "inventory"))]),
    ("expired_credential", "medium", "subtle_cred", {"svc": "inventory"},
     ["cache_miss"], [], "checkout",
     [any_of((C, "inventory"),)]),
    ("expired_credential", "hard", "subtle_cred", {"svc": "payment"},
     [cd("checkout"), "redis_evictions"], [("trace", "payment")], "api-gateway",
     [any_of((C, "payment"),)]),
    ("bad_config_deploy", "easy", "config", {"variant": "rate_limit"},
     ["noisy_warn"], [], "api-gateway",
     [any_of((C, "api-gateway"),)]),
    ("bad_config_deploy", "medium", "subtle_config", {"variant": "upstream"},
     ["redis_evictions"], [], "api-gateway",
     [any_of((C, "api-gateway"),)]),
    ("bad_config_deploy", "hard", "subtle_config", {"variant": "timeout"},
     [cd("inventory"), "db_cpu_mild"], [("trace", "checkout")], "api-gateway",
     [any_of((C, "checkout"),)]),
    ("unknown", "easy", "disk_full", {"explicit": True},
     ["gc_warn"], [], "checkout",
     [any_of((L, "orders-db"), (M, "orders-db"))]),
    ("unknown", "medium", "redis_misconf", {},
     ["noisy_warn"], [], "checkout",
     [any_of((L, "redis"),)]),
    ("unknown", "hard", "disk_full", {"explicit": False},
     [cd("inventory"), "cache_miss"], [], "api-gateway",
     [any_of((L, "orders-db"), (M, "orders-db"))]),
]


def build_case(spec, s: Series) -> tuple[dict, dict]:
    label, tier, fault, params, herrings, missing, alert_svc, key_evidence = spec
    onset = s.rng.choice([4, 5, 6])
    w = healthy_world(s)
    FAULTS[fault](w, s, onset, **params)
    for rh in herrings:
        name, rh_params = (next(iter(rh.items())) if isinstance(rh, dict) else (rh, {}))
        RED_HERRINGS[name](w, s, onset, **rh_params)
    services = finalize(w)
    for item in missing:
        if item[0] == "trace":
            services[item[1]]["trace"] = {"unavailable": "trace sampling is disabled for this service"}
        else:
            services[item[1]]["metrics"].pop(item[2])
    scenario = {"alert": build_alert(services, alert_svc, onset),
                "window": {"date": DATE, "times": TIMES, "timezone": "UTC"}, "services": services}
    label_info = {"root_cause": label, "tier": tier, "fault": fault,
                  "red_herrings": [next(iter(r)) if isinstance(r, dict) else r for r in herrings],
                  "missing_data": [list(m) for m in missing], "key_evidence": key_evidence}
    return scenario, label_info


def generate() -> None:
    rng = random.Random(SEED)
    specs = [(spec, "dev") for spec in DEV] + [(spec, "heldout") for spec in HELDOUT]
    rng.shuffle(specs)  # case ids carry no information about label, tier or split

    SCENARIO_DIR.mkdir(exist_ok=True)
    for old in SCENARIO_DIR.glob("case_*.json"):
        old.unlink()
    labels = {}
    for i, (spec, split) in enumerate(specs, start=1):
        case_id = f"case_{i:03d}"
        s = Series(random.Random(f"{SEED}-{i}"))
        scenario, info = build_case(spec, s)
        scenario = {"case_id": case_id, **scenario}
        (SCENARIO_DIR / f"{case_id}.json").write_text(json.dumps(scenario, indent=2), encoding="utf-8")
        labels[case_id] = {"split": split, **info}
    LABELS_PATH.write_text(json.dumps(labels, indent=2), encoding="utf-8")
    counts = {sp: sum(v["split"] == sp for v in labels.values()) for sp in ("dev", "heldout")}
    print(f"Wrote {len(labels)} v2 scenarios to {SCENARIO_DIR} ({counts})")


if __name__ == "__main__":
    generate()
