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
        if o["alternative"] not in (top_label, "unknown") and (o["check_tool"], o["check_service"]) not in done
    ]


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
