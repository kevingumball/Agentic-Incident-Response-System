"""Run one incident with either architecture and collect a uniform result."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable, Literal

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from agent import config
from agent.baseline_react import ReActAgent
from agent.graph import IncidentAgent, make_llm
from agent.mcp_client import connect

# Architecture name -> verification mode of IncidentAgent (None = ReAct baseline).
# Ablation ladder: react < plan_hyp < plan_hyp_rules < verifier (full phase-1 system).
ARCHITECTURES: dict[str, str | None] = {
    "react": None,
    "plan_hyp": "none",
    "plan_hyp_rules": "rules",
    "verifier": "rules+skeptic",
    # Phase 2 (driven by failure attribution): checklist + margin rule instead of LLM-confidence gates
    "plan_hyp_checklist": "checklist",
    "verifier_v2": "checklist+skeptic",
}
Architecture = Literal["react", "plan_hyp", "plan_hyp_rules", "verifier", "plan_hyp_checklist", "verifier_v2"]
EventHandler = Callable[[str, dict], None]
Approver = Callable[[dict], Awaitable[bool]]


async def auto_approve(_request: dict) -> bool:
    return True


@dataclass
class RunResult:
    case_id: str
    architecture: str
    model: str
    predicted: str = "unknown"
    confidence: float = 0.0
    status: str = "error"
    best_hypothesis: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    seconds: float = 0.0
    approved: bool | None = None
    remediation: dict | None = None
    evidence: list[dict] = field(default_factory=list)
    report: str | None = None
    trace: list[dict] = field(default_factory=list)
    suite: str = "v1"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def _run_graph_agent(ctx, llm, verification: str, result: RunResult, on_event: EventHandler | None,
                           approver: Approver) -> None:
    graph = IncidentAgent(ctx.tools, llm, verification=verification).build()
    cfg = {"configurable": {"thread_id": uuid.uuid4().hex}, "recursion_limit": 200}
    payload: Any = {"alert": ctx.alert}
    while True:
        pending = None
        async for chunk in graph.astream(payload, cfg, stream_mode="updates"):
            for node, update in chunk.items():
                if node == "__interrupt__":
                    pending = update[0].value
                elif on_event:
                    on_event(node, update or {})
        if pending is None:
            break
        payload = Command(resume=await approver(pending))

    state = (await graph.aget_state(cfg)).values
    result.status = state.get("status", "undetermined")
    rc = state.get("root_cause")
    hyps = state.get("hypotheses", [])
    result.best_hypothesis = hyps[0]["label"] if hyps else None
    if rc:
        result.predicted, result.confidence = rc["label"], rc["confidence"]
    else:
        result.predicted = "unknown"
        result.confidence = hyps[0]["confidence"] if hyps else 0.0
    result.tool_calls = [{"tool": c["tool"], "args": c["args"]} for c in state.get("actions_taken", [])]
    result.approved = state.get("approved")
    result.remediation = state.get("remediation")
    result.evidence = state.get("evidence", [])
    result.report = state.get("report")
    result.trace = state.get("trace", [])


async def _run_react(ctx, llm, result: RunResult, on_event: EventHandler | None) -> None:
    graph = ReActAgent(ctx.read_tools, llm).build()
    final: dict = {}
    start = time.time()
    async for chunk in graph.astream(
        {"messages": [HumanMessage(ctx.alert)]}, {"recursion_limit": 200}, stream_mode="updates"
    ):
        for node, update in chunk.items():
            if on_event:
                on_event(f"react:{node}", update or {})
            entry = {"node": node, "t": round(time.time() - start, 2)}
            if node == "agent":
                calls = [tc for m in update["messages"] if isinstance(m, AIMessage) for tc in m.tool_calls]
                entry["action"] = [f"{tc['name']}({tc['args']})" for tc in calls]
            elif node == "diagnose":
                entry["diagnosis"] = update["diagnosis"]
            result.trace.append(entry)
            if node == "diagnose":
                final = update["diagnosis"]
            elif node == "agent":
                for msg in update["messages"]:
                    if isinstance(msg, AIMessage):
                        result.tool_calls += [{"tool": tc["name"], "args": tc["args"]} for tc in msg.tool_calls]
    # Only count tool calls that were actually executed (budget may cut the last one).
    result.tool_calls = result.tool_calls[: config.MAX_STEPS]
    result.predicted = final.get("root_cause", "unknown")
    result.confidence = final.get("confidence", 0.0)
    result.best_hypothesis = result.predicted
    result.status = "diagnosed" if result.predicted != "unknown" else "undetermined"
    result.report = final.get("reasoning")


async def run_incident(
    case_id: str,
    architecture: Architecture = "verifier",
    *,
    model: str | None = None,
    on_event: EventHandler | None = None,
    approver: Approver = auto_approve,
    suite: str = "v1",
) -> RunResult:
    model = model or config.MODEL
    result = RunResult(case_id=case_id, architecture=architecture, model=model, suite=suite)
    llm = make_llm(model)
    start = time.time()
    try:
        with get_usage_metadata_callback() as usage:
            async with connect(case_id, suite) as ctx:
                verification = ARCHITECTURES[architecture]
                if verification is None:
                    await _run_react(ctx, llm, result, on_event)
                else:
                    await _run_graph_agent(ctx, llm, verification, result, on_event, approver)
        for model_name, u in usage.usage_metadata.items():
            result.input_tokens += u.get("input_tokens", 0)
            result.output_tokens += u.get("output_tokens", 0)
            result.model = model_name
        result.cost_usd = config.cost_usd(result.model, result.input_tokens, result.output_tokens)
    except Exception as exc:  # keep evaluation running; the failure is recorded
        while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
            exc = exc.exceptions[0]  # MCP's anyio task groups wrap the real error
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
    result.seconds = round(time.time() - start, 2)
    return result
