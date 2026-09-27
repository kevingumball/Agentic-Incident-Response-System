from evaluation.attribution import attribute, first_covering_step

KEY = [{"any_of": [["get_service_metrics", "orders-db"], ["get_trace", "checkout"]]}]
LABEL = {"root_cause": "slow_db_query", "key_evidence": KEY}


def call(tool, service):
    return {"tool": tool, "args": {"service": service}}


def hyp_step(step, top):
    return {"node": "hypothesis", "step": step, "hypotheses": [{"label": top, "confidence": 0.9}]}


def run(arch, predicted, calls, trace, status="diagnosed"):
    return {"architecture": arch, "predicted": predicted, "status": status, "tool_calls": calls, "trace": trace}


def test_first_covering_step():
    calls = [call("search_logs", "checkout"), call("get_trace", "checkout")]
    assert first_covering_step(calls, KEY) == 2
    assert first_covering_step(calls[:1], KEY) is None


def test_missing_key_evidence_is_a_planner_failure():
    r = run("verifier", "db_pool_exhaustion", [call("search_logs", "checkout")], [hyp_step(1, "db_pool_exhaustion")])
    assert attribute(r, LABEL)[0] == "planner_missed_key_evidence"


def test_truth_on_top_then_lost_is_drift():
    calls = [call("get_trace", "checkout"), call("search_logs", "checkout")]
    trace = [hyp_step(1, "slow_db_query"), hyp_step(2, "db_pool_exhaustion")]
    assert attribute(run("plan_hyp", "db_pool_exhaustion", calls, trace), LABEL)[0] == "hypothesis_drifted_away"


def test_budget_exhausted_with_truth_on_top_is_blocked():
    calls = [call("get_trace", "checkout")]
    trace = [hyp_step(1, "slow_db_query"),
             {"node": "verifier", "step": 1, "feedback": "Competing hypothesis db_pool_exhaustion is still at 0.60"}]
    r = run("plan_hyp_rules", "unknown", calls, trace, status="undetermined")
    assert attribute(r, LABEL)[0] == "blocked_correct_by_rules"


def test_verifier_accepting_wrong_label():
    calls = [call("get_trace", "checkout")]
    r = run("verifier", "db_pool_exhaustion", calls, [hyp_step(1, "db_pool_exhaustion")])
    assert attribute(r, LABEL)[0] == "verifier_accepted_wrong"


def test_react_categories():
    assert attribute(run("react", "db_pool_exhaustion", [], []), LABEL)[0] == "planner_missed_key_evidence"
    assert attribute(run("react", "db_pool_exhaustion", [call("get_trace", "checkout")], []), LABEL)[0] == "react_misread"
