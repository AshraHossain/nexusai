"""
Unit tests for app.models.workflow — request/response Pydantic models.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.workflow import (
    ApprovalDecisionRequest,
    WorkflowRunRequest,
    WorkflowRunResponse,
)


# ── WorkflowRunRequest ───────────────────────────────────────────────────────

def test_workflow_run_request_defaults():
    req = WorkflowRunRequest(request="Build a login page")
    assert req.workflow_type == "general"
    assert req.knowledge_collection == "default"
    assert req.preferred_language == "Python"
    assert req.created_by == "api"
    assert req.metadata == {}


def test_workflow_run_request_rejects_short_request():
    with pytest.raises(ValidationError):
        WorkflowRunRequest(request="hi")


def test_workflow_run_request_rejects_invalid_workflow_type():
    with pytest.raises(ValidationError):
        WorkflowRunRequest(request="Build a login page", workflow_type="not_a_type")


def test_workflow_run_request_accepts_known_types():
    for wt in ("general", "contract_review", "sdet"):
        req = WorkflowRunRequest(request="A valid request", workflow_type=wt)
        assert req.workflow_type == wt


# ── ApprovalDecisionRequest ──────────────────────────────────────────────────

def test_approval_decision_request_requires_reviewed_by():
    with pytest.raises(ValidationError):
        ApprovalDecisionRequest(status="approved")


def test_approval_decision_request_valid():
    req = ApprovalDecisionRequest(status="approved", reviewed_by="ash")
    assert req.notes == ""
    assert req.status == "approved"


def test_approval_decision_request_rejects_bad_status():
    with pytest.raises(ValidationError):
        ApprovalDecisionRequest(status="maybe", reviewed_by="ash")


# ── WorkflowRunResponse.from_state ──────────────────────────────────────────

def test_from_state_minimal():
    state = {"workflow_id": "wf-1", "status": "completed", "workflow_type": "general"}
    resp = WorkflowRunResponse.from_state(state)
    assert resp.workflow_id == "wf-1"
    assert resp.status == "completed"
    assert resp.evaluation is None
    assert resp.security is not None
    assert resp.security.passed is True
    assert resp.step_outputs == []


def test_from_state_with_steps_and_evaluation():
    state = {
        "workflow_id": "wf-2",
        "status": "completed",
        "workflow_type": "sdet",
        "final_output": "done",
        "step_outputs": [
            {"step": "research", "success": True, "tokens": 100, "latency_ms": 50},
            {"step": "coding", "success": True, "tokens": 200, "latency_ms": 150, "error": None},
        ],
        "eval_quality": 0.9,
        "eval_completeness": 0.8,
        "eval_groundedness": 0.95,
        "eval_passed": True,
        "sentinel_risk_score": 5,
        "sentinel_flags": ["pii"],
        "security_passed": True,
        "total_tokens": 300,
        "duration_ms": 1200,
    }
    resp = WorkflowRunResponse.from_state(state)
    assert len(resp.step_outputs) == 2
    assert resp.step_outputs[0].step == "research"
    assert resp.evaluation.quality == 0.9
    assert resp.evaluation.passed is True
    assert resp.security.risk_score == 5
    assert resp.security.flags == ["pii"]
    assert resp.total_tokens == 300


def test_from_state_with_error():
    state = {
        "workflow_id": "wf-3",
        "status": "failed",
        "workflow_type": "general",
        "error": "something broke",
    }
    resp = WorkflowRunResponse.from_state(state)
    assert resp.error == "something broke"
    assert resp.status == "failed"
