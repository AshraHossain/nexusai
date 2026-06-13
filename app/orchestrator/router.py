"""
Workflow Router
Determines the next node in the LangGraph graph based on WorkflowState.
All conditional edges are pure functions — easy to test.
"""
from __future__ import annotations

from typing import Literal

from app.orchestrator.state import WorkflowState
from app.config import settings


# ── After Plan ────────────────────────────────────────────────────────────

def route_after_plan(
    state: WorkflowState,
) -> Literal["research", "coding", "end_error"]:
    """After planning, route to first step."""
    if state.get("error"):
        return "end_error"
    plan = state.get("plan", {})
    steps = plan.get("steps", [])
    if not steps:
        return "end_error"

    first_step = steps[0]
    agent = first_step.get("agent", "")
    if "research" in agent:
        return "research"
    if "coding" in agent:
        return "coding"
    return "research"  # default: always research first


# ── After Research ────────────────────────────────────────────────────────

def route_after_research(
    state: WorkflowState,
) -> Literal["coding", "qa", "security", "documentation", "evaluate", "end_error"]:
    """After research, route to next planned step."""
    if state.get("error"):
        return "end_error"
    return _next_step_agent(state, current="research")


# ── After Coding ──────────────────────────────────────────────────────────

def route_after_coding(
    state: WorkflowState,
) -> Literal["qa", "security", "documentation", "human_approval", "evaluate", "end_error"]:
    if state.get("error"):
        return "end_error"

    plan = state.get("plan", {})
    if plan.get("requires_approval"):
        return "human_approval"
    return _next_step_agent(state, current="coding")


# ── After QA ──────────────────────────────────────────────────────────────

def route_after_qa(
    state: WorkflowState,
) -> Literal["security", "documentation", "evaluate", "end_error"]:
    if state.get("error"):
        return "end_error"
    return _next_step_agent(state, current="qa")


# ── After Security ────────────────────────────────────────────────────────

def route_after_security(
    state: WorkflowState,
) -> Literal["documentation", "human_approval", "evaluate", "end_error", "end_blocked"]:
    if state.get("error"):
        return "end_error"

    # Block if risk score too high
    risk = state.get("sentinel_risk_score", 0)
    if risk > settings.sentinel_risk_threshold:
        return "end_blocked"

    security_passed = state.get("security_passed", True)
    if not security_passed:
        return "end_blocked"

    plan = state.get("plan", {})
    if plan.get("requires_approval"):
        return "human_approval"

    return _next_step_agent(state, current="security")


# ── After Human Approval ──────────────────────────────────────────────────

def route_after_approval(
    state: WorkflowState,
) -> Literal["evaluate", "end_rejected"]:
    status = state.get("approval_status", "pending")
    if status == "approved":
        return "evaluate"
    return "end_rejected"


# ── After Evaluate ────────────────────────────────────────────────────────

def route_after_evaluate(
    state: WorkflowState,
) -> Literal["documentation", "end_success", "end_quality_fail"]:
    if not state.get("eval_passed", False):
        return "end_quality_fail"

    # If no documentation yet, generate it
    if not state.get("documentation_output"):
        return "documentation"

    return "end_success"


# ── Helper ────────────────────────────────────────────────────────────────

_AGENT_ORDER = ["research", "coding", "qa", "security", "documentation", "evaluate"]


def _next_step_agent(state: WorkflowState, current: str) -> str:
    """
    Walk the planned steps to find what comes after current.
    Falls back to sequential default order if plan has no explicit next.
    """
    plan = state.get("plan", {})
    steps = plan.get("steps", [])
    step_index = state.get("current_step", 0)

    # Advance to the next planned step
    next_index = step_index + 1
    if next_index < len(steps):
        agent_key = steps[next_index].get("agent", "")
        for key in _AGENT_ORDER:
            if key in agent_key:
                return key

    # Default: evaluate when nothing left
    return "evaluate"
