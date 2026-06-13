# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the API (dev)
uvicorn app.main:app --reload

# Run all tests (no API key required — everything is mocked)
DEBUG=false OPENAI_API_KEY=test-key DATABASE_URL='sqlite+aiosqlite:////tmp/nexusai_pytest.db' pytest -q

# Run a single test file
DEBUG=false OPENAI_API_KEY=test-key DATABASE_URL='sqlite+aiosqlite:////tmp/nexusai_pytest.db' pytest tests/test_agents.py -v

# Docker
docker compose -f docker/docker-compose.yml up --build
```

`pytest.ini` sets `asyncio_mode = auto` and `testpaths = tests`, so all async tests are auto-collected.

## Architecture

NexusAI is a **FastAPI + LangGraph** multi-agent orchestration platform. The central concept is a `WorkflowState` TypedDict (`app/orchestrator/state.py`) that flows through a compiled LangGraph state machine, accumulating outputs from each agent node.

### Request Flow

```
POST /workflows/run
  → FastAPI route (app/api/routes/workflows.py)
  → dispatches to run_workflow() or run_<specialized>()
  → LangGraph compiled_graph.ainvoke(state)
  → nodes: plan → research → coding → qa → security → documentation → evaluate
  → conditional routing between nodes via router.py
  → human_approval node pauses via interrupt_before + MemorySaver checkpointer
  → POST /approvals/{id} resumes via compiled_graph.ainvoke(updated_state)
```

### Agent Pattern

All agents inherit `BaseAgent` (`app/agents/base.py`) and implement two abstract members:
- `system_prompt` — the agent's role definition string
- `execute(state)` — core logic returning an `AgentResult`

`BaseAgent.run()` wraps every `execute()` call with SentinelAI input/output validation and cost accumulation. Agents call `self._call_llm()` which auto-tracks tokens → USD via the `PRICING` table in `app/observability/pricing.py`.

### Specialized Workflows

Each lives in `app/workflows/<name>/` with two files:
- `agents.py` — 4 domain-specific agents (no `BaseAgent` inheritance, simpler pattern)
- `graph.py` — its own LangGraph pipeline + `run_<name>()` entry point

Pattern: **retrieve context → domain analysis → risk/compliance scoring → executive report**. Compliance audit triggers human approval when `risk_score > 40`.

### External Integrations

`app/integrations/` contains three HTTP clients — `SentinelAI`, `EvalOps`, `KnowledgeOps` — each with a `get_<name>_client()` factory. In tests, `conftest.py` patches all three with fakes so no external services are needed.

### Configuration

All settings come from `app/config.py` via `pydantic-settings` → `.env`. The singleton is `from app.config import settings`. LLM provider switches between OpenAI-compatible and Ollama via `LLM_PROVIDER`. In debug mode (`DEBUG=true`), `create_tables()` runs at startup — use Alembic migrations in production.

### Cost Tracking

`app/observability/pricing.py` holds a `PRICING` dict mapping model names to `(prompt_$/1M, completion_$/1M)`. Unknown models fall back to `DEFAULT_PRICING` (never raises). Costs accumulate in `WorkflowState.total_cost_usd` per step and are exposed via `GET /metrics`.

### Database

SQLAlchemy async models in `app/db/models.py`: `WorkflowRun`, `WorkflowStep`, `AgentRun`, `Evaluation`, `SecurityEvent`, `AuditLog`, `Approval`. Default is PostgreSQL (`asyncpg`); SQLite (`aiosqlite`) is used in tests. Migrations live in `app/db/migrations/`.

### Human-in-the-Loop

The LangGraph graph is compiled with `interrupt_before=["human_approval"]` and a `MemorySaver` checkpointer. When security risk exceeds the threshold, the graph pauses before `node_human_approval`. `POST /approvals/{id}` reads the checkpoint, sets `approval_status`, and re-invokes the graph to resume.
