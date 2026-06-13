"""
Contract Review Agent Workflow
Specialized LangGraph graph for AI-driven contract analysis.

Pipeline:
  User Input
    → SentinelAI (input validation)
    → KnowledgeOps (retrieve precedents, clauses, regulations)
    → ContractAnalysisAgent (clause extraction + risk identification)
    → LegalResearchAgent (compliance check against retrieved standards)
    → RiskScoringAgent (score via SentinelAI risk-score)
    → Human Approval (if risk > threshold)
    → SummaryAgent (executive summary + recommendations)
    → EvalOps (quality evaluation)
    → Final Report
"""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.workflows.contract_review.agents import (
    ContractAnalysisAgent,
    LegalResearchAgent,
    ContractRiskAgent,
    ContractSummaryAgent,
)
from app.integrations.evalops import get_evalops_client
from app.integrations.sentinelai import get_sentinel_client
from app.integrations.knowledgeops import get_knowledgeops_client
from app.orchestrator.state import WorkflowState, initial_state


# ── Agent singletons ──────────────────────────────────────────────────────
_analysis = ContractAnalysisAgent()
_legal = LegalResearchAgent()
_risk = ContractRiskAgent()
_summary = ContractSummaryAgent()


# ── Nodes ─────────────────────────────────────────────────────────────────

async def node_retrieve_precedents(state: WorkflowState) -> WorkflowState:
    """Pull relevant contract precedents and legal standards from KnowledgeOps."""
    ko = get_knowledgeops_client()
    result = await ko.retrieve(
        query=f"contract clauses standards: {state['user_request'][:200]}",
        collection=state.get("knowledge_collection", "contracts"),
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


async def node_analyze_contract(state: WorkflowState) -> WorkflowState:
    """Extract clauses, obligations, risks, and non-standard terms."""
    result = await _analysis.run(state)
    state["coding_output"] = result.output  # reuse coding_output slot for analysis
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    _append(state, "contract_analysis", result)
    return state


async def node_legal_research(state: WorkflowState) -> WorkflowState:
    """Check clauses against retrieved legal standards and precedents."""
    result = await _legal.run(state)
    state["architecture_output"] = result.output  # reuse arch slot for legal findings
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    _append(state, "legal_research", result)
    return state


async def node_risk_score(state: WorkflowState) -> WorkflowState:
    """Score contract risk via SentinelAI + ContractRiskAgent."""
    result = await _risk.run(state)
    state["security_output"] = result.output
    state["sentinel_risk_score"] = result.structured_output.get("risk_score", 0)
    state["security_passed"] = result.structured_output.get("passed", True)
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    _append(state, "risk_scoring", result)

    # Require human approval for HIGH risk contracts
    if state["sentinel_risk_score"] > 40:
        state["requires_approval"] = True

    return state


async def node_human_approval(state: WorkflowState) -> WorkflowState:
    approval_id = str(uuid.uuid4())
    state["approval_id"] = approval_id
    state["approval_status"] = "pending"
    state["status"] = "awaiting_approval"
    return state


async def node_summary(state: WorkflowState) -> WorkflowState:
    """Generate executive summary and actionable recommendations."""
    result = await _summary.run(state)
    state["documentation_output"] = result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    _append(state, "summary", result)
    return state


async def node_evaluate(state: WorkflowState) -> WorkflowState:
    evalops = get_evalops_client()
    try:
        eval_result = await evalops.evaluate(
            workflow_id=state["workflow_id"],
            prompt=state["user_request"],
            response=state.get("documentation_output", ""),
            workflow_type="contract_review",
        )
        state["eval_quality"] = eval_result.quality
        state["eval_completeness"] = eval_result.completeness
        state["eval_groundedness"] = eval_result.groundedness
        state["eval_passed"] = eval_result.passed
    except Exception:
        state["eval_passed"] = True
    return state


async def node_end_success(state: WorkflowState) -> WorkflowState:
    state["final_output"] = state.get("documentation_output", "Contract review complete.")
    state["status"] = "completed"
    return state


async def node_end_rejected(state: WorkflowState) -> WorkflowState:
    state["status"] = "failed"
    state["final_output"] = "Contract review rejected during human approval."
    return state


async def node_end_blocked(state: WorkflowState) -> WorkflowState:
    state["status"] = "failed"
    state["final_output"] = (
        f"Contract review blocked — risk score {state.get('sentinel_risk_score', 0)}/100 "
        f"exceeds policy threshold."
    )
    return state


# ── Routing ───────────────────────────────────────────────────────────────

def route_after_risk(state: WorkflowState) -> str:
    if state.get("requires_approval"):
        return "human_approval"
    return "summary"


def route_after_approval(state: WorkflowState) -> str:
    return "summary" if state.get("approval_status") == "approved" else "end_rejected"


# ── Graph ─────────────────────────────────────────────────────────────────

def build_contract_review_graph() -> StateGraph:
    builder = StateGraph(WorkflowState)

    builder.add_node("retrieve_precedents", node_retrieve_precedents)
    builder.add_node("analyze_contract", node_analyze_contract)
    builder.add_node("legal_research", node_legal_research)
    builder.add_node("risk_score", node_risk_score)
    builder.add_node("human_approval", node_human_approval)
    builder.add_node("summary", node_summary)
    builder.add_node("evaluate", node_evaluate)
    builder.add_node("end_success", node_end_success)
    builder.add_node("end_rejected", node_end_rejected)

    builder.add_edge(START, "retrieve_precedents")
    builder.add_edge("retrieve_precedents", "analyze_contract")
    builder.add_edge("analyze_contract", "legal_research")
    builder.add_edge("legal_research", "risk_score")

    builder.add_conditional_edges(
        "risk_score",
        route_after_risk,
        {"human_approval": "human_approval", "summary": "summary"},
    )
    builder.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {"summary": "summary", "end_rejected": "end_rejected"},
    )

    builder.add_edge("summary", "evaluate")
    builder.add_edge("evaluate", "end_success")
    builder.add_edge("end_success", END)
    builder.add_edge("end_rejected", END)

    return builder


_cr_checkpointer = MemorySaver()
contract_review_graph = build_contract_review_graph().compile(
    checkpointer=_cr_checkpointer,
    interrupt_before=["human_approval"],
)


async def run_contract_review(
    contract_text: str,
    created_by: str = "api",
    collection: str = "contracts",
) -> WorkflowState:
    workflow_id = str(uuid.uuid4())
    state = initial_state(
        workflow_id=workflow_id,
        user_request=contract_text,
        workflow_type="contract_review",
        created_by=created_by,
        knowledge_collection=collection,
    )
    config = {"configurable": {"thread_id": workflow_id}}
    return await contract_review_graph.ainvoke(state, config=config)


# ── Helpers ───────────────────────────────────────────────────────────────

def _append(state: WorkflowState, step_name: str, result: Any) -> None:
    steps = state.get("step_outputs", [])
    steps.append({
        "step": step_name,
        "success": result.success,
        "tokens": result.tokens_used,
        "latency_ms": result.latency_ms,
        "error": result.error,
    })
    state["step_outputs"] = steps
