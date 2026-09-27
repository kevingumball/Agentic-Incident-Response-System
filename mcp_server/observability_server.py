"""Observability MCP server.

Exposes read-only observability tools plus one (simulated) write tool over MCP
stdio. One server process serves exactly one incident scenario:

    python -m mcp_server.observability_server --scenario case_003

The server only ever reads scenarios/<case>.json (observable data). Ground
truth lives with the evaluation harness and is never loaded here.
"""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from mcp_server.backend import ScenarioBackend

SERVICES = "api-gateway, checkout, inventory, payment, orders-db (PostgreSQL), redis"

mcp = FastMCP(
    "observability",
    instructions=(
        "Observability tools for the shop platform. Services: " + SERVICES + ". "
        "All queries cover the last 10 minutes."
    ),
    log_level="WARNING",
)
backend: ScenarioBackend | None = None


def _backend() -> ScenarioBackend:
    if backend is None:
        raise RuntimeError("No scenario loaded")
    return backend


@mcp.resource("alert://current")
def current_alert() -> str:
    """The currently firing alert (what the pager sends to the on-call)."""
    return _backend().alert


@mcp.tool()
def get_service_metrics(service: str, metric: str = "") -> str:
    """Get metric summaries for a service over the last 10 minutes.

    Services: api-gateway, checkout, inventory, payment, orders-db, redis.
    Leave `metric` empty to get every metric of the service with baseline, current value,
    change and anomaly status (recommended first). Pass a metric name
    (e.g. latency_p95_ms, error_rate_pct, cpu_pct, memory_mb, db_pool_utilization_pct)
    to get its full per-minute series.
    """
    return _backend().get_service_metrics(service, metric)


@mcp.tool()
def search_logs(service: str, query: str = "") -> str:
    """Search a service's logs from the last 10 minutes.

    `query` is a set of keywords matched case-insensitively (any keyword matches),
    e.g. "error timeout". Leave it empty to list all log patterns.
    Returns deduplicated log patterns with counts, most severe first.
    """
    return _backend().search_logs(service, query)


@mcp.tool()
def get_trace(service: str) -> str:
    """Get the slowest recent distributed trace for a service's main endpoint.

    Shows each child span (with the service that handled it), its duration,
    its share of total request time, and any span errors.
    """
    return _backend().get_trace(service)


@mcp.tool()
def get_service_config(service: str) -> str:
    """Get a service's current environment configuration and its recent deploys (with config diffs)."""
    return _backend().get_service_config(service)


@mcp.tool()
def apply_fix(service: str, change: str) -> str:
    """WRITE ACTION (simulated). Apply a remediation to a service.

    Must only be called after a human has approved the change. In this
    environment the change is recorded but no real system is modified.
    """
    return _backend().apply_fix(service, change)


READ_ONLY_TOOLS = ("get_service_metrics", "search_logs", "get_trace", "get_service_config")
WRITE_TOOLS = ("apply_fix",)


def main() -> None:
    global backend
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, help="scenario id, e.g. case_003")
    parser.add_argument("--suite", default="v1", help="benchmark suite: v1 or v2")
    args = parser.parse_args()
    backend = ScenarioBackend.load(args.scenario, args.suite)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
