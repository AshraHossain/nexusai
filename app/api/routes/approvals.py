"""
Human Approval Routes
GET  /approvals/pending      — list pending approvals
POST /approvals/{id}/decide  — approve or reject
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.models.workflow import ApprovalDecisionRequest, WorkflowRunResponse
from app.orchestrator.graph import resume_workflow
from app.api.routes._store import workflow_store as _workflow_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["Human Approvals"])


@router.get(
    "/pending",
    summary="List workflows awaiting human approval",
)
async def list_pending_approvals() -> list[dict]:
    pending = []
    for wf_id, state in _workflow_store.items():
        if state.get("approval_status") == "pending":
            pending.append(
                {
                    "workflow_id": wf_id,
                    "workflow_type": state.get("workflow_type"),
                    "status": state.get("status"),
                    "current_step": state.get("current_step"),
                    "plan": state.get("plan"),
                }
            )
    return pending


@router.post(
    "/{workflow_id}/decide",
    response_model=WorkflowRunResponse,
    summary="Approve or reject a paused workflow step",
)
async def decide_approval(
    workflow_id: str, decision: ApprovalDecisionRequest
) -> WorkflowRunResponse:
    state = _workflow_store.get(workflow_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )

    if state.get("approval_status") != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workflow {workflow_id} is not awaiting approval",
        )

    try:
        final_state = await resume_workflow(
            workflow_id=workflow_id,
            approval_status=decision.status,
            notes=decision.notes,
        )
        _workflow_store[workflow_id] = final_state
        return WorkflowRunResponse.from_state(final_state)

    except Exception as exc:
        logger.exception("Failed to resume workflow %s", workflow_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resume failed: {exc}",
        )
