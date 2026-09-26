"""Evaluation metrics (pure functions over run records + ground truth)."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

HIGH_CONFIDENCE = 0.8


def called(tool_calls: list[dict], tool: str, service: str) -> bool:
    return any(c["tool"] == tool and c["args"].get("service") == service for c in tool_calls)


def key_evidence_covered(tool_calls: list[dict], key_evidence: list[dict]) -> bool:
    """Every requirement group must be satisfied by at least one of its alternatives."""
    return all(
        any(called(tool_calls, tool, service) for tool, service in group["any_of"])
        for group in key_evidence
    )


def score_run(run: dict, label: dict) -> dict:
    """Per-run flags used by the aggregate metrics."""
    predicted = run["predicted"]
    diagnosed = predicted != "unknown" and run["status"] != "error"
    correct = predicted == label["root_cause"]
    return {
        "correct": correct,
        "diagnosed": diagnosed,
        "false_diagnosis": diagnosed and not correct and run["confidence"] >= HIGH_CONFIDENCE,
        "premature": diagnosed and not key_evidence_covered(run["tool_calls"], label["key_evidence"]),
        "error": run["status"] == "error",
    }


def aggregate(runs: list[dict], labels: dict[str, dict]) -> dict:
    """Summary metrics for one architecture."""
    if not runs:
        return {}
    scored = [(r, score_run(r, labels[r["case_id"]])) for r in runs]
    n = len(scored)

    by_case: dict[str, list[bool]] = defaultdict(list)
    for r, s in scored:
        by_case[r["case_id"]].append(s["correct"])

    costs = [r["cost_usd"] for r, _ in scored if r.get("cost_usd") is not None]
    ok = [r for r, s in scored if not s["error"]]
    return {
        "runs": n,
        "correct_runs": sum(s["correct"] for _, s in scored),
        "accuracy": sum(s["correct"] for _, s in scored) / n,
        "cases": len(by_case),
        "cases_always_correct": sum(all(v) for v in by_case.values()),
        "false_diagnosis_rate": sum(s["false_diagnosis"] for _, s in scored) / n,
        "premature_diagnosis_rate": sum(s["premature"] for _, s in scored) / n,
        "unknown_rate": sum(not s["diagnosed"] and not s["error"] for _, s in scored) / n,
        "errors": sum(s["error"] for _, s in scored),
        "avg_tool_calls": mean(len(r["tool_calls"]) for r in ok) if ok else 0.0,
        "avg_tokens": mean(r["input_tokens"] + r["output_tokens"] for r in ok) if ok else 0.0,
        "avg_cost_usd": mean(costs) if costs else None,
        "avg_seconds": mean(r["seconds"] for r in ok) if ok else 0.0,
    }


def per_root_cause(runs: list[dict], labels: dict[str, dict]) -> dict[str, tuple[int, int]]:
    """root cause -> (correct runs, total runs)."""
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in runs:
        rc = labels[r["case_id"]]["root_cause"]
        out[rc][1] += 1
        out[rc][0] += r["predicted"] == rc
    return {k: (v[0], v[1]) for k, v in sorted(out.items())}


def confusions(runs: list[dict], labels: dict[str, dict]) -> dict[tuple[str, str], int]:
    """(true, predicted) -> count, for wrong predictions only."""
    out: dict[tuple[str, str], int] = defaultdict(int)
    for r in runs:
        truth = labels[r["case_id"]]["root_cause"]
        if r["predicted"] != truth:
            out[(truth, r["predicted"])] += 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
