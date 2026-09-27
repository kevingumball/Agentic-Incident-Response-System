from agent.verifier import check_rules, open_objections


def obj(alternative, tool, service):
    return {"alternative": alternative, "check_tool": tool, "check_service": service, "why": "x"}


def test_objections_with_already_run_checks_are_dropped():
    done = [{"tool": "get_trace", "args": {"service": "checkout"}, "reason": "", "step": 1}]
    objections = [obj("slow_db_query", "get_trace", "checkout"), obj("slow_db_query", "get_service_metrics", "orders-db")]
    remaining = open_objections(objections, done, "db_pool_exhaustion")
    assert remaining == [objections[1]]


def test_objections_against_self_or_unknown_are_ignored():
    objections = [obj("db_pool_exhaustion", "get_trace", "checkout"), obj("unknown", "search_logs", "payment")]
    assert open_objections(objections, [], "db_pool_exhaustion") == []


def ev(source, supports, contradicts=()):
    return {"source": source, "service": "checkout", "observation": "x",
            "supports": list(supports), "contradicts": list(contradicts), "step": 1}


def test_passes_with_high_confidence_two_sources_and_weak_competitor():
    hyps = [{"label": "db_pool_exhaustion", "confidence": 0.91}, {"label": "slow_db_query", "confidence": 0.22}]
    evidence = [ev("metrics", ["db_pool_exhaustion"]), ev("logs", ["db_pool_exhaustion"])]
    check = check_rules(hyps, evidence)
    assert check.passed
    assert check.top["label"] == "db_pool_exhaustion"


def test_fails_when_competitor_still_strong():
    hyps = [{"label": "db_pool_exhaustion", "confidence": 0.82}, {"label": "slow_db_query", "confidence": 0.73}]
    evidence = [ev("metrics", ["db_pool_exhaustion"]), ev("traces", ["db_pool_exhaustion"])]
    check = check_rules(hyps, evidence)
    assert not check.passed
    assert any("slow_db_query" in r for r in check.reasons)


def test_fails_with_single_source_type_even_if_many_items():
    hyps = [{"label": "memory_leak", "confidence": 0.95}]
    evidence = [ev("metrics", ["memory_leak"]), ev("metrics", ["memory_leak"]), ev("metrics", ["memory_leak"])]
    check = check_rules(hyps, evidence)
    assert not check.passed
    assert any("source type" in r for r in check.reasons)


def test_fails_below_confidence_threshold():
    hyps = [{"label": "cpu_hot_loop", "confidence": 0.6}]
    evidence = [ev("metrics", ["cpu_hot_loop"]), ev("traces", ["cpu_hot_loop"])]
    assert not check_rules(hyps, evidence).passed


def test_unknown_is_never_accepted():
    hyps = [{"label": "unknown", "confidence": 0.9}]
    evidence = [ev("metrics", ["unknown"]), ev("logs", ["unknown"])]
    assert not check_rules(hyps, evidence).passed


def test_no_hypotheses():
    assert not check_rules([], []).passed


def test_uses_highest_confidence_regardless_of_order():
    hyps = [{"label": "slow_db_query", "confidence": 0.1}, {"label": "db_pool_exhaustion", "confidence": 0.9}]
    evidence = [ev("metrics", ["db_pool_exhaustion"]), ev("logs", ["db_pool_exhaustion"])]
    assert check_rules(hyps, evidence).top["label"] == "db_pool_exhaustion"


# --- phase-2 rules: checklist + margin -------------------------------------------------

from agent.verifier import check_rules_v2, checklist_gaps  # noqa: E402


def done(*pairs):
    return [{"tool": t, "args": {"service": s}, "reason": "", "step": i} for i, (t, s) in enumerate(pairs, 1)]


def test_checklist_requires_config_before_blaming_config():
    assert checklist_gaps("bad_config_deploy", "checkout", done(("search_logs", "checkout")))
    assert not checklist_gaps("bad_config_deploy", "checkout", done(("get_service_config", "checkout")))


def test_checklist_any_of_within_group():
    calls = done(("search_logs", "checkout"), ("get_service_metrics", "orders-db"))
    assert not checklist_gaps("db_pool_exhaustion", "checkout", calls)


def test_checklist_unknown_service_accepts_tool_anywhere():
    assert not checklist_gaps("dependency_unavailable", "payprovider-api (external)", done(("search_logs", "payment")))


def test_v2_margin_rule_replaces_absolute_competitor_threshold():
    evidence = [ev("metrics", ["memory_leak"]), ev("logs", ["memory_leak"])]
    calls = done(("get_service_metrics", "checkout"))
    close = [{"label": "memory_leak", "confidence": 0.9, "service": "checkout"},
             {"label": "cpu_hot_loop", "confidence": 0.7}]
    clear = [{"label": "memory_leak", "confidence": 0.9, "service": "checkout"},
             {"label": "cpu_hot_loop", "confidence": 0.55}]
    assert not check_rules_v2(close, evidence, calls).passed
    assert check_rules_v2(clear, evidence, calls).passed   # 0.55 would have blocked under the phase-1 rule


def test_objection_with_invented_tool_is_dropped():
    assert open_objections([obj("slow_db_query", "get_service_logs", "orders-db")], [], "db_pool_exhaustion") == []
