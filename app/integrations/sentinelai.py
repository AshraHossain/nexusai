"""
SentinelAI Integration Client
Security & Governance layer — validates inputs and scores outputs.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# ── Response models ────────────────────────────────────────────────────────


class ValidationResult(BaseModel):
    passed: bool
    flags: list[str] = []          # ["injection", "pii", "policy"]
    details: dict[str, Any] = {}
    blocked: bool = False


class RiskScoreResult(BaseModel):
    risk_score: int                 # 0–100; higher = riskier
    flags: list[str] = []
    recommendation: str = "allow"  # allow | review | block
    details: dict[str, Any] = {}


# ── Client ────────────────────────────────────────────────────────────────


class SentinelAIClient:
    """Async HTTP client for SentinelAI."""

    def __init__(self) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if settings.sentinelai_api_key:
            headers["X-API-Key"] = settings.sentinelai_api_key

        self._client = httpx.AsyncClient(
            base_url=settings.sentinelai_url,
            headers=headers,
            timeout=30.0,
        )

    async def validate_input(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        workflow_id: str | None = None,
    ) -> ValidationResult:
        """
        POST /validate-input
        Checks for prompt injection, PII, and policy violations.
        """
        try:
            resp = await self._client.post(
                "/validate-input",
                json={
                    "prompt": prompt,
                    "context": context or {},
                    "workflow_id": workflow_id,
                },
            )
            resp.raise_for_status()
            return ValidationResult(**resp.json())
        except httpx.HTTPError as exc:
            logger.warning("SentinelAI validate-input failed: %s — allowing by default", exc)
            # Fail open in dev; fail closed in prod by raising
            if settings.debug:
                return ValidationResult(passed=True)
            raise

    async def validate_output(
        self,
        output: str,
        context: dict[str, Any] | None = None,
        workflow_id: str | None = None,
    ) -> ValidationResult:
        """
        POST /validate-output
        Checks agent output for PII leakage, policy violations, and data leakage.
        """
        try:
            resp = await self._client.post(
                "/validate-output",
                json={
                    "output": output,
                    "context": context or {},
                    "workflow_id": workflow_id,
                },
            )
            resp.raise_for_status()
            return ValidationResult(**resp.json())
        except httpx.HTTPError as exc:
            logger.warning("SentinelAI validate-output failed: %s", exc)
            if settings.debug:
                return ValidationResult(passed=True)
            raise

    async def risk_score(
        self,
        content: str,
        content_type: str = "document",
        workflow_id: str | None = None,
    ) -> RiskScoreResult:
        """
        POST /risk-score
        Returns a numeric risk score (0–100) for content.
        """
        try:
            resp = await self._client.post(
                "/risk-score",
                json={
                    "content": content,
                    "content_type": content_type,
                    "workflow_id": workflow_id,
                },
            )
            resp.raise_for_status()
            return RiskScoreResult(**resp.json())
        except httpx.HTTPError as exc:
            logger.warning("SentinelAI risk-score failed: %s", exc)
            if settings.debug:
                return RiskScoreResult(risk_score=0)
            raise

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "SentinelAIClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()


# ── Singleton ─────────────────────────────────────────────────────────────
_sentinel_client: SentinelAIClient | None = None


def get_sentinel_client() -> SentinelAIClient:
    global _sentinel_client
    if _sentinel_client is None:
        _sentinel_client = SentinelAIClient()
    return _sentinel_client
