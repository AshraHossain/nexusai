"""
Shared in-memory workflow store (replace with DB-backed store in production).
Extracted to its own module to avoid circular imports between
workflows.py, approvals.py, and health.py.
"""
from __future__ import annotations

from typing import Any

workflow_store: dict[str, dict[str, Any]] = {}
