"""
Unit tests for app.orchestrator.router — pure routing functions.
"""
from __future__ import annotations

import pytest

from app.orchestrator import router as r
from app.orchestrator.state import initial_state


def _state(**overrides):
    state = initial_state(workflow_id="wf-1", user_request="do something")
    state.update(overrides)
    return state


# ── route_after_plan ────────────────────────────────────────────────────────

def test_route_after_plan_error_goes_to_end_error():
    state = _state(error="boom")
    assert r.route_after_plan(state) == "end_error"


def test_route_after_plan_no_steps_goes_to_end_error():
    state = _state(plan={"steps": []})
    assert r.route_after_plan(state) == "end_error"


def test_route_after_plan_research_first():
    state = _state(plan={"steps": [{"agent": "research_agent"}]})
    assert r.route_after_plan(state) == "research"


def test_route_after_plan_coding_first():
    state = _state(plan={"steps": [{"agent": "coding_agent"}]})
    assert r.route_after_plan(state) == "coding"


def test_route_after_plan_unknown_agent_defaults_research():
    state = _state(plan={"steps": [{"agent": "mystery_agent"}]})
    assert r.route_after_plan(state) == "research"


# ── route_after_research / coding / qa ──────────────────────────────────────

def test_route_after_research_error():
    state = _state(error="boom")
    assert r.route_after_research(state) == "end_error"


def test_route_after_research_advances_to_next_planned_step():
    plan = {"steps": [{"agent": "research_agent"}, {"agent": "coding_agent"}]}
    state = _state(plan=plan, current_step=0)
    assert r.route_after_research(state) == "coding"


def test_route_after_research_no_more_steps_goes_to_evaluate():
    plan = {"steps": [{"agent": "research_agent"}]}
    state = _state(plan=plan, current_step=0)
    assert r.route_after_research(state) == "evaluate"


def test_route_after_coding_requires_approval():
    state = _state(plan={"steps": [{"agent": "coding"}], "requires_approval": True})
    assert r.route_after_coding(state) == "human_approval"


def test_route_after_coding_error():
    state = _state(error="boom")
    assert r.route_after_coding(state) == "end_error"


def test_route_after_qa_advances():
    plan = {"steps": [{"agent": "qa_agent"}, {"agent": "security_agent"}]}
    state = _state(plan=plan, current_step=0)
    assert r.route_after_qa(state) == "security"


# ── route_after_security ─────────────────────────────────────────────────────

def test_route_after_security_blocks_on_high_risk():
    state = _state(sentinel_risk_score=99)
    assert r.route_after_security(state) == "end_blocked"


def test_route_after_security_blocks_on_failed_check():
    state = _state(security_passed=False)
    assert r.route_after_security(state) == "end_blocked"


def test_route_after_security_requires_approval():
    state = _state(plan={"requires_approval": True}, sentinel_risk_score=0, security_passed=True)
    assert r.route_after_security(state) == "human_approval"


def test_route_after_security_error():
    state = _state(error="boom")
    assert r.route_after_security(state) == "end_error"


def test_route_after_security_passes_to_evaluate_by_default():
    state = _state(sentinel_risk_score=0, security_passed=True)
    assert r.route_after_security(state) == "evaluate"


# ── route_after_approval ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "status,expected",
    [
        ("approved", "evaluate"),
        ("rejected", "end_rejected"),
        ("pending", "end_rejected"),
        ("expired", "end_rejected"),
    ],
)
def test_route_after_approval(status, expected):
    state = _state(approval_status=status)
    assert r.route_after_approval(state) == expected


# ── route_after_evaluate ──────────────────────────────────────────────────────

def test_route_after_evaluate_quality_fail():
    state = _state(eval_passed=False)
    assert r.route_after_evaluate(state) == "end_quality_fail"


def test_route_after_evaluate_generates_documentation_when_missing():
    state = _state(eval_passed=True)
    assert r.route_after_evaluate(state) == "documentation"


def test_route_after_evaluate_success_when_documentation_present():
    state = _state(eval_passed=True, documentation_output="docs here")
    assert r.route_after_evaluate(state) == "end_success"


# ── _next_step_agent ──────────────────────────────────────────────────────────

def test_next_step_agent_falls_back_to_evaluate_when_plan_empty():
    state = _state(plan={}, current_step=0)
    assert r._next_step_agent(state, current="research") == "evaluate"


def test_next_step_agent_skips_to_matching_agent_order():
    plan = {"steps": [{"agent": "research_agent"}, {"agent": "documentation_agent"}]}
    state = _state(plan=plan, current_step=0)
    assert r._next_step_agent(state, current="research") == "documentation"
