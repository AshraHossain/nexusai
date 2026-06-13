"""
NexusAI LangGraph Orchestrator
Builds the multi-agent state machine graph.
Nodes -> agents; edges -> router functions.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.agents.planner import PlannerAgent
from app.agents.research import ResearchAgent
from app.agents.coding import CodingAgent
from app.agents.qa import QAAgent
from app.agents.security import SecurityAgent
from app.agents.documentation import DocumentationAgent
from app.integrations.evalops import get_evalops_client
from app.orchestrator.state import WorkflowState, initial_state
from app.orchestrator.router import (
    route_after_plan,
    route_after_research,
    route_after_coding,
    route_after_qa,
    route_after_security,
    route_after_approval,
    route_after_evaluate,
)

logger = logging.getLogger(__name__)

# Agent singletons
_planner = PlannerAgent()
_research = ResearchAgent()
_coding = CodingAgent()
_qa = QAAgent()
_security = SecurityAgent()
_docs = DocumentationAgent()


# Node functions

async def node_plan(state: WorkflowState) -> WorkflowState:
    """Step 1: Decompose the request into a plan."""
    result = await _planner.run(state)
    state["plan"] = result.structured_output
    state["current_step"] = 0
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _append_step(state, "plan", result)
    if not result.success:
        state["error"] = result.error
    return state


async def node_research(state: WorkflowState) -> WorkflowState:
    """Retrieve knowledge from KnowledgeOps."""
    _set_current_task(state, "research")
    result = await _research.run(state)
    state["research_output"] = result.output
    state["research_citations"] = result.structured_output.get("citations", [])
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _advance_step(state)
    _append_step(state, "research", result)
    return state


async def node_coding(state: WorkflowState) -> WorkflowState:
    """Generate code based on research and requirements."""
    _set_current_task(state, "coding")
    result = await _coding.run(state)
    state["coding_output"] = result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _advance_step(state)
    _append_step(state, "coding", result)
    return state


async def node_qa(state: WorkflowState) -> WorkflowState:
    """Generate tests for produced code."""
    _set_current_task(state, "qa")
    result = await _qa.run(state)
    state["qa_output"] = result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _advance_step(state)
    _append_step(state, "qa", result)
    return state


async def node_security(state: WorkflowState) -> WorkflowState:
    """Security review via SecurityAgent + SentinelAI."""
    _set_current_task(state, "security")
    result = await _security.run(state)
    state["security_output"] = result.output
    state["security_passed"] = result.structured_output.get("passed", True)
    state["sentinel_risk_score"] = result.structured_output.get("risk_score", 0)
    state["sentinel_flags"] = result.structured_output.get("sentinel_flags", [])
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _advance_step(state)
    _append_step(state, "security", result)
    return state


async def node_documentation(state: WorkflowState) -> WorkflowState:
    """Generate final documentation."""
    _set_current_task(state, "documentation")
    result = await _docs.run(state)
    state["documentation_output"] = result.output
    state["total_tokens"] = state.get("total_tokens", 0) + result.tokens_used
    state["total_cost_usd"] = round(state.get("total_cost_usd", 0.0) + result.cost_usd, 6)
    _advance_step(state)
    _append_step(state, "documentation", result)
    return state


async def node_evaluate(state: WorkflowState) -> WorkflowState:
    """Evaluate workflow output quality via EvalOps."""
    evalops = get_evalops_client()
    final = state.get("documentation_output") or state.get("coding_output") or ""
    context_docs = [c.get("source", "") for c in state.get("research_citations", [])]

    try:
        eval_result = await evalops.evaluate(
            workflow_id=state["workflow_id"],
            prompt=state["user_request"],
            response=final,
            context_docs=context_docs,
            workflow_type=state.get("workflow_type", "general"),
        )
        state["eval_quality"] = eval_result.quality
        state["eval_completeness"] = eval_result.completeness
        state["eval_groundedness"] = eval_result.groundedness
        state["eval_passed"] = eval_result.passed
        logger.info(
            "EvalOps | quality=%.2f completeness=%.2f groundedness=%.2f passed=%s",
            eval_result.quality, eval_result.completeness,
            eval_result.groundedness, eval_result.passed,
        )
    except Exception as exc:
        logger.warning("EvalOps evaluation failed: %s - continuing", exc)
        state["eval_passed"] = True  # fail open

    return state


async def node_human_approval(state: WorkflowState) -> WorkflowState:
    """
    Pause the workflow and request human approval.
    The approval endpoint resumes the graph via the checkpointer.
    """
    approval_id = str(uuid.uuid4())
    state["approval_id"] = approval_id
    state["approval_status"] = "pending"
    state["status"] = "awaiting_approval"
    logger.info("Workflow %s awaiting human approval %s", state["workflow_id"], approval_id)
    return state


async def node_end_success(state: WorkflowState) -> WorkflowState:
    final = (
        state.get("documentation_output")
        or state.get("coding_output")
        or state.get("research_output")
        or "Workflow completed."
    )
    state["final_output"] = final
    state["status"] = "completed"
    return state


async def node_end_error(state: WorkflowState) -> WorkflowState:
    state["status"] = "failed"
    state["final_output"] = f"Workflow failed: {state.get('error', 'Unknown error')}"
    return state


async def node_end_blocked(state: WorkflowState) -> WorkflowState:
    state["status"] = "failed"
    risk = state.get("sentinel_risk_score", 0)
    flags = state.get("sentinel_flags", [])
    state["final_output"] = (
        f"Workflow blocked by security policy. "
        f"Risk score: {risk}/100. Flags: {', '.join(flags) or 'none'}."
    )
    return state


async def node_end_rejected(state: WorkflowState) -> WorkflowState:
    state["status"] = "failed"
    state["final_output"] = (
        f"Workflow rejected during human approval. "
        f"Notes: {state.get('approval_notes', 'No notes provided.')}"
    )
    return state


async def node_end_quality_fail(state: WorkflowState) -> WorkflowState:
    state["status"] = "failed"
    state["final_output"] = (
        f"Workflow failed quality evaluation. "
        f"Quality: {state.get('eval_quality', 0):.2f} "
        f"Groundedness: {state.get('eval_groundedness', 0):.2f}"
    )
    return state


# Helpers

def _set_current_task(state: WorkflowState, agent_key: str) -> None:
    plan = state.get("plan", {})
    steps = plan.get("steps", [])
    idx = state.get("current_step", 0)
    if idx < len(steps):
        state["current_task"] = steps[idx].get("task", state.get("user_request", ""))
    else:
        state["current_task"] = state.get("user_request", "")


def _advance_step(state: WorkflowState) -> None:
    state["current_step"] = state.get("current_step", 0) + 1


def _append_step(state: WorkflowState, step_name: str, result: Any) -> None:
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


# Graph Builder

def build_graph() -> StateGraph:
    """
    Assemble the NexusAI LangGraph state machine.
    Returns a compiled graph ready to invoke.
    """
    builder = StateGraph(WorkflowState)

    # Register nodes
    builder.add_node("planner", node_plan)
    builder.add_node("research", node_research)
    builder.add_node("coding", node_coding)
    builder.add_node("qa", node_qa)
    builder.add_node("security", node_security)
    builder.add_node("documentation", node_documentation)
    builder.add_node("evaluate", node_evaluate)
    builder.add_node("human_approval", node_human_approval)
    builder.add_node("end_success", node_end_success)
    builder.add_node("end_error", node_end_error)
    builder.add_node("end_blocked", node_end_blocked)
    builder.add_node("end_rejected", node_end_rejected)
    builder.add_node("end_quality_fail", node_end_quality_fail)

    # Entry point
    builder.add_edge(START, "planner")

    # Conditional routing
    builder.add_conditional_edges(
        "planner",
        route_after_plan,
        {"research": "research", "coding": "coding", "end_error": "end_error"},
    )
    builder.add_conditional_edges(
        "research",
        route_after_research,
        {
            "coding": "coding",
            "qa": "qa",
            "security": "security",
            "documentation": "documentation",
            "evaluate": "evaluate",
            "end_error": "end_error",
        },
    )
    builder.add_conditional_edges(
        "coding",
        route_after_coding,
        {
            "qa": "qa",
            "security": "security",
            "documentation": "documentation",
            "human_approval": "human_approval",
            "evaluate": "evaluate",
            "end_error": "end_error",
        },
    )
    builder.add_conditional_edges(
        "qa",
        route_after_qa,
        {
            "security": "security",
            "documentation": "documentation",
            "evaluate": "evaluate",
            "end_error": "end_error",
        },
    )
    builder.add_conditional_edges(
        "security",
        route_after_security,
        {
            "documentation": "documentation",
            "human_approval": "human_approval",
            "evaluate": "evaluate",
            "end_error": "end_error",
            "end_blocked": "end_blocked",
        },
    )
    builder.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {"evaluate": "evaluate", "end_rejected": "end_rejected"},
    )
    builder.add_conditional_edges(
        "evaluate",
        route_after_evaluate,
        {
            "documentation": "documentation",
            "end_success": "end_success",
            "end_quality_fail": "end_quality_fail",
        },
    )

    # Terminal nodes -> END
    for terminal in ["end_success", "end_error", "end_blocked", "end_rejected", "end_quality_fail"]:
        builder.add_edge(terminal, END)

    # Documentation always flows to evaluate (unless already done)
    builder.add_edge("documentation", "evaluate")

    return builder


# Compiled graph (with in-memory checkpointer for human-in-loop)
_checkpointer = MemorySaver()
compiled_graph = build_graph().compile(
    checkpointer=_checkpointer,
    interrupt_before=["human_approval"],  # pause before approval node
)


async def run_workflow(
    user_request: str,
    workflow_type: str = "general",
    created_by: str = "api",
    **kwargs: Any,
) -> WorkflowState:
    """
    High-level entry point: creates a new workflow run and executes it.
    Returns the final WorkflowState.
    """
    workflow_id = str(uuid.uuid4())
    state = initial_state(
        workflow_id=workflow_id,
        user_request=user_request,
        workflow_type=workflow_type,
        created_by=created_by,
        **kwargs,
    )

    config = {"configurable": {"thread_id": workflow_id}}
    start_time = time.monotonic()

    final_state: WorkflowState = await compiled_graph.ainvoke(state, config=config)
    final_state["duration_ms"] = int((time.monotonic() - start_time) * 1000)

    return final_state


async def resume_workflow(workflow_id: str, approval_status: str, notes: str = "") -> WorkflowState:
    """Resume a workflow paused at human_approval."""
    config = {"configurable": {"thread_id": workflow_id}}

    # Get current state and update approval
    current = await compiled_graph.aget_state(config)
    updated = dict(current.values)
    updated["approval_status"] = approval_status
    updated["approval_notes"] = notes

    final_state: WorkflowState = await compiled_graph.ainvoke(updated, config=config)
    return final_state
