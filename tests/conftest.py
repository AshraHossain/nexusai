"""
Shared pytest fixtures and environment setup for the NexusAI test suite.

Sets safe defaults via environment variables BEFORE any `app.*` module is
imported, since `app.config.settings` is instantiated at import time.
"""
from __future__ import annotations

import os

# ── Test environment defaults (set before any app import) ──────────────────
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/nexusai_pytest.db")
os.environ.setdefault("OTEL_ENABLED", "false")

import pytest


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"
