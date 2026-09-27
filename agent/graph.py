"""Planner + Hypothesis + Verifier incident agent (LangGraph).

START -> triage -> planner -> executor -> hypothesis -> verifier
                     ^                                   |
                     +------------ insufficient ---------+
verifier -> remediation -> human_approval -> apply_fix -> report -> END
verifier -> report  (step budget exhausted: undetermined)
"""

from __future__ import annotations

import inspect
import time
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agent import config, prompts
from agent.mcp_client import WRITE_TOOLS, content_to_text
from agent.schemas import (
    HypothesisUpdate,
    PlannerDecision,
    PlannerDecisionOrConclude,
    RemediationProposal,
    SkepticReview,
    TriageResult,
)
from agent.state import TOOL_SOURCE, Evidence, Hypothesis, IncidentState, Observation, ToolCall
from agent.verifier import check_rules, check_rules_v2, open_objections, ranked

MAX_LABELS_PER_EVIDENCE = 2


def make_llm(model: str | None = None) -> ChatOpenAI:
    # Normal calls finish in 1-5 s. Some requests stall until the timeout under concurrent load,
    # so a short timeout with more retries bounds that stall (phase 2, DEVLOG 10.2).
    return ChatOpenAI(model=model or config.MODEL, temperature=config.TEMPERATURE,
                      max_retries=config.LLM_MAX_RETRIES, timeout=config.LLM_TIMEOUT_S)


# ---------------------------------------------------------------------------
# Prompt formatting helpers
# ---------------------------------------------------------------------------

def fmt_call(call: ToolCall | dict) -> str:
    args = ", ".join(f'{k}="{v}"' for k, v in call["args"].items() if v != "")
    return f"{call['tool']}({args})"


def fmt_evidence(evidence: list[Evidence]) -> str:
    if not evidence:
        return "(none yet)"
    lines = []
    for i, e in enumerate(evidence, 1):
        tags = []
        if e["supports"]:
            tags.append("supports " + ", ".join(e["supports"]))
        if e["contradicts"]:
            tags.append("contradicts " + ", ".join(e["contradicts"]))
        lines.append(f"E{i} [{e['source']}/{e['service']}] {e['observation']}" + (f" ({'; '.join(tags)})" if tags else ""))
    return "\n".join(lines)


def fmt_hypotheses(hypotheses: list[Hypothesis]) -> str:
    if not hypotheses:
        return "(none yet)"
    return "\n".join(f"- {h['label']}: {h['confidence']:.2f}" for h in ranked(hypotheses))


def fmt_observations(observations: list[Observation]) -> str:
    if not observations:
        return "(none yet)"
    return "\n\n".join(f"[step {o['step']}] {o['call']}\n{o['output']}" for o in observations)


def investigation_context(state: IncidentState, *, exclude_latest_output: bool = False) -> str:
    """Everything the LLM nodes reason over: structured state plus the raw tool outputs.

    The raw outputs are kept (not only the evidence summaries) so no detail is lost between
    steps; the evidence log is an annotated index on top of them.
    """
    calls = state.get("actions_taken", [])
    observations = state.get("observations", [])
    if exclude_latest_output:
        observations = observations[:-1]
    return (
        f"ALERT: {state['alert']}\n"
        f"Alerting service: {state.get('service')} | severity: {state.get('severity')}\n"
        f"Symptoms: {'; '.join(state.get('symptoms', []))}\n\n"
        f"Raw tool outputs so far:\n{fmt_observations(observations)}\n\n"
        f"Evidence log:\n{fmt_evidence(state.get('evidence', []))}\n\n"
        f"Hypotheses:\n{fmt_hypotheses(state.get('hypotheses', []))}\n\n"
        f"Calls already made:\n" + ("\n".join(f"- {fmt_call(c)}" for c in calls) or "(none)")
    )


