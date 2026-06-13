"""
API-level tests for the FastAPI app using TestClient.

`/ready` makes outbound httpx calls to integration platforms — these are
expected to fail (unreachable) in any environment where SentinelAI/EvalOps/
KnowledgeOps aren't running, so we assert on the "degraded" shape rather
than mocking them out.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.routes._store import workflow_store


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
    workflow_store.clear()


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "NexusAI"
    assert body["docs"] == "/docs"
    assert body["health"] == "/health"


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "NexusAI"
    assert "uptime_seconds" in body


def test_ready_reports_integration_status(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ready", "degraded")
    assert set(body["integrations"].keys()) == {"sentinelai", "evalops", "knowledgeops"}


def test_metrics_empty_store(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_workflows"] == 0
    assert body["by_status"] == {}
    assert body["total_tokens_used"] == 0
    assert body["avg_tokens_per_workflow"] == 0


def test_metrics_reflects_store_contents(client):
    workflow_store["wf-1"] = {"status": "completed", "total_tokens": 100}
    workflow_store["wf-2"] = {"status": "completed", "total_tokens": 50}
    workflow_store["wf-3"] = {"status": "failed", "total_tokens": 0}

    resp = client.get("/metrics")
    body = resp.json()
    assert body["total_workflows"] == 3
    assert body["by_status"] == {"completed": 2, "failed": 1}
    assert body["total_tokens_used"] == 150
    assert body["avg_tokens_per_workflow"] == 50


# ── /workflows ────────────────────────────────────────────────────────────

def test_get_workflow_not_found(client):
    resp = client.get("/workflows/does-not-exist")
    assert resp.status_code == 404


def test_get_workflow_found(client):
    workflow_store["wf-abc"] = {
        "workflow_id": "wf-abc",
        "status": "completed",
        "workflow_type": "general",
        "final_output": "hello",
    }
    resp = client.get("/workflows/wf-abc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow_id"] == "wf-abc"
    assert body["final_output"] == "hello"


def test_list_workflows(client):
    workflow_store["wf-1"] = {
        "workflow_id": "wf-1",
        "status": "completed",
        "workflow_type": "general",
        "total_tokens": 10,
        "duration_ms": 100,
    }
    workflow_store["wf-2"] = {
        "workflow_id": "wf-2",
        "status": "running",
        "workflow_type": "sdet",
        "total_tokens": 20,
        "duration_ms": 200,
    }
    resp = client.get("/workflows")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # newest first
    assert body[0]["workflow_id"] == "wf-2"


def test_run_workflow_validation_error(client):
    # "request" field has min_length=5
    resp = client.post("/workflows/run", json={"request": "hi"})
    assert resp.status_code == 422


# ── /approvals ────────────────────────────────────────────────────────────

def test_list_pending_approvals_empty(client):
    resp = client.get("/approvals/pending")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_pending_approvals_filters_by_status(client):
    workflow_store["wf-pending"] = {
        "workflow_id": "wf-pending",
        "workflow_type": "general",
        "status": "awaiting_approval",
        "approval_status": "pending",
        "current_step": 2,
        "plan": {"steps": []},
    }
    workflow_store["wf-done"] = {
        "workflow_id": "wf-done",
        "workflow_type": "general",
        "status": "completed",
        "approval_status": "approved",
    }
    resp = client.get("/approvals/pending")
    body = resp.json()
    assert len(body) == 1
    assert body[0]["workflow_id"] == "wf-pending"


def test_decide_approval_workflow_not_found(client):
    resp = client.post(
        "/approvals/missing-wf/decide",
        json={"status": "approved", "reviewed_by": "ash"},
    )
    assert resp.status_code == 404


def test_decide_approval_not_awaiting(client):
    workflow_store["wf-not-pending"] = {
        "workflow_id": "wf-not-pending",
        "workflow_type": "general",
        "status": "completed",
        "approval_status": "approved",
    }
    resp = client.post(
        "/approvals/wf-not-pending/decide",
        json={"status": "approved", "reviewed_by": "ash"},
    )
    assert resp.status_code == 409
