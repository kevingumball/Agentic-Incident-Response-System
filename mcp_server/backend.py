"""Simulated observability backend.

Reads one scenario file (observable data only) and answers queries the way a
metrics / logging / tracing backend would, returning compact text summaries
instead of raw dumps so tool output stays small in the agent's context.

Swapping this class for one backed by Prometheus / Loki / Jaeger would not
change the MCP tool interface or the agent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
# Benchmark suites: v1 (phase 1) and v2 (harder, phase 2). Each directory holds observable data only.
SUITE_DIRS = {"v1": ROOT / "scenarios", "v2": ROOT / "scenarios_v2"}
SCENARIO_DIR = SUITE_DIRS["v1"]

LEVEL_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2, "DEBUG": 3}


def _fmt(v: float | int | None, unit: str) -> str:
    if v is None:
        return "no data"
    if unit == "%":
        return f"{v}%"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{v:,} {unit}" if unit not in ("count",) else f"{v}"


def summarize_series(series: list, times: list[str], unit: str) -> dict:
    """Baseline (median of first 3 points), current value, ratio and anomaly onset."""
    baseline_pts = [v for v in series[:3] if v is not None]
    baseline = median(baseline_pts) if baseline_pts else None
    current = series[-1]
    threshold = max(0.2 * abs(baseline), 1.0) if baseline is not None else None

    onset = None
    if baseline is not None:
        for t, v in zip(times, series):
            if v is None or abs(v - baseline) > threshold:
                onset = t
                break

    anomalous = baseline is not None and (current is None or abs(current - baseline) > threshold)
    if current is None:
        change = "no data (target not reporting)"
    elif baseline in (None, 0):
        change = "from 0" if current else "unchanged"
    else:
        change = f"{current / baseline:.1f}x baseline"
    return {
        "baseline": baseline, "current": current, "change": change,
        "status": "ANOMALOUS" if anomalous else "normal",
        "since": onset if anomalous else None, "unit": unit,
    }


class ScenarioBackend:
    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.services: dict = scenario["services"]
        self.times: list[str] = scenario["window"]["times"]
        self.applied_fixes: list[dict] = []

    @classmethod
    def load(cls, case_id: str, suite: str = "v1") -> "ScenarioBackend":
        if not re.fullmatch(r"case_\d{3}", case_id) or suite not in SUITE_DIRS:
            raise ValueError(f"invalid case id or suite: {case_id!r} / {suite!r}")
        path = SUITE_DIRS[suite] / f"{case_id}.json"
        return cls(json.loads(path.read_text(encoding="utf-8")))

    # -- helpers -------------------------------------------------------------

    def _unknown_service(self, service: str) -> str | None:
        if service in self.services:
            return None
        return f"Unknown service '{service}'. Known services: {', '.join(self.services)}."

    @property
    def alert(self) -> str:
        return self.scenario["alert"]

    # -- queries -------------------------------------------------------------

    def get_service_metrics(self, service: str, metric: str = "") -> str:
        if err := self._unknown_service(service):
            return err
        metrics = self.services[service]["metrics"]
        window = f"{self.times[0]}-{self.times[-1]} UTC"

        if not metric:
            lines = [f"Metrics for {service} ({window}); baseline = median of first 3 minutes:"]
            for name, m in metrics.items():
                s = summarize_series(m["series"], self.times, m["unit"])
                line = (f"- {name}: baseline {_fmt(s['baseline'], s['unit'])}, now {_fmt(s['current'], s['unit'])} "
                        f"({s['change']}) [{s['status']}")
                line += f" since {s['since']}]" if s["since"] else "]"
                lines.append(line)
            return "\n".join(lines)

        if metric not in metrics:
            return f"Metric '{metric}' not found for {service}. Available: {', '.join(metrics)}."
        m = metrics[metric]
        s = summarize_series(m["series"], self.times, m["unit"])
        points = ", ".join(f"{t}={_fmt(v, m['unit'])}" for t, v in zip(self.times, m["series"]))
        header = (f"{service} {metric} ({window}): baseline {_fmt(s['baseline'], s['unit'])}, "
                  f"now {_fmt(s['current'], s['unit'])} ({s['change']}) [{s['status']}"
                  + (f" since {s['since']}]" if s["since"] else "]"))
        return f"{header}\nSeries: {points}"

    def search_logs(self, service: str, query: str = "", limit: int = 15) -> str:
        if err := self._unknown_service(service):
            return err
        logs = self.services[service]["logs"]
        tokens = [t.lower() for t in re.split(r"\s+|\|", query) if t and t.upper() not in ("OR", "AND", "*")]
        matched = [
            entry for entry in logs
            if not tokens or any(tok in f"{entry['level']} {entry['message']}".lower() for tok in tokens)
        ]
        if not matched:
            return (f"No log lines for {service} matching '{query}' in the last 10 minutes "
                    f"({len(logs)} log patterns exist; try a broader query or an empty query).")
        matched.sort(key=lambda e: (LEVEL_ORDER.get(e["level"], 9), -e["count"]))
        total = sum(e["count"] for e in matched)
        by_level: dict[str, int] = {}
        for e in matched:
            by_level[e["level"]] = by_level.get(e["level"], 0) + e["count"]
        keywords = ", ".join(tokens) if tokens else "none (all logs)"
        lines = [
            f"Log search on {service} (keywords: {keywords}; a line matches if it contains ANY keyword): "
            f"{len(matched)} patterns / {total} lines "
            f"(by level: {', '.join(f'{k}={v}' for k, v in by_level.items())}). Actual log lines:"
        ]
        for e in matched[:limit]:
            lines.append(f"- [{e['level']}] first seen {e['time']}, x{e['count']}: {e['message']}")
        return "\n".join(lines)

    def get_trace(self, service: str) -> str:
        if err := self._unknown_service(service):
            return err
        svc = self.services[service]
        if svc["kind"] == "datastore":
            return (f"{service} is a datastore and emits no request traces. "
                    "Use get_service_metrics / search_logs for it, or get_trace on a calling service.")
        trace = svc["trace"]
        if not trace:
            return f"No traces received from {service} in the last 10 minutes (service may not be running)."
        if trace.get("unavailable"):
            return f"Tracing unavailable for {service}: {trace['unavailable']}."
        total = trace["total_ms"]
        status = "error" if any(sp.get("status") == "error" for sp in trace["spans"]) else "ok"
        lines = [f"Slowest recent trace for {service}: {trace['endpoint']} total {total:,} ms, status {status}",
                 "Spans (sequential):"]
        for sp in trace["spans"]:
            share = 100 * sp["ms"] / total if total else 0
            line = f"- {sp['name']} [{sp['service']}]: {sp['ms']:,} ms ({share:.0f}%)"
            if sp.get("status") and sp["status"] != "ok":
                line += f" status={sp['status']}"
            if sp.get("error"):
                line += f" error=\"{sp['error']}\""
            lines.append(line)
        self_time = total - sum(sp["ms"] for sp in trace["spans"])
        lines.append(f"- self time in {service} (not in child spans): {self_time:,} ms ({100 * self_time / total:.0f}%)")
        return "\n".join(lines)

    def get_service_config(self, service: str) -> str:
        if err := self._unknown_service(service):
            return err
        svc = self.services[service]
        cfg = svc["config"]
        lines = [f"Configuration for {service} ({svc['kind']}), depends on: {', '.join(svc['depends_on']) or 'nothing'}",
                 "Environment:"]
        lines += [f"- {k}={v}" for k, v in cfg["env"].items()]
        deploys = sorted(cfg["deploys"], key=lambda d: d["time"], reverse=True)
        lines.append("Recent deploys (newest first):" if deploys else "Recent deploys: none")
        for d in deploys[:3]:
            diff = "; ".join(f"{k}: {v}" for k, v in d["diff"].items()) or "no config changes"
            lines.append(f"- {d['time']} {d['version']}: {d['change']} ({diff})")
        return "\n".join(lines)

    def apply_fix(self, service: str, change: str) -> str:
        if err := self._unknown_service(service):
            return err
        record = {"service": service, "change": change, "sequence": len(self.applied_fixes) + 1}
        self.applied_fixes.append(record)
        return (f"SIMULATED: change #{record['sequence']} recorded for {service}: '{change}'. "
                "No real system was modified.")
