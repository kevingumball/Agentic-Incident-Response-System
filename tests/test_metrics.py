from evaluation.metrics import aggregate, key_evidence_covered, score_run

LABEL = {
    "root_cause": "db_pool_exhaustion",
    "key_evidence": [
        {"any_of": [["get_service_metrics", "checkout"], ["search_logs", "checkout"]]},
        {"any_of": [["get_trace", "checkout"], ["get_service_metrics", "orders-db"]]},
    ],
}


def call(tool, service):
    return {"tool": tool, "args": {"service": service}}


def run(predicted, confidence, calls, status="diagnosed", case="case_001"):
    return {"case_id": case, "predicted": predicted, "confidence": confidence, "status": status,
            "tool_calls": calls, "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.001, "seconds": 1.0}


def test_key_evidence_requires_every_group():
    assert not key_evidence_covered([call("search_logs", "checkout")], LABEL["key_evidence"])
    assert key_evidence_covered([call("search_logs", "checkout"), call("get_trace", "checkout")], LABEL["key_evidence"])


def test_correct_guess_without_key_evidence_is_premature():
    s = score_run(run("db_pool_exhaustion", 0.9, [call("search_logs", "checkout")]), LABEL)
    assert s["correct"] and s["premature"] and not s["false_diagnosis"]


def test_confident_wrong_answer_is_false_diagnosis():
    s = score_run(run("slow_db_query", 0.85, []), LABEL)
    assert s["false_diagnosis"] and not s["correct"]


def test_unknown_is_neither_premature_nor_false():
    s = score_run(run("unknown", 0.4, [], status="undetermined"), LABEL)
    assert not s["premature"] and not s["false_diagnosis"] and not s["diagnosed"]


def test_aggregate_counts_cases_correct_in_every_run():
    labels = {"case_001": LABEL, "case_002": LABEL}
    full = [call("get_service_metrics", "checkout"), call("get_trace", "checkout")]
    runs = [
        run("db_pool_exhaustion", 0.9, full, case="case_001"),
        run("db_pool_exhaustion", 0.9, full, case="case_001"),
        run("db_pool_exhaustion", 0.9, full, case="case_002"),
        run("slow_db_query", 0.9, full, case="case_002"),
    ]
    stats = aggregate(runs, labels)
    assert stats["correct_runs"] == 3
    assert stats["cases_always_correct"] == 1
    assert stats["premature_diagnosis_rate"] == 0
    assert stats["false_diagnosis_rate"] == 0.25


def test_errored_run_is_never_correct_even_when_truth_is_unknown():
    label = {"root_cause": "unknown", "key_evidence": []}
    s = score_run(run("unknown", 0.0, [], status="error"), label)
    assert not s["correct"] and s["error"]
