"""
WorkflowState - the shared state that flows through the LangGraph graph.
Every node reads from and writes into this TypedDict.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


class WorkflowState(TypedDict, total=False):
    # Identity
    workflow_id: str
    workflow_type: str          # general | contract_review | sdet | compliance_audit
    created_by: str

    # Input
    user_request: str
    knowledge_collection: str  # KnowledgeOps collection name
    preferred_language: str    # for CodingAgent

    # Plan
    plan: dict[str, Any]       # PlannerAgent structured output
    current_step: int
    current_task: str

    # Agent Outputs
    research_output: str
    research_citations: list[dict[str, Any]]
    coding_output: str
    architecture_output: str
    qa_output: str
    security_output: str
    security_passed: bool
    documentation_output: str

    # Security & Evaluation
    sentinel_risk_score: int
    sentinel_flags: list[str]
    eval_quality: float
    eval_completeness: float
    eval_groundedness: float
    eval_passed: bool

    # Human Approval
    requires_approval: bool
    approval_id: str
    approval_status: Literal["pending", "approved", "rejected", "expired"]
    approval_notes: str

    # Workflow Control
    status: Literal["running", "awaiting_approval", "completed", "failed"]
    error: str
    final_output: str
    step_outputs: list[dict[str, Any]]  # ordered list of all step results

    # Metrics
    total_tokens: int
    total_cost_usd: float
    duration_ms: int


def initial_state(
    workflow_id: str,
    user_request: str,
    workflow_type: str = "general",
    created_by: str = "api",
    **kwargs: Any,
) -> WorkflowState:
    """Create a fresh WorkflowState for a new workflow run."""
    return WorkflowState(
        workflow_id=workflow_id,
        workflow_type=workflow_type,
        created_by=created_by,
        user_request=user_request,
        current_step=0,
        requires_approval=False,
        approval_status="pending",
        status="running",
        step_outputs=[],
        total_tokens=0,
        total_cost_usd=0.0,
        security_passed=True,
        eval_passed=False,
        sentinel_flags=[],
        research_citations=[],
        **kwargs,
    )
