"""Structured investigation state.

Unlike a plain MessagesState (chat history), the investigation progress lives in
explicit fields; each node reads and writes only the fields it owns.
"""

import operator
from typing import Annotated, Literal, TypedDict

EvidenceSource = Literal["metrics", "logs", "traces", "config"]

TOOL_SOURCE: dict[str, EvidenceSource] = {
    "get_service_metrics": "metrics",
    "search_logs": "logs",
    "get_trace": "traces",
    "get_service_config": "config",
}


class Evidence(TypedDict):
    source: EvidenceSource
    service: str
    observation: str
    supports: list[str]      # hypothesis labels this evidence supports
    contradicts: list[str]   # hypothesis labels this evidence argues against
    step: int


class Hypothesis(TypedDict):
    label: str               # taxonomy label or "unknown"
    confidence: float


class ToolCall(TypedDict):
    tool: str
    args: dict
    reason: str
    step: int


class Observation(TypedDict):
    step: int
    call: str
    output: str


class IncidentState(TypedDict, total=False):
    alert: str
    service: str
    symptoms: list[str]
    severity: str
    evidence: Annotated[list[Evidence], operator.add]
    hypotheses: list[Hypothesis]
    actions_taken: Annotated[list[ToolCall], operator.add]
    observations: Annotated[list[Observation], operator.add]   # raw tool outputs (full history)
    next_action: ToolCall | None
    last_observation: str
    verifier_feedback: str
    step_count: int
    status: Literal["investigating", "diagnosed", "undetermined"]
    root_cause: Hypothesis | None
    remediation: dict | None
    approved: bool | None
    fix_result: str | None
    report: str
