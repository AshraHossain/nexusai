"""
Health & Readiness endpoints.
GET /health   - liveness probe
GET /ready    - readiness probe (checks integrations)
GET /metrics  - basic metrics summary
"""
from __future__ import annotations

import time

import httpx
from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["Health"])
_start_time = time.time()


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "uptime_seconds": int(time.time() - _start_time),
    }


@router.get("/ready", summary="Readiness probe - checks all integrations")
async def ready() -> dict:
    checks: dict[str, str] = {}

    for name, url in [
        ("sentinelai", settings.sentinelai_url),
        ("evalops", settings.evalops_url),
        ("knowledgeops", settings.knowledgeops_url),
    ]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{url}/health")
                checks[name] = "ok" if resp.status_code < 300 else f"degraded ({resp.status_code})"
        except Exception as exc:
            checks[name] = f"unreachable: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "integrations": checks,
    }


@router.get("/metrics", summary="Basic workflow metrics")
async def metrics() -> dict:
    from app.api.routes._store import workflow_store as _workflow_store

    total = len(_workflow_store)
    by_status: dict[str, int] = {}
    for state in _workflow_store.values():
        s = state.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    total_tokens = sum(s.get("total_tokens", 0) for s in _workflow_store.values())
    avg_tokens = total_tokens // total if total else 0

    total_cost = sum(s.get("total_cost_usd", 0.0) for s in _workflow_store.values())
    avg_cost = (total_cost / total) if total else 0.0

    return {
        "total_workflows": total,
        "by_status": by_status,
        "total_tokens_used": total_tokens,
        "avg_tokens_per_workflow": avg_tokens,
        "total_cost_usd": round(total_cost, 6),
        "avg_cost_usd_per_workflow": round(avg_cost, 6),
    }
