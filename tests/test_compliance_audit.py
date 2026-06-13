"""
End-to-end tests for the Compliance Audit Agent workflow
(app.workflows.compliance_audit), with all external integrations and the
LLM provider mocked out.
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from app.integrations.evalops import EvaluationResult
from app.integrations.knowledgeops import Document, RetrievalResult
from app.integrations.sentinelai import ValidationResult
from app.workflows.compliance_audit import graph as ca_graph


# ── Fakes ─────────────────────────────────────────────────────────────────

class _FakeChatModel:
    """Returns canned responses in order, one per ainvoke() call."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    async def ainvoke(self, messages):
        idx = min(self.calls, len(self._responses) - 1)
        content = self._responses[idx]
        self.calls += 1
        return AIMessage(
            content=content,
            usage_metadata={"input_tokens": 100, "output_tokens": 100, "total_tokens": 200},
        )


class _FakeLLMProvider:
    def __init__(self, chat_model: _FakeChatModel, model_name: str = "gpt-4o-mini"):
        self._chat_model = chat_model
        self._model_name = model_name

    def get_chat_model(self, **kwargs):
        return self._chat_model

    def get_model_name(self, **kwargs) -> str:
        return self._model_name


class _FakeSentinel:
    async def validate_input(self, prompt, context=None, workflow_id=None):
        return ValidationResult(passed=True)

    async def validate_output(self, output, context=None, workflow_id=None):
        return ValidationResult(passed=True)


class _FakeKnowledgeOps:
    async def retrieve(self, query, collection, top_k=10, retrieval_method="hybrid", rerank=True):
        return RetrievalResult(
            documents=[
                Document(
                    id="doc-1",
                    content="FAA Part 145 requires documented quality control procedures.",
                    score=0.9,
                    source="FAA Part 145",
                ),
            ],
            query=query,
            total_found=1,
            retrieval_method=retrieval_method,
        )


class _FakeEvalOps:
    def __init__(self, quality: float = 0.95, groundedness: float = 0.95):
        self._quality = quality
        self._groundedness = groundedness

    async def evaluate(self, workflow_id, prompt, response, workflow_type="general", **kwargs):
        return EvaluationResult(
            quality=self._quality,
            completeness=0.9,
            groundedness=self._groundedness,
        )


# ── Fixtures ─────────────────────────────────────────────────────────────

RISK_JSON_LOW = """
Compliance posture looks reasonable overall.

```json
{
  "risk_score": 25,
  "risk_level": "MEDIUM",
  "critical_findings": 0,
  "major_findings": 1,
  "minor_findings": 2,
  "recommendation": "conditional_pass",
  "top_findings": ["Missing document retention policy"]
}
```
"""

RISK_JSON_HIGH = """
Significant gaps identified across multiple controls.

```json
{
  "risk_score": 65,
  "risk_level": "HIGH",
  "critical_findings": 1,
  "major_findings": 3,
  "minor_findings": 1,
  "recommendation": "remediate_before_certification",
  "top_findings": ["No documented incident response plan"]
}
```
"""


def _patch_agents(monkeypatch, responses: list[str]):
    """Patch the module-level agent singletons' LLM + sentinel clients."""
    chat_model = _FakeChatModel(responses)
    provider = _FakeLLMProvider(chat_model)
    sentinel = _FakeSentinel()

    for agent in (ca_graph._policy, ca_graph._evidence, ca_graph._risk, ca_graph._report):
        monkeypatch.setattr(agent, "_llm", provider)
        monkeypatch.setattr(agent, "_sentinel", sentinel)

    return chat_model


# ── Tests ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compliance_audit_low_risk_completes(monkeypatch):
    _patch_agents(
        monkeypatch,
        responses=[
            "## Audit Scope Summary\nMapped to FAA Part 145.",   # policy mapping
            "## Evidence Assessment\nCTL-001: Partially Met.",    # evidence analysis
            RISK_JSON_LOW,                                        # risk scoring
            "# Compliance Audit Report\nOverall low risk.",       # audit report
        ],
    )
    monkeypatch.setattr(ca_graph, "get_knowledgeops_client", lambda: _FakeKnowledgeOps())
    monkeypatch.setattr(ca_graph, "get_evalops_client", lambda: _FakeEvalOps())

    final_state = await ca_graph.run_compliance_audit(
        audit_scope="Audit our maintenance records program against FAA Part 145.",
        created_by="tester",
    )

    assert final_state["status"] == "completed"
    assert final_state["workflow_type"] == "compliance_audit"
    assert "Compliance Audit Report" in final_state["final_output"]
    assert final_state["sentinel_risk_score"] == 25
    assert final_state["security_passed"] is True
    assert final_state.get("requires_approval", False) is False

    step_names = [s["step"] for s in final_state["step_outputs"]]
    assert step_names == ["policy_mapping", "evidence_analysis", "risk_scoring", "audit_report"]
    assert all(s["cost_usd"] >= 0 for s in final_state["step_outputs"])
    assert final_state["total_cost_usd"] > 0
    assert final_state["total_tokens"] == 200 * 4


@pytest.mark.asyncio
async def test_compliance_audit_high_risk_requires_approval(monkeypatch):
    _patch_agents(
        monkeypatch,
        responses=[
            "## Audit Scope Summary\nMapped to FAA Part 145.",
            "## Evidence Assessment\nMultiple controls Not Met.",
            RISK_JSON_HIGH,
            "# Compliance Audit Report\nOverall high risk.",
        ],
    )
    monkeypatch.setattr(ca_graph, "get_knowledgeops_client", lambda: _FakeKnowledgeOps())
    monkeypatch.setattr(ca_graph, "get_evalops_client", lambda: _FakeEvalOps())

    final_state = await ca_graph.run_compliance_audit(
        audit_scope="Audit our incident response program.",
        created_by="tester",
    )

    # High risk score (65) triggers human approval, which is interrupted
    # before execution by the checkpointer (interrupt_before=["human_approval"]).
    assert final_state["sentinel_risk_score"] == 65
    # risk_score 65 < 70 still counts as "passed" per ComplianceRiskAgent,
    assert final_state["security_passed"] is True
    assert final_state.get("requires_approval") is True
    # The graph is interrupted before node_human_approval runs, so status
    # remains "running" (node_human_approval is what sets "awaiting_approval").
    assert final_state["status"] == "running"
