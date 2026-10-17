from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cause(str, Enum):
    configuration = "configuration_error"
    dependency = "dependency_unavailable"
    timeout = "dependency_timeout"
    database = "database_unavailable"
    regression = "application_regression"
    healthy = "healthy"
    unknown = "insufficient_evidence"


class Action(str, Enum):
    route = "restore_inventory_route"
    dependency = "restore_inventory_service"
    timeout = "restore_timeout_budget"
    database = "restore_catalog_path"
    rollback = "rollback_checkout_release"
    none = "no_action"


class Evidence(StrictModel):
    id: str
    source: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class Finding(StrictModel):
    cause: Cause
    title: str = Field(min_length=1, max_length=140)
    explanation: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(max_length=20)
    action: Action
    verification: str = Field(min_length=1, max_length=600)
    limitations: str = Field(min_length=1, max_length=1000)


class ToolTrace(StrictModel):
    tool: str
    arguments: dict[str, Any]
    evidence: list[Evidence]
    elapsed_ms: float
    error: str | None = None


class Investigation(StrictModel):
    mode: str
    finding: Finding
    traces: list[ToolTrace]
    elapsed_ms: float
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    cost_note: str = "Not available for this run."


class InjectRequest(StrictModel):
    scenario_id: str
    seed: int = Field(default=42, ge=0, le=1_000_000)


class InvestigateRequest(StrictModel):
    mode: Literal["baseline", "mistral", "prompt", "retrieval"] = "baseline"
    question: str = Field(
        default="Investigate checkout health. Identify the cause of any failure and propose an evidence-backed fix.",
        min_length=5, max_length=2000,
    )


class RemediateRequest(StrictModel):
    investigation_id: str = Field(min_length=1, max_length=64)
    action: Action


class ProbeRequest(StrictModel):
    count: int = Field(default=5, ge=1, le=20)

