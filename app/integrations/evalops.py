"""
EvalOps Integration Client
Evaluation & Observability — scores workflow outputs for quality, completeness, groundedness.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)


# ── Response models ────────────────────────────────────────────────────────


class EvaluationResult(BaseModel):
    quality: float                    # 0.0–1.0
    completeness: float               # 0.0–1.0
    groundedness: float               # 0.0–1.0
    hallucination_score: float = 0.0  # 0.0–1.0 (lower is better)
    agent_efficiency: float = 1.0     # 0.0–1.0
    workflow_completion_rate: float = 1.0
    cost_per_workflow: float = 0.0
    passed: bool = False
    details: dict[str, Any] = {}

    def model_post_init(self, __context: Any) -> None:
        from app.config import settings as s
        self.passed = (
            self.quality >= s.evalops_min_quality
            and self.groundedness >= s.evalops_min_groundedness
        )


# ── Client ────────────────────────────────────────────────────────────────


class EvalOpsClient:
    """Async HTTP client for EvalOps."""

    def __init__(self) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if settings.evalops_api_key:
            headers["X-API-Key"] = settings.evalops_api_key

        self._client = httpx.AsyncClient(
            base_url=settings.evalops_url,
            headers=headers,
            timeout=60.0,  # evaluations can be slow
        )

    async def evaluate(
        self,
        workflow_id: str,
        prompt: str,
        response: str,
        context_docs: list[str] | None = None,
        workflow_type: str = "general",
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """
        POST /evaluate
        Evaluates a workflow's final output.
        """
        try:
            resp = await self._client.post(
                "/evaluate",
                json={
                    "workflow_id": workflow_id,
                    "prompt": prompt,
                    "response": response,
                    "context_docs": context_docs or [],
                    "workflow_type": workflow_type,
                    "metadata": metadata or {},
                },
            )
            resp.raise_for_status()
            return EvaluationResult(**resp.json())
        except httpx.HTTPError as exc:
            logger.warning("EvalOps evaluate failed: %s", exc)
            if settings.debug:
                return EvaluationResult(
                    quality=0.9,
                    completeness=0.9,
                    groundedness=0.9,
                )
            raise

    async def get_metrics(self, workflow_id: str) -> dict[str, Any]:
        """GET /metrics/{workflow_id} — fetch stored evaluation metrics."""
        resp = await self._client.get(f"/metrics/{workflow_id}")
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "EvalOpsClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()


# ── Singleton ─────────────────────────────────────────────────────────────
_evalops_client: EvalOpsClient | None = None


def get_evalops_client() -> EvalOpsClient:
    global _evalops_client
    if _evalops_client is None:
        _evalops_client = EvalOpsClient()
    return _evalops_client
