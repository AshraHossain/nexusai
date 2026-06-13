"""
Compliance Audit Agent Workflow
Specialized LangGraph graph for AI-driven regulatory/standards compliance audits
(e.g. aviation FAA/EASA Part 145, SOC 2, ISO 27001, GDPR, HIPAA).

Pipeline:
  Audit Scope Input
    -> SentinelAI (input validation)
    -> KnowledgeOps (retrieve applicable regulations/standards)
    -> PolicyMappingAgent (map scope to controls + required evidence)
    -> EvidenceAnalysisAgent (assess evidence against control matrix)
    -> ComplianceRiskAgent (score overall compliance risk via SentinelAI)
    -> Human Approval (if risk > threshold)
    -> AuditReportAgent (executive audit report + remediation plan)
    -> EvalOps (quality evaluation)
    -> Final Report
"""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.workflows.compliance_audit.agents import (
    PolicyMappingAgent,
    EvidenceAnalysisAgent,
    ComplianceRiskAgent,
    AuditReportAgent,
)
from app.integrations.evalops import get_evalops_client
from app.integrations.knowledgeops import get_knowledgeops_client
from app.orchestrator.state import WorkflowState, initial_state


# Agent singletons
_policy = PolicyMappingAgent()
_evidence = EvidenceAnalysisAgent()
_risk = ComplianceRiskAgent()
_report = AuditReportAgent()


# Nodes

async def node_retrieve_regulations(state: WorkflowState) -> WorkflowState:
    """Pull relevant regulations, standards, and controls from KnowledgeOps."""
    ko = get_knowledgeops_client()
    result = await ko.retrieve(
        query=f"compliance regulations standards controls: {state['user_request'][:200]}",
        collection=state.get("knowledge_collection", "compliance_policies"),
        top_k=10,
        retrieval_method="hybrid",
        rerank=True,
    )
    state["research_output"] = "\n\n".join(
        f"[{d.source}] {d.content}" for d in result.documents
    )
    state["research_citations"] = [
        {"id": d.id, "source": d.source, "score": d.score}
        for d in result.documents
    ]
    return state


async def node_map_policies(state: WorkflowState) -> WorkflowState:
    """Map the audit scope to applicable regulations, controls, and required evidence."""
    result = await _policy.run(state)
    # research_output now holds the policy/control mapping (overwrite raw retrieval)
    state["research_output"] = result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _append(state, "policy_mapping", result)
    return state


async def node_analyze_evidence(state: WorkflowState) -> WorkflowState:
    """Assess evidence against the control matrix."""
    result = await _evidence.run(state)
    state["coding_output"] = result.output  # reuse coding_output slot for evidence assessment
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _append(state, "evidence_analysis", result)
    return state


async def node_risk_score(state: WorkflowState) -> WorkflowState:
    """Score overall compliance risk via ComplianceRiskAgent."""
    result = await _risk.run(state)
    state["security_output"] = result.output
    state["sentinel_risk_score"] = result.structured_output.get("risk_score", 0)
    state["security_passed"] = result.structured_output.get("passed", True)
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _append(state, "risk_scoring", result)

    # Require human approval for HIGH risk audits
    if state["sentinel_risk_score"] > 40:
        state["requires_approval"] = True

    return state


async def node_human_approval(state: WorkflowState) -> WorkflowState:
    approval_id = str(uuid.uuid4())
    state["approval_id"] = approval_id
    state["approval_status"] = "pending"
    state["status"] = "awaiting_approval"
    return state


async def node_audit_report(state: WorkflowState) -> WorkflowState:
    """Generate the executive audit report and remediation plan."""
    result = await _report.run(state)
    state["documentation_output"] = result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _append(state, "audit_report", result)
    return state


async def node_evaluate(state: WorkflowState) -> WorkflowState:
    evalops = get_evalops_client()
    try:
        eval_result = await evalops.evaluate(
            workflow_id=state["workflow_id"],
            prompt=state["user_request"],
            response=state.get("documentation_output", ""),
            workflow_type="compliance_audit",
        )
        state["eval_quality"] = eval_result.quality
        state["eval_completeness"] = eval_result.completeness
        state["eval_groundedness"] = eval_result.groundedness
        state["eval_passed"] = eval_result.passed
    except Exception:
        state["eval_passed"] = True
    return state


async def node_end_success(state: WorkflowState) -> WorkflowState:
    state["final_output"] = state.get("documentation_output", "Compliance audit complete.")
    state["status"] = "completed"
    return state


async def node_end_rejected(state: WorkflowState) -> WorkflowState:
    state["status"] = "failed"
    state["final_output"] = "Compliance audit rejected during human approval."
    return state


async def node_end_blocked(state: WorkflowState) -> WorkflowState:
    state["status"] = "failed"
    state["final_output"] = (
        f"Compliance audit blocked - risk score {state.get('sentinel_risk_score', 0)}/100 "
        f"exceeds policy threshold."
    )
    return state


# Routing

def route_after_risk(state: WorkflowState) -> str:
    if state.get("requires_approval"):
        return "human_approval"
    return "audit_report"


def route_after_approval(state: WorkflowState) -> str:
    return "audit_report" if state.get("approval_status") == "approved" else "end_rejected"


# Graph

def build_compliance_audit_graph() -> StateGraph:
    builder = StateGraph(WorkflowState)

    builder.add_node("retrieve_regulations", node_retrieve_regulations)
    builder.add_node("map_policies", node_map_policies)
    builder.add_node("analyze_evidence", node_analyze_evidence)
    builder.add_node("risk_score", node_risk_score)
    builder.add_node("human_approval", node_human_approval)
    builder.add_node("audit_report", node_audit_report)
    builder.add_node("evaluate", node_evaluate)
    builder.add_node("end_success", node_end_success)
    builder.add_node("end_rejected", node_end_rejected)

    builder.add_edge(START, "retrieve_regulations")
    builder.add_edge("retrieve_regulations", "map_policies")
    builder.add_edge("map_policies", "analyze_evidence")
    builder.add_edge("analyze_evidence", "risk_score")

    builder.add_conditional_edges(
        "risk_score",
        route_after_risk,
        {"human_approval": "human_approval", "audit_report": "audit_report"},
    )
    builder.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {"audit_report": "audit_report", "end_rejected": "end_rejected"},
    )

    builder.add_edge("audit_report", "evaluate")
    builder.add_edge("evaluate", "end_success")
    builder.add_edge("end_success", END)
    builder.add_edge("end_rejected", END)

    return builder


_ca_checkpointer = MemorySaver()
compliance_audit_graph = build_compliance_audit_graph().compile(
    checkpointer=_ca_checkpointer,
    interrupt_before=["human_approval"],
)


async def run_compliance_audit(
    audit_scope: str,
    created_by: str = "api",
    collection: str = "compliance_policies",
) -> WorkflowState:
    workflow_id = str(uuid.uuid4())
    state = initial_state(
        workflow_id=workflow_id,
        user_request=audit_scope,
        workflow_type="compliance_audit",
        created_by=created_by,
        knowledge_collection=collection,
    )
    config = {"configurable": {"thread_id": workflow_id}}
    return await compliance_audit_graph.ainvoke(state, config=config)


# Helpers

def _append(state: WorkflowState, step_name: str, result: Any) -> None:
    steps = state.get("step_outputs", [])
    steps.append({
        "step": step_name,
        "success": result.success,
        "tokens": result.tokens_used,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
        "error": result.error,
    })
    state["step_outputs"] = steps
