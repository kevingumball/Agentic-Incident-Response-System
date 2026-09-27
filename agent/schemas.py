"""Pydantic schemas for every structured LLM output."""

from typing import Literal

from pydantic import BaseModel, Field

from agent.taxonomy import RootCauseLabel

ReadTool = Literal["get_service_metrics", "search_logs", "get_trace", "get_service_config"]


class TriageResult(BaseModel):
    service: str = Field(description="The service the alert fired on")
    symptoms: list[str] = Field(description="Short factual symptoms taken from the alert")
    severity: Literal["low", "medium", "high", "critical"]


class PlannerDecision(BaseModel):
    reasoning: str = Field(description="Why this is the most informative next check (1-2 sentences)")
    tool: ReadTool
    service: str = Field(description="Target service name")
    metric: str = Field(default="", description="Only for get_service_metrics: metric name, or empty for all metrics")
    query: str = Field(default="", description="Only for search_logs: keywords, or empty for all logs")


class PlannerDecisionOrConclude(PlannerDecision):
    """Planner for the no-verifier ablation: it may also decide the investigation is finished."""
    tool: Literal["get_service_metrics", "search_logs", "get_trace", "get_service_config", "conclude"]


class EvidenceItem(BaseModel):
    observation: str = Field(description="One factual sentence with concrete numbers from the tool output")
    supports: list[RootCauseLabel] = Field(description="Root causes this observation makes MORE likely")
    contradicts: list[RootCauseLabel] = Field(description="Root causes this observation makes LESS likely")


class RankedHypothesis(BaseModel):
    label: RootCauseLabel
    confidence: float = Field(ge=0.0, le=1.0)
    service: str = Field(default="", description="Service where this fault is located (e.g. inventory, orders-db); "
                                                "empty if unclear")


class HypothesisUpdate(BaseModel):
    new_evidence: list[EvidenceItem] = Field(
        description="0-3 diagnostically relevant observations from the latest tool output"
    )
    hypotheses: list[RankedHypothesis] = Field(
        description="All plausible root causes ranked by confidence (highest first)"
    )


class Objection(BaseModel):
    alternative: RootCauseLabel = Field(description="Competing label that is still consistent with all evidence")
    # A plain string: an invented tool name should drop this objection, not crash the run (DEVLOG 10.4).
    check_tool: str = Field(description="One of get_service_metrics / search_logs / get_trace / get_service_config")
    check_service: str = Field(description="Service to run that tool on")
    why: str = Field(description="What result would rule the alternative in or out")


class SkepticReview(BaseModel):
    definition_match: bool = Field(description="Evidence satisfies the proposed label's taxonomy definition")
    inspected_directly: bool = Field(description="The faulty component itself was examined")
    objections: list[Objection] = Field(
        description="Only alternatives that a NOT-YET-RUN check (tool + service) could discriminate; empty if none"
    )
    concern: str = Field(default="", description="If definition or inspection fails: what is missing")


class RemediationProposal(BaseModel):
    service: str = Field(description="Service to change")
    action: str = Field(description="One-line concrete change, e.g. 'DB_POOL_SIZE: 20 -> 40'")
    steps: list[str] = Field(description="Ordered remediation and follow-up steps")
    risk: Literal["low", "medium", "high"]


class Diagnosis(BaseModel):
    """Final output format shared by all architectures."""
    reasoning: str
    root_cause: RootCauseLabel
    confidence: float = Field(ge=0.0, le=1.0)
