"""Resume + out-of-credits behaviour of the benchmark runner (no LLM calls: run_incident is faked)."""

import asyncio
import json

from agent.runner import RunResult
from evaluation import run_eval

LABELS = {
    "case_001": {"root_cause": "memory_leak", "split": "heldout", "key_evidence": []},
    "case_002": {"root_cause": "unknown", "split": "heldout", "key_evidence": []},
}


def record(case, arch, repeat, error=None):
    r = RunResult(case_id=case, architecture=arch, model="m", predicted="memory_leak", status="diagnosed")
    if error:
        r.status, r.predicted, r.error = "error", "unknown", error
    return r.to_dict() | {"repeat": repeat}


def fake_runner(calls, quota_after=None):
    async def run_incident(case, arch, **_):
        calls.append((case, arch))
        if quota_after is not None and len(calls) > quota_after:
            return RunResult(case_id=case, architecture=arch, model="m", status="error",
                             error="OpenAIRateLimitError: 429 insufficient_quota")
        return RunResult(case_id=case, architecture=arch, model="m", predicted="memory_leak", status="diagnosed")
    return run_incident


def test_resume_keeps_successes_and_reruns_only_errored(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "load_labels", lambda suite="v1": LABELS)
    calls = []
    monkeypatch.setattr(run_eval, "run_incident", fake_runner(calls))
    existing = [record("case_001", "react", 0), record("case_002", "react", 0, error="boom")]
    records = asyncio.run(run_eval.run_benchmark("v2", "heldout", 1, ["react"], 2, None, tmp_path, existing))
    assert calls == [("case_002", "react")]
    assert len(records) == 2 and not any(r["error"] for r in records)
    assert len((tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_out_of_credits_stops_and_does_not_record_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "load_labels", lambda suite="v1": LABELS)
    calls = []
    monkeypatch.setattr(run_eval, "run_incident", fake_runner(calls, quota_after=1))
    records = asyncio.run(run_eval.run_benchmark("v2", "heldout", 3, ["react"], 1, None, tmp_path, None))
    assert len(records) == 1                      # only the successful run is kept
    assert len(calls) == 2                        # stopped right after the first quota error
    lines = (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["error"] for line in lines] == [None]
