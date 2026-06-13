# NexusAI - Enterprise Agent Orchestration Platform

NexusAI is a production-shaped multi-agent orchestration platform built with
**FastAPI + LangGraph**. It coordinates a pipeline of specialized LLM agents
behind a governance layer (SentinelAI), a quality-evaluation layer (EvalOps),
and a retrieval layer (KnowledgeOps), with human-in-the-loop approval gates,
per-call cost tracking, and a full async test suite.

---

## Why this project

Most "AI agent" demos are a single prompt with tools. NexusAI models what an
enterprise actually needs around an LLM pipeline:

- **Orchestration** - a LangGraph state machine routes work between agents,
  persists state via checkpointing, and can pause mid-run for human approval.
- **Governance** - every input/output passes through SentinelAI for risk
  scoring; high-risk runs are blocked or escalated for approval.
- **Evaluation** - EvalOps scores each run for quality, completeness, and
  groundedness, so output quality is measurable, not assumed.
- **Retrieval** - KnowledgeOps provides hybrid + reranked RAG so agents work
  from an organization's actual documents/policies.
- **Cost tracking** - every LLM call's token usage is converted to USD via a
  per-model pricing table, rolled up per step and per workflow, and exposed
  via `/metrics`.
- **Specialized workflows** - beyond the general-purpose pipeline, NexusAI
  ships four purpose-built 4-agent workflows for real business tasks.

---

## Architecture

```
                         ┌────────────────────────┐
   POST /workflows/run   │   FastAPI (app.main)    │   GET /workflows/{id}
   ─────────────────────▶│  workflows / approvals  │◀───────────────────────
                          │       / health          │
                          └───────────┬─────────────┘
                                       │
                          ┌────────────▼─────────────┐
                          │   LangGraph Orchestrator   │
                          │ (MemorySaver checkpointer) │
                          └────────────┬─────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
┌───────▼────────┐           ┌─────────▼─────────┐          ┌─────────▼─────────┐
│  General        │           │ Specialized        │          │ Governance &       │
│  Pipeline       │           │ Workflows          │          │ Evaluation         │
│                 │           │                    │          │                    │
│ Planner         │           │ Contract Review    │          │ SentinelAI          │
│ Research        │           │  (4 agents)        │          │  - input/output     │
│ Coding          │           │ AI SDET            │          │    risk scoring     │
│ QA              │           │  (4 agents)        │          │  - blocks/approval  │
│ Security        │           │ Compliance Audit   │          │                    │
│ Documentation   │           │  (4 agents)        │          │ EvalOps             │
│                 │           │                    │          │  - quality score    │
│ + Human         │           │ Each: retrieve →   │          │  - groundedness     │
│   Approval gate │           │ analyze → assess   │          │                    │
│                 │           │ → report           │          │ KnowledgeOps        │
│                 │           │                    │          │  - hybrid RAG       │
└─────────────────┘           └────────────────────┘          └────────────────────┘
                                       │
                          ┌────────────▼─────────────┐
                          │   Cost Tracking            │
                          │  PRICING table → cost_usd  │
                          │  per step, per workflow     │
                          └────────────────────────────┘
```

### Core agents (general pipeline)

| Agent | Role |
|---|---|
| Planner | Breaks the request into a structured plan |
| Research | Retrieves and synthesizes relevant context via KnowledgeOps |
| Coding | Produces code/implementation artifacts |
| QA | Reviews and tests the output |
| Security | Risk-scores the work via SentinelAI |
| Documentation | Produces the final deliverable / report |

### Specialized 4-agent workflows

Each lives in `app/workflows/<name>/{agents.py, graph.py}` and follows the
same shape: **retrieve context -> domain analysis -> risk/compliance scoring
-> executive report**, with a human-approval gate when risk exceeds a
threshold.

- **Contract Review** (`contract_review`) - reviews contracts against a
  knowledge base of clauses/precedents, flags risk, produces a redline +
  recommendation report.
- **AI SDET** (`sdet`) - turns a feature description into test plans, test
  cases, and an automation/quality assessment.
- **Compliance Audit** (`compliance_audit`) - maps an audit scope to
  applicable regulations/controls (e.g. FAA Part 145, SOC 2, ISO 27001,
  GDPR, HIPAA), assesses evidence per control, scores compliance risk, and
  produces an executive audit report with a remediation plan. Risk scores
  above 40 require human approval before the final report is generated.

