"""Deterministic verifier rules (spec 7.3).

These run before (and independently of) the LLM skeptic. A diagnosis is only
accepted when all hard rules pass AND the LLM reviewer agrees.
"""

from dataclasses import dataclass, field

from agent import config
from agent.state import Evidence, Hypothesis


@dataclass
class RuleCheck:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    top: Hypothesis | None = None


def ranked(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    return sorted(hypotheses, key=lambda h: h["confidence"], reverse=True)


def support_sources(label: str, evidence: list[Evidence]) -> set[str]:
    return {e["source"] for e in evidence if label in e["supports"]}


def open_objections(objections: list[dict], actions_taken: list[dict], top_label: str) -> list[dict]:
    """Keep only reviewer objections that are still actionable.

    An objection must name a competing label and a check (tool + service) that has NOT been run
    yet. Objections whose check was already performed are dropped: that evidence already exists,
    so re-raising them cannot change the outcome and would only loop until the budget runs out.
    """
    done = {(c["tool"], c["args"].get("service")) for c in actions_taken}
    return [
        o for o in objections
        if o["alternative"] not in (top_label, "unknown")
        and o["check_tool"] in READ_TOOLS  # an invented tool name cannot be acted on
        and (o["check_tool"], o["check_service"]) not in done
    ]


# ---------------------------------------------------------------------------
# Phase-2 verifier: evidence checklist + margin rule
# ---------------------------------------------------------------------------

READ_TOOLS = {"get_service_metrics", "search_logs", "get_trace", "get_service_config"}
KNOWN_SERVICES = {"api-gateway", "checkout", "inventory", "payment", "orders-db", "redis"}
FAULTY = "$S"  # placeholder for the service the hypothesis blames

# Runbook-style evidence requirements, per root cause. Each group is satisfied by ANY of its
# (tool, service) checks; all groups must be satisfied before the label can be accepted.
# These encode generic SRE practice ("to blame a config, read the config"), not per-case answers.
CHECKLISTS: dict[str, list[list[tuple[str, str]]]] = {
    "db_pool_exhaustion": [[("get_service_metrics", FAULTY), ("search_logs", FAULTY)],
                           [("get_trace", FAULTY), ("get_service_metrics", "orders-db")]],
    "slow_db_query": [[("get_service_metrics", "orders-db"), ("search_logs", "orders-db")]],
    "missing_env_var": [[("get_service_config", FAULTY)]],
    "bad_config_deploy": [[("get_service_config", FAULTY)]],
    "expired_credential": [[("get_service_config", FAULTY)], [("search_logs", FAULTY), ("get_trace", FAULTY)]],
    "dependency_unavailable": [[("get_service_metrics", FAULTY), ("search_logs", FAULTY)]],
    "memory_leak": [[("get_service_metrics", FAULTY)]],
    "cpu_hot_loop": [[("get_service_metrics", FAULTY)], [("get_trace", FAULTY), ("search_logs", FAULTY)]],
}


def checklist_gaps(label: str, service: str, actions_taken: list[dict]) -> list[str]:
    """Unmet checklist groups for `label` blamed on `service`, rendered as suggested calls."""
    done = [(c["tool"], c["args"].get("service")) for c in actions_taken]
    gaps = []
    for group in CHECKLISTS.get(label, []):
        options = []
        for tool, svc in group:
            if svc == FAULTY:
                if service not in KNOWN_SERVICES:
                    # External or unnamed component: accept the tool on any service.
                    options.append((tool, None))
                    continue
                svc = service
            options.append((tool, svc))
        satisfied = any((t, s_) in done if s_ else any(d[0] == t for d in done) for t, s_ in options)
        if not satisfied:
            gaps.append(" or ".join(f'{t}(service="{s_}")' if s_ else f"{t}(any service)" for t, s_ in options))
    return gaps


def check_rules_v2(
    hypotheses: list[Hypothesis],
    evidence: list[Evidence],
    actions_taken: list[dict],
    *,
    confidence_threshold: float = config.CONFIDENCE_THRESHOLD,
    margin_threshold: float = config.MARGIN_THRESHOLD,
    min_source_types: int = config.MIN_SOURCE_TYPES,
) -> RuleCheck:
    """Phase-2 rules: confidence, source diversity, MARGIN over the runner-up, and the evidence
    checklist of the top label (checked against the calls actually made, not LLM judgment)."""
    if not hypotheses:
        return RuleCheck(False, ["No hypotheses yet."])
    order = ranked(hypotheses)
    top = order[0]
    reasons: list[str] = []
    if top["label"] == "unknown":
        reasons.append("Top hypothesis is 'unknown'; gather evidence that points to a specific cause.")
    if top["confidence"] < confidence_threshold:
        reasons.append(f"Top hypothesis {top['label']} has confidence {top['confidence']:.2f} < {confidence_threshold}.")
    sources = support_sources(top["label"], evidence)
    if len(sources) < min_source_types:
        reasons.append(f"Supporting evidence for {top['label']} comes from {len(sources)} source type(s); "
                       f"need at least {min_source_types}.")
    if len(order) > 1 and top["confidence"] - order[1]["confidence"] < margin_threshold:
        reasons.append(f"{top['label']} ({top['confidence']:.2f}) does not lead {order[1]['label']} "
                       f"({order[1]['confidence']:.2f}) by {margin_threshold}; find discriminating evidence.")
    gaps = checklist_gaps(top["label"], top.get("service", ""), actions_taken)
    if gaps:
        reasons.append(f"Before concluding {top['label']}, run: " + "; ".join(gaps) + ".")
    return RuleCheck(not reasons, reasons, top)


def check_rules(
    hypotheses: list[Hypothesis],
    evidence: list[Evidence],
    *,
    confidence_threshold: float = config.CONFIDENCE_THRESHOLD,
    competitor_threshold: float = config.COMPETITOR_THRESHOLD,
    min_source_types: int = config.MIN_SOURCE_TYPES,
) -> RuleCheck:
    if not hypotheses:
        return RuleCheck(False, ["No hypotheses yet."])

    order = ranked(hypotheses)
    top = order[0]
    reasons: list[str] = []

    if top["label"] == "unknown":
        reasons.append("Top hypothesis is 'unknown'; gather evidence that points to a specific cause.")
    if top["confidence"] < confidence_threshold:
        reasons.append(
            f"Top hypothesis {top['label']} has confidence {top['confidence']:.2f} < {confidence_threshold}."
        )

    sources = support_sources(top["label"], evidence)
    if len(sources) < min_source_types:
        have = ", ".join(sorted(sources)) or "none"
        reasons.append(
            f"Supporting evidence for {top['label']} comes from {len(sources)} source type(s) ({have}); "
            f"need at least {min_source_types} different types (metrics / logs / traces / config)."
        )

    if len(order) > 1 and order[1]["confidence"] >= competitor_threshold:
        second = order[1]
        reasons.append(
            f"Competing hypothesis {second['label']} is still at {second['confidence']:.2f} "
            f"(>= {competitor_threshold}); find evidence that discriminates it from {top['label']}."
        )

    return RuleCheck(not reasons, reasons, top)
