"""Root-cause taxonomy shared by the agent, the baseline and the benchmark.

Every diagnosis must be one of these labels (or "unknown"). The descriptions are
given to the LLM so that labels have precise, non-overlapping meanings.
"""

from typing import Literal

RootCauseLabel = Literal[
    "db_pool_exhaustion",
    "slow_db_query",
    "missing_env_var",
    "dependency_unavailable",
    "memory_leak",
    "cpu_hot_loop",
    "expired_credential",
    "bad_config_deploy",
    "unknown",
]

ROOT_CAUSES: dict[str, str] = {
    "db_pool_exhaustion": (
        "The application's database connection pool is saturated (~100% of connections in use). "
        "Requests wait to ACQUIRE a connection and time out, while the database itself is healthy "
        "(normal DB CPU and query latency). Caused by traffic growth or connections not being released."
    ),
    "slow_db_query": (
        "Database queries themselves are slow (e.g. full table scans / missing index). DB CPU and "
        "query latency are high and the time is spent EXECUTING queries, not acquiring connections. "
        "The pool may also fill up as a side effect."
    ),
    "missing_env_var": (
        "A required environment variable is ABSENT from a service's configuration, so code paths that "
        "read it crash (e.g. KeyError / 'required setting not found'). Takes precedence over "
        "bad_config_deploy when the failure is caused by an absent variable."
    ),
    "dependency_unavailable": (
        "A downstream service is down or unreachable (instances not running, connection refused), "
        "so its callers fail. The downstream service's own configuration and credentials are not the cause."
    ),
    "memory_leak": (
        "A service's memory grows steadily until it hits its limit, causing long GC pauses and "
        "OOM kills / restarts."
    ),
    "cpu_hot_loop": (
        "A service's CPU is saturated by expensive computation inside its own code path, making all of "
        "its requests slow while its downstream dependencies stay fast."
    ),
    "expired_credential": (
        "Calls to a dependency are rejected because a token, API key or certificate has expired "
        "(401/403, invalid_token, expired certificate)."
    ),
    "bad_config_deploy": (
        "A recent deploy set a configuration value to a WRONG value (e.g. timeout too low, wrong "
        "upstream URL, wrong limit). The variable exists, but its new value breaks the service."
    ),
}

LABELS: list[str] = list(ROOT_CAUSES)


def taxonomy_prompt() -> str:
    """Render the taxonomy as a bullet list for prompts."""
    lines = [f"- {label}: {desc}" for label, desc in ROOT_CAUSES.items()]
    lines.append("- unknown: none of the above fits the evidence.")
    return "\n".join(lines)
