"""
Workflow Routes
POST /workflows/run         - start a workflow
GET  /workflows/{id}        - get workflow status
GET  /workflows             - list recent workflows
POST /workflows/{id}/cancel - cancel a running workflow
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import db_dependency
from app.models.workflow import (
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowListItem,
)
from app.orchestrator.graph import run_workflow
from app.workflows.contract_review.graph import run_contract_review
from app.workflows.sdet.graph import run_sdet_workflow
from app.workflows.compliance_audit.graph import run_compliance_audit
from app.api.routes._store import workflow_store as _workflow_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.post(
    "/run",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a new workflow",
)
async def start_workflow(
    req: WorkflowRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(db_dependency),
) -> WorkflowRunResponse:
    """
    Kick off a new multi-agent workflow.
    The workflow runs asynchronously; poll /workflows/{id} for status.
    """
    logger.info("Starting %s workflow: %.80s", req.workflow_type, req.request)

    try:
        if req.workflow_type == "contract_review":
            final_state = await run_contract_review(
                contract_text=req.request,
                created_by=req.created_by,
                collection=req.knowledge_collection
                if req.knowledge_collection != "default"
                else "contracts",
            )
        elif req.workflow_type == "sdet":
            final_state = await run_sdet_workflow(
                feature_description=req.request,
                created_by=req.created_by,
                collection=req.knowledge_collection,
            )
        elif req.workflow_type == "compliance_audit":
            final_state = await run_compliance_audit(
                audit_scope=req.request,
                created_by=req.created_by,
                collection=req.knowledge_collection
                if req.knowledge_collection != "default"
                else "compliance_policies",
            )
        else:
            final_state = await run_workflow(
                user_request=req.request,
                workflow_type=req.workflow_type,
                created_by=req.created_by,
                knowledge_collection=req.knowledge_collection,
                preferred_language=req.preferred_language,
            )
        # Cache state for retrieval
        _workflow_store[final_state["workflow_id"]] = final_state
        return WorkflowRunResponse.from_state(final_state)

    except Exception as exc:
        logger.exception("Workflow execution failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow failed: {exc}",
        )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowRunResponse,
    summary="Get workflow status and result",
)
async def get_workflow(workflow_id: str) -> WorkflowRunResponse:
    state = _workflow_store.get(workflow_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )
    return WorkflowRunResponse.from_state(state)


@router.get(
    "",
    response_model=list[WorkflowListItem],
    summary="List recent workflows",
)
async def list_workflows(limit: int = 20) -> list[WorkflowListItem]:
    from datetime import datetime

    items = []
    for state in list(_workflow_store.values())[-limit:]:
        items.append(
            WorkflowListItem(
                workflow_id=state["workflow_id"],
                status=state.get("status", "unknown"),
                workflow_type=state.get("workflow_type", "general"),
                total_tokens=state.get("total_tokens", 0),
                total_cost_usd=state.get("total_cost_usd", 0.0),
                duration_ms=state.get("duration_ms", 0),
                created_at=datetime.utcnow(),
            )
        )
    return items[::-1]  # newest first