---

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows/run` | Start a workflow (`workflow_type`: `general`, `contract_review`, `sdet`, `compliance_audit`) |
| `GET`  | `/workflows/{id}` | Get workflow status, output, cost, and evaluation |
| `GET`  | `/workflows` | List recent workflows |
| `POST` | `/approvals/{id}` | Approve or reject a paused (high-risk) workflow |
| `GET`  | `/health` | Liveness check |
| `GET`  | `/ready` | Readiness check (DB connectivity) |
| `GET`  | `/metrics` | Aggregate metrics, including `total_cost_usd` and `avg_cost_usd_per_workflow` |
| `GET`  | `/docs` | Interactive OpenAPI (Swagger) docs |

---

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# set OPENAI_API_KEY (or configure llm_provider=ollama for local models)

# 3. Run the API
uvicorn app.main:app --reload

# 4. Try it
curl -X POST http://localhost:8000/workflows/run \
  -H "Content-Type: application/json" \
  -d '{
        "request": "Audit our maintenance records program against FAA Part 145.",
        "workflow_type": "compliance_audit",
        "created_by": "demo"
      }'
```

Or with Docker:

```bash
docker compose -f docker/docker-compose.yml up --build
```

---

## Demo script

A 3-minute walkthrough for a recruiter or hiring manager:

1. **Start the API** (`uvicorn app.main:app --reload`) and open `/docs`.
2. **Run a Compliance Audit**: `POST /workflows/run` with
   `workflow_type=compliance_audit` and a one-line audit scope. Show the
   response containing the policy mapping, evidence assessment, risk score,
   and final audit report - all generated by 4 chained agents.
3. **Trigger the approval gate**: use a scope that yields a risk score > 40
   (e.g. an audit scope describing missing controls). Show that the workflow
   pauses with `status: awaiting_approval`, then call
   `POST /approvals/{id}` to approve and let it complete.
4. **Show cost tracking**: `GET /workflows/{id}` returns `total_cost_usd`
   and a per-step cost breakdown; `GET /metrics` aggregates this across all
   runs.
5. **Show the test suite**: `pytest -q` - 65 tests covering every agent,
   workflow, the orchestrator, cost tracking, and the API, all running with
   mocked LLM/SentinelAI/EvalOps/KnowledgeOps clients (no API key required).
6. **Show the architecture map**: open `2026-06-09-nexusai-architecture-map.html`
   for an interactive view of the full system.

---

## Testing

```bash
pip install -r requirements.txt
DEBUG=false OPENAI_API_KEY=test-key DATABASE_URL='sqlite+aiosqlite:////tmp/nexusai_pytest.db' \
  pytest -q
```

65 tests, fully mocked (no external API calls), covering: all 6 core agents,
the orchestrator state machine, cost tracking/pricing, and all three
specialized workflows (contract review, SDET, compliance audit) including
their human-approval branches.

---

## Tech stack

- **FastAPI** - async REST API, OpenAPI docs, middleware (CORS, gzip, request IDs)
- **LangGraph** - state machine orchestration with checkpointing and interrupts
- **LangChain** - LLM provider abstraction (OpenAI-compatible APIs + Ollama)
- **SQLAlchemy (async) + SQLite/Postgres** - workflow/run persistence
- **pytest + pytest-asyncio** - async test suite with fakes for every external dependency

---

## Project layout

```
app/
  agents/            # 6 core agents (planner, research, coding, qa, security, documentation)
  api/routes/        # workflows, approvals, health endpoints
  db/                # SQLAlchemy models + async engine
  integrations/      # SentinelAI, EvalOps, KnowledgeOps clients
  llm/               # provider abstraction (OpenAI / Ollama)
  observability/     # telemetry + cost/pricing
  orchestrator/      # LangGraph state + general-pipeline graph
  workflows/
    contract_review/ # 4-agent contract review pipeline
    sdet/             # 4-agent AI SDET pipeline
    compliance_audit/ # 4-agent compliance audit pipeline
tests/               # 65 tests, fully mocked
docker/              # Dockerfile + docker-compose
```