def build_report(state: IncidentState) -> str:
    status = state.get("status", "undetermined")
    lines = ["# Incident report", "", f"- **Alert:** {state['alert']}", f"- **Status:** {status}"]
    rc = state.get("root_cause")
    if rc:
        lines.append(f"- **Root cause:** `{rc['label']}` (confidence {rc['confidence']:.2f})")
    else:
        best = ranked(state.get("hypotheses", []))
        if best:
            lines.append(f"- **Undetermined.** Best hypothesis so far: `{best[0]['label']}` ({best[0]['confidence']:.2f})")
        if state.get("verifier_feedback"):
            lines.append(f"- **Open question:** {state['verifier_feedback']}")
    lines += ["", "## Evidence", ""]
    lines += [f"- {line}" for line in fmt_evidence(state.get("evidence", [])).splitlines()]
    lines += ["", "## Investigation steps", ""]
    lines += [f"{c['step']}. `{fmt_call(c)}` - {c['reason']}" for c in state.get("actions_taken", [])]
    rem = state.get("remediation")
    if rem:
        lines += ["", "## Remediation", "",
                  f"**Proposed action ({rem['risk']} risk):** `{rem['action']}` on `{rem['service']}`", ""]
        lines += [f"{i}. {s}" for i, s in enumerate(rem["steps"], 1)]
        lines += ["", f"- **Human approval:** {'approved' if state.get('approved') else 'rejected'}"]
        if state.get("fix_result"):
            lines.append(f"- **Result:** {state['fix_result']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

Verification = Literal["none", "rules", "rules+skeptic", "checklist", "checklist+skeptic"]


class IncidentAgent:
    """Planner + Hypothesis agent with a configurable verification stage (for ablations).

    verification="none"          planner decides when to conclude (no verifier)
    verification="rules"         hard rules only
    verification="rules+skeptic" hard rules, then the LLM skeptic (the phase-1 system)
    verification="checklist"     phase-2 rules: margin rule + per-label evidence checklist
    verification="checklist+skeptic"  phase-2 rules, then the skeptic (definition + objections)
    """

    def __init__(self, tools: dict[str, BaseTool], llm: ChatOpenAI | None = None,
                 max_steps: int = config.MAX_STEPS, verification: Verification = "rules+skeptic"):
        self.tools = tools
        self.read_tools = {n: t for n, t in tools.items() if n not in WRITE_TOOLS}
        self.max_steps = max_steps
        self.verification = verification
        llm = llm or make_llm()

        def structured(schema):
            return llm.with_structured_output(schema, method="function_calling")

        self.triage_llm = structured(TriageResult)
        self.planner_llm = structured(PlannerDecisionOrConclude if verification == "none" else PlannerDecision)
        self.hypothesis_llm = structured(HypothesisUpdate)
        self.skeptic_llm = structured(SkepticReview)
        self.remediation_llm = structured(RemediationProposal)
        tool_docs = "\n".join(f"- {t.name}{list(t.args)}: {t.description}" for t in self.read_tools.values())
        self.planner_system = prompts.PLANNER_SYSTEM.replace("{tools}", tool_docs)
        if verification == "none":
            self.planner_system += prompts.PLANNER_CONCLUDE_OPTION

    # -- nodes ---------------------------------------------------------------

    async def triage(self, state: IncidentState) -> dict:
        r: TriageResult = await self.triage_llm.ainvoke(
            [SystemMessage(prompts.TRIAGE_SYSTEM), HumanMessage(state["alert"])]
        )
        return {"service": r.service, "symptoms": r.symptoms, "severity": r.severity,
                "hypotheses": [], "step_count": 0, "status": "investigating", "verifier_feedback": ""}

    async def planner(self, state: IncidentState) -> dict:
        steps_left = self.max_steps - state.get("step_count", 0)
        feedback = state.get("verifier_feedback") or "(none)"
        d: PlannerDecision = await self.planner_llm.ainvoke([
            SystemMessage(self.planner_system),
            HumanMessage(f"{investigation_context(state)}\n\nVerifier feedback: {feedback}\n"
                         f"Tool calls remaining: {steps_left}\n\nChoose the next check."),
        ])
        if d.tool == "conclude":
            return {"next_action": {"tool": "conclude", "args": {}, "reason": d.reasoning, "step": 0},
                    "_trace": {"action": "conclude", "reason": d.reasoning}}
        schema_args = self.read_tools[d.tool].args
        candidate = {"service": d.service, "metric": d.metric, "query": d.query}
        args = {k: v for k, v in candidate.items() if k in schema_args and (k == "service" or v)}
        action = {"tool": d.tool, "args": args, "reason": d.reasoning, "step": 0}
        return {"next_action": action, "_trace": {"action": fmt_call(action), "reason": d.reasoning}}

    def conclude(self, state: IncidentState) -> dict:
        """No-verifier ablation: accept the current top hypothesis when the planner says so."""
        best = ranked(state.get("hypotheses", []))
        if not best or best[0]["label"] == "unknown":
            return {"status": "undetermined", "root_cause": None, "_trace": {"decision": "undetermined"}}
        return {"status": "diagnosed", "root_cause": best[0], "_trace": {"decision": "diagnosed", "top": best[0]}}

    async def executor(self, state: IncidentState) -> dict:
        action = state["next_action"]
        step = state.get("step_count", 0) + 1
        already = any(c["tool"] == action["tool"] and c["args"] == action["args"] for c in state.get("actions_taken", []))
        if already:
            # Guardrail: duplicate calls are not executed but still consume budget.
            return {"last_observation": f"DUPLICATE CALL {fmt_call(action)} was not executed: its result is "
                                        "already in the evidence log. Choose a different check.",
                    "step_count": step}
        try:
            raw = await self.read_tools[action["tool"]].ainvoke(action["args"])
            observation = content_to_text(raw)
        except Exception as exc:  # tool errors become observations the planner can react to
            observation = f"TOOL ERROR: {exc}"
        return {"last_observation": observation, "step_count": step,
                "actions_taken": [{**action, "step": step}],
                "observations": [{"step": step, "call": fmt_call(action), "output": observation}]}

    async def hypothesis(self, state: IncidentState) -> dict:
        action = state["next_action"]
        if state["last_observation"].startswith("DUPLICATE CALL"):
            return {}
        u: HypothesisUpdate = await self.hypothesis_llm.ainvoke([
            SystemMessage(prompts.HYPOTHESIS_SYSTEM),
            HumanMessage(f"{investigation_context(state, exclude_latest_output=True)}\n\n"
                         f"=== LATEST TOOL OUTPUT (source: {TOOL_SOURCE[action['tool']]}; extract new evidence ONLY "
                         f"from this) ===\nCall: {fmt_call(action)}\n{state['last_observation']}\n=== END ==="),
        ])
        source = TOOL_SOURCE[action["tool"]]
        service = action["args"].get("service", "")

        def cap(labels: list[str]) -> list[str]:
            # An observation that "contradicts" most of the taxonomy carries no signal; keep the top 2.
            return [label for label in labels if label != "unknown"][:MAX_LABELS_PER_EVIDENCE]

        new_evidence: list[Evidence] = [
            {"source": source, "service": service, "observation": e.observation,
             "supports": cap(list(e.supports)), "contradicts": cap(list(e.contradicts)), "step": state["step_count"]}
            for e in u.new_evidence
        ]
        best: dict[str, Hypothesis] = {}
        for h in u.hypotheses:
            if h.label not in best or h.confidence > best[h.label]["confidence"]:
                best[h.label] = {"label": h.label, "confidence": h.confidence, "service": h.service}
        hypotheses = ranked(list(best.values()))
        return {"evidence": new_evidence, "hypotheses": hypotheses,
                "_trace": {"new_evidence": new_evidence, "hypotheses": hypotheses[:4]}}

    async def verifier(self, state: IncidentState) -> dict:
        out = await self._verify(state)
        rc = out.get("root_cause")
        out["_trace"] = {"decision": out.get("status", "continue"),
                         "feedback": out.get("verifier_feedback", ""),
                         "accepted": rc["label"] if rc else None}
        return out

    async def _verify(self, state: IncidentState) -> dict:
        at_budget = state.get("step_count", 0) >= self.max_steps
        if self.verification == "none":
            # Like ReAct: no gate. At the budget, commit to the best hypothesis instead of refusing.
            if not at_budget:
                return {"verifier_feedback": ""}
            best = ranked(state.get("hypotheses", []))
            if best and best[0]["label"] != "unknown":
                return {"status": "diagnosed", "root_cause": best[0], "verifier_feedback": "Step budget reached."}
            return {"status": "undetermined", "root_cause": None, "verifier_feedback": "Step budget reached."}

        v2 = self.verification.startswith("checklist")
        if v2:
            check = check_rules_v2(state.get("hypotheses", []), state.get("evidence", []), state.get("actions_taken", []))
        else:
            check = check_rules(state.get("hypotheses", []), state.get("evidence", []))
        if check.passed and self.verification in ("rules", "checklist"):
            return {"status": "diagnosed", "root_cause": check.top, "verifier_feedback": "Accepted by rules."}
        if check.passed:
            top = check.top
            review: SkepticReview = await self.skeptic_llm.ainvoke([
                SystemMessage(prompts.SKEPTIC_SYSTEM),
                HumanMessage(f"{investigation_context(state)}\n\nProposed root cause: {top['label']} "
                             f"(confidence {top['confidence']:.2f})"),
            ])
            objections = open_objections(
                [o.model_dump() for o in review.objections], state.get("actions_taken", []), top["label"]
            )
            # In checklist mode, "inspected directly" is already enforced in code by the checklist.
            inspected = True if v2 else review.inspected_directly
            if review.definition_match and inspected and not objections:
                return {"status": "diagnosed", "root_cause": top, "verifier_feedback": "Accepted by rules and reviewer."}
            gaps = []
            if not review.definition_match:
                gaps.append(f"evidence does not yet satisfy the definition of {top['label']}. {review.concern}")
            if not inspected:
                gaps.append(f"the faulty component has not been inspected directly. {review.concern}")
            for o in objections:
                gaps.append(f"rule out {o['alternative']} with {o['check_tool']}(service=\"{o['check_service']}\"): {o['why']}")
            feedback = f"Reviewer rejected {top['label']}: " + " | ".join(gaps)
        else:
            feedback = " ".join(check.reasons)

        if at_budget:
            return {"status": "undetermined", "root_cause": None, "verifier_feedback": feedback}
        return {"verifier_feedback": feedback}

    async def remediation(self, state: IncidentState) -> dict:
        rc = state["root_cause"]
        p: RemediationProposal = await self.remediation_llm.ainvoke([
            SystemMessage(prompts.REMEDIATION_SYSTEM),
            HumanMessage(f"Root cause: {rc['label']} (confidence {rc['confidence']:.2f})\n\n"
                         f"{investigation_context(state)}"),
        ])
        return {"remediation": p.model_dump()}

    def human_approval(self, state: IncidentState) -> dict:
        decision = interrupt({
            "root_cause": state["root_cause"],
            "proposal": state["remediation"],
            "evidence": state.get("evidence", []),
        })
        return {"approved": bool(decision)}

    async def apply_fix(self, state: IncidentState) -> dict:
        rem = state["remediation"]
        raw = await self.tools["apply_fix"].ainvoke({"service": rem["service"], "change": rem["action"]})
        return {"fix_result": content_to_text(raw)}

    def report(self, state: IncidentState) -> dict:
        return {"report": build_report(state)}

    # -- routing -------------------------------------------------------------

    @staticmethod
    def route_after_verifier(state: IncidentState) -> Literal["planner", "remediation", "report"]:
        status = state.get("status")
        if status == "diagnosed":
            return "remediation"
        if status == "undetermined":
            return "report"
        return "planner"

    @staticmethod
    def route_after_approval(state: IncidentState) -> Literal["apply_fix", "report"]:
        return "apply_fix" if state.get("approved") else "report"

    @staticmethod
    def route_after_planner(state: IncidentState) -> Literal["executor", "conclude"]:
        return "conclude" if state["next_action"]["tool"] == "conclude" else "executor"

    @staticmethod
    def route_after_conclude(state: IncidentState) -> Literal["remediation", "report"]:
        return "remediation" if state.get("status") == "diagnosed" else "report"

    # -- graph ---------------------------------------------------------------

    @staticmethod
    def _traced(name: str, fn):
        """Wrap a node so every call appends a trace entry (node, step, seconds, details)."""
        async def run(state: IncidentState) -> dict:
            start = time.time()
            out = fn(state)
            if inspect.isawaitable(out):
                out = await out
            out = dict(out or {})
            entry = {"node": name, "step": out.get("step_count", state.get("step_count", 0)),
                     "seconds": round(time.time() - start, 2), **out.pop("_trace", {})}
            out["trace"] = [entry]
            return out
        return run

    def build(self, checkpointer=None):
        g = StateGraph(IncidentState)
        for name in ("triage", "planner", "executor", "hypothesis", "verifier", "conclude",
                     "remediation", "human_approval", "apply_fix", "report"):
            g.add_node(name, self._traced(name, getattr(self, name)))
        g.add_edge(START, "triage")
        g.add_edge("triage", "planner")
        g.add_conditional_edges("planner", self.route_after_planner)
        g.add_conditional_edges("conclude", self.route_after_conclude)
        g.add_edge("executor", "hypothesis")
        g.add_edge("hypothesis", "verifier")
        g.add_conditional_edges("verifier", self.route_after_verifier)
        g.add_edge("remediation", "human_approval")
        g.add_conditional_edges("human_approval", self.route_after_approval)
        g.add_edge("apply_fix", "report")
        g.add_edge("report", END)
        # A checkpointer is required for interrupt()-based human approval.
        return g.compile(checkpointer=checkpointer or InMemorySaver())
