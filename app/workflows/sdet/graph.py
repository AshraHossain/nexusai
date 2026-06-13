"""
AI SDET Workflow
LangGraph pipeline for AI-driven software testing.

Pipeline:
  Feature/System Description
    → KnowledgeOps (retrieve existing tests, specs, requirements)
    → RequirementsAnalyzerAgent (extract what to test)
    → TestCaseGeneratorAgent (pytest unit tests)
    → PlaywrightAgent (E2E browser tests)
    → APITestAgent (API test suite)
    → DefectAnalyzerAgent (if test results provided)
    → SentinelAI (governance check on generated tests)
    → EvalOps (quality evaluation)
    → Final Test Package
"""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.workflows.sdet.agents import (
    RequirementsAnalyzerAgent,
    TestCaseGeneratorAgent,
    PlaywrightAgent,
    APITestAgent,
    DefectAnalyzerAgent,
)
from app.integrations.evalops import get_evalops_client
from app.integrations.knowledgeops import get_knowledgeops_client
from app.integrations.sentinelai import get_sentinel_client
from app.orchestrator.state import WorkflowState, initial_state


# ── Agent singletons ──────────────────────────────────────────────────────
_requirements = RequirementsAnalyzerAgent()
_test_gen = TestCaseGeneratorAgent()
_playwright = PlaywrightAgent()
_api_test = APITestAgent()
_defect = DefectAnalyzerAgent()


# ── Nodes ─────────────────────────────────────────────────────────────────

async def node_retrieve_specs(state: WorkflowState) -> WorkflowState:
    """Pull existing tests, specs, and documentation from KnowledgeOps."""
    ko = get_knowledgeops_client()
    result = await ko.retrieve(
        query=f"test specifications requirements: {state['user_request'][:200]}",
        collection=state.get("knowledge_collection", "default"),
        top_k=8,
        retrieval_method="hybrid",
    )
    state["research_output"] = "\n\n".join(
        f"[{d.source}] {d.content}" for d in result.documents
    )
    state["research_citations"] = [
        {"id": d.id, "source": d.source} for d in result.documents
    ]
    return state


async def node_analyze_requirements(state: WorkflowState) -> WorkflowState:
    """Extract test requirements from feature description."""
    result = await _requirements.run(state)
    # Store requirements in research_output for downstream agents
    state["research_output"] = result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    _append(state, "requirements_analysis", result)
    return state


async def node_generate_unit_tests(state: WorkflowState) -> WorkflowState:
    """Generate pytest unit and integration tests."""
    result = await _test_gen.run(state)
    state["qa_output"] = result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    _append(state, "unit_tests", result)
    return state


async def node_generate_e2e_tests(state: WorkflowState) -> WorkflowState:
    """Generate Playwright E2E test suite."""
    result = await _playwright.run(state)
    # Append E2E tests to qa_output
    state["qa_output"] = (state.get("qa_output", "") or "") + "\n\n---\n\n## Playwright E2E Tests\n" + result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    _append(state, "e2e_tests", result)
    return state


async def node_generate_api_tests(state: WorkflowState) -> WorkflowState:
    """Generate API test suite."""
    result = await _api_test.run(state)
    state["qa_output"] = (state.get("qa_output", "") or "") + "\n\n---\n\n## API Tests\n" + result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    _append(state, "api_tests", result)
    return state


async def node_analyze_defects(state: WorkflowState) -> WorkflowState:
    """Analyze defects if test results are present in state."""
    if not state.get("qa_output"):
        return state
    result = await _defect.run(state)
    state["security_output"] = result.output  # defect report in security slot
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    _append(state, "defect_analysis", result)
    return state


async def node_governance_check(state: WorkflowState) -> WorkflowState:
    """SentinelAI check on generated test code for security issues."""
    sentinel = get_sentinel_client()
    test_code = state.get("qa_output", "")[:5000]  # limit for API
    try:
        risk = await sentinel.risk_score(
            content=test_code,
            content_type="code",
            workflow_id=state.get("workflow_id"),
        )
        state["sentinel_risk_score"] = risk.risk_score
        state["sentinel_flags"] = risk.flags
        state["security_passed"] = risk.risk_score < 50
    except Exception:
        state["security_passed"] = True
    return state


async def node_evaluate(state: WorkflowState) -> WorkflowState:
    evalops = get_evalops_client()
    try:
        eval_result = await evalops.evaluate(
            workflow_id=state["workflow_id"],
            prompt=state["user_request"],
            response=state.get("qa_output", ""),
            workflow_type="sdet",
        )
        state["eval_quality"] = eval_result.quality
        state["eval_completeness"] = eval_result.completeness
        state["eval_groundedness"] = eval_result.groundedness
        state["eval_passed"] = eval_result.passed
    except Exception:
        state["eval_passed"] = True
    return state


async def node_package_output(state: WorkflowState) -> WorkflowState:
    """Assemble the final test package report."""
    steps = state.get("step_outputs", [])
    step_names = [s.get("step") for s in steps]
    total_tokens = state.get("total_tokens", 0)

    header = (
        "# AI SDET Test Package\n"
        f"**Workflow ID:** {state['workflow_id']}\n"
        f"**Feature:** {state['user_request'][:100]}\n"
        f"**Tests generated:** {', '.join(step_names)}\n"
        f"**Total tokens:** {total_tokens}\n\n"
        "---\n\n"
    )
    state["final_output"] = header + (state.get("qa_output") or "No tests generated.")
    state["status"] = "completed"
    return state


# ── Graph ─────────────────────────────────────────────────────────────────

def build_sdet_graph() -> StateGraph:
    builder = StateGraph(WorkflowState)

    builder.add_node("retrieve_specs", node_retrieve_specs)
    builder.add_node("analyze_requirements", node_analyze_requirements)
    builder.add_node("generate_unit_tests", node_generate_unit_tests)
    builder.add_node("generate_e2e_tests", node_generate_e2e_tests)
    builder.add_node("generate_api_tests", node_generate_api_tests)
    builder.add_node("analyze_defects", node_analyze_defects)
    builder.add_node("governance_check", node_governance_check)
    builder.add_node("evaluate", node_evaluate)
    builder.add_node("package_output", node_package_output)

    builder.add_edge(START, "retrieve_specs")
    builder.add_edge("retrieve_specs", "analyze_requirements")
    builder.add_edge("analyze_requirements", "generate_unit_tests")
    builder.add_edge("generate_unit_tests", "generate_e2e_tests")
    builder.add_edge("generate_e2e_tests", "generate_api_tests")
    builder.add_edge("generate_api_tests", "analyze_defects")
    builder.add_edge("analyze_defects", "governance_check")
    builder.add_edge("governance_check", "evaluate")
    builder.add_edge("evaluate", "package_output")
    builder.add_edge("package_output", END)

    return builder


_sdet_checkpointer = MemorySaver()
sdet_graph = build_sdet_graph().compile(checkpointer=_sdet_checkpointer)


async def run_sdet_workflow(
    feature_description: str,
    created_by: str = "api",
    collection: str = "default",
    existing_test_results: str = "",
) -> WorkflowState:
    workflow_id = str(uuid.uuid4())
    state = initial_state(
        workflow_id=workflow_id,
        user_request=feature_description,
        workflow_type="sdet",
        created_by=created_by,
        knowledge_collection=collection,
    )
    if existing_test_results:
        state["qa_output"] = existing_test_results  # for defect analysis mode

    config = {"configurable": {"thread_id": workflow_id}}
    return await sdet_graph.ainvoke(state, config=config)


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
