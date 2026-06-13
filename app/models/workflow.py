"""
Pydantic request/response models for the NexusAI API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# Requests

class WorkflowRunRequest(BaseModel):
    request: str = Field(..., description="The user's task or question", min_length=5)
    workflow_type: Literal["general", "contract_review", "sdet", "compliance_audit"] = "general"
    knowledge_collection: str = "default"
    preferred_language: str = "Python"
    created_by: str = "api"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    status: Literal["approved", "rejected"]
    notes: str = ""
    reviewed_by: str


# Responses

class StepSummary(BaseModel):
    step: str
    success: bool
    tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    error: Optional[str] = None


class EvalSummary(BaseModel):
    quality: float = 0.0
    completeness: float = 0.0
    groundedness: float = 0.0
    passed: bool = False


class SecuritySummary(BaseModel):
    risk_score: int = 0
    flags: list[str] = []
    passed: bool = True


class WorkflowRunResponse(BaseModel):
    workflow_id: str
    status: str
    workflow_type: str
    final_output: str = ""
    step_outputs: list[StepSummary] = []
    evaluation: Optional[EvalSummary] = None
    security: Optional[SecuritySummary] = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    duration_ms: int = 0
    error: Optional[str] = None
    approval_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "WorkflowRunResponse":
        steps = [StepSummary(**s) for s in state.get("step_outputs", [])]
        eval_s = None
        if state.get("eval_quality") is not None:
            eval_s = EvalSummary(
                quality=state.get("eval_quality", 0.0),
                completeness=state.get("eval_completeness", 0.0),
                groundedness=state.get("eval_groundedness", 0.0),
                passed=state.get("eval_passed", False),
            )
        sec_s = SecuritySummary(
            risk_score=state.get("sentinel_risk_score", 0),
            flags=state.get("sentinel_flags", []),
            passed=state.get("security_passed", True),
        )
        return cls(
            workflow_id=state["workflow_id"],
            status=state.get("status", "unknown"),
            workflow_type=state.get("workflow_type", "general"),
            final_output=state.get("final_output", ""),
            step_outputs=steps,
            evaluation=eval_s,
            security=sec_s,
            total_tokens=state.get("total_tokens", 0),
            total_cost_usd=state.get("total_cost_usd", 0.0),
            duration_ms=state.get("duration_ms", 0),
            error=state.get("error"),
            approval_id=state.get("approval_id"),
        )


class WorkflowListItem(BaseModel):
    workflow_id: str
    status: str
    workflow_type: str
    total_tokens: int
    total_cost_usd: float = 0.0
    duration_ms: int
    created_at: datetime
