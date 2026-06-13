"""
NexusAI FastAPI Application Entry Point
Enterprise Agent Orchestration Platform
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.api.routes import workflows, approvals, health
from app.db.database import create_tables
from app.observability.telemetry import setup_telemetry

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


# ── Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting NexusAI v%s", settings.app_version)

    # Telemetry
    if settings.otel_enabled:
        setup_telemetry()

    # Database (dev convenience — use Alembic in prod)
    if settings.debug:
        await create_tables()
        logger.info("Database tables created (debug mode)")

    logger.info("NexusAI ready — provider=%s", settings.llm_provider)
    yield

    logger.info("NexusAI shutting down")


# ── App ───────────────────────────────────────────────────────────────────

app = FastAPI(
    title="NexusAI",
    description=(
        "Enterprise Agent Orchestration Platform — "
        "coordinates Planner, Research, Coding, QA, Security, and Documentation agents "
        "with SentinelAI governance, EvalOps evaluation, and KnowledgeOps RAG."
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next) -> Response:
    import uuid
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.monotonic()
    response: Response = await call_next(request)
    duration = int((time.monotonic() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration}ms"
    return response


# ── Routers ───────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(workflows.router)
app.include_router(approvals.router)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "NexusAI",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }
