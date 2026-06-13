-- NexusAI Initial Schema Migration
-- Run once against a clean PostgreSQL 15+ database.

BEGIN;

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- fuzzy search on audit logs

-- ── Agents ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(100) NOT NULL UNIQUE,
    agent_type  VARCHAR(50)  NOT NULL CHECK (agent_type IN (
                    'planner','research','coding','qa','security','documentation'
                )),
    description TEXT,
    capabilities JSONB DEFAULT '[]',
    config       JSONB DEFAULT '{}',
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ
);

CREATE INDEX idx_agents_type     ON agents (agent_type);
CREATE INDEX idx_agents_active   ON agents (is_active);

-- ── Workflow Runs ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS workflow_runs (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_type VARCHAR(100) NOT NULL,
    title         VARCHAR(255),
    status        VARCHAR(20) DEFAULT 'pending' CHECK (status IN (
                      'pending','running','awaiting_approval','completed','failed'
                  )),
    input_data    JSONB,
    output_data   JSONB,
    error_message TEXT,
    total_tokens  INTEGER DEFAULT 0,
    total_cost_usd NUMERIC(10,6) DEFAULT 0,
    duration_ms   INTEGER,
    created_by    VARCHAR(255),
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_workflow_runs_status ON workflow_runs (status);
CREATE INDEX idx_workflow_runs_type   ON workflow_runs (workflow_type);
CREATE INDEX idx_workflow_runs_created ON workflow_runs (created_at DESC);

-- ── Workflow Steps ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS workflow_steps (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    step_name   VARCHAR(100) NOT NULL,
    step_order  INTEGER NOT NULL,
    status      VARCHAR(20) DEFAULT 'pending',
    input_data  JSONB,
    output_data JSONB,
    error_message TEXT,
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_workflow_steps_workflow ON workflow_steps (workflow_id);

-- ── Agent Runs ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_runs (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id         UUID NOT NULL REFERENCES agents(id),
    workflow_step_id UUID REFERENCES workflow_steps(id),
    status           VARCHAR(20) DEFAULT 'pending',
    input_data       JSONB,
    output_data      JSONB,
    tokens_used      INTEGER DEFAULT 0,
    latency_ms       INTEGER,
    error_message    TEXT,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_runs_agent  ON agent_runs (agent_id);
CREATE INDEX idx_agent_runs_step   ON agent_runs (workflow_step_id);
CREATE INDEX idx_agent_runs_status ON agent_runs (status);

-- ── Agent Messages ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_messages (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id     UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    role       VARCHAR(20) NOT NULL CHECK (role IN ('system','user','assistant','tool')),
    content    TEXT NOT NULL,
    metadata   JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_messages_run ON agent_messages (run_id);

-- ── Tool Calls ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tool_calls (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id      UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    tool_name   VARCHAR(100) NOT NULL,
    tool_input  JSONB,
    tool_output JSONB,
    status      VARCHAR(20) DEFAULT 'pending',
    latency_ms  INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tool_calls_run  ON tool_calls (run_id);
CREATE INDEX idx_tool_calls_name ON tool_calls (tool_name);

-- ── Evaluations ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS evaluations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id         UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    quality_score       NUMERIC(4,3),
    completeness_score  NUMERIC(4,3),
    groundedness_score  NUMERIC(4,3),
    hallucination_score NUMERIC(4,3),
    agent_efficiency    NUMERIC(4,3),
    raw_response        JSONB,
    passed              BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_evaluations_workflow ON evaluations (workflow_id);
CREATE INDEX idx_evaluations_passed   ON evaluations (passed);

-- ── Security Events ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS security_events (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id  UUID REFERENCES workflow_runs(id),
    event_type   VARCHAR(50) NOT NULL,
    risk_score   INTEGER,
    flags        JSONB DEFAULT '[]',
    blocked      BOOLEAN DEFAULT FALSE,
    raw_response JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_security_events_workflow ON security_events (workflow_id);
CREATE INDEX idx_security_events_blocked  ON security_events (blocked);
CREATE INDEX idx_security_events_score    ON security_events (risk_score DESC);

-- ── Audit Logs ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_logs (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id   UUID REFERENCES workflow_runs(id),
    action        VARCHAR(100) NOT NULL,
    actor         VARCHAR(255),
    resource_type VARCHAR(100),
    resource_id   VARCHAR(255),
    details       JSONB DEFAULT '{}',
    ip_address    INET,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_workflow   ON audit_logs (workflow_id);
CREATE INDEX idx_audit_logs_actor      ON audit_logs (actor);
CREATE INDEX idx_audit_logs_action     ON audit_logs (action);
CREATE INDEX idx_audit_logs_created    ON audit_logs (created_at DESC);

-- ── Human Approvals ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS approvals (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id  UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    step_name    VARCHAR(100) NOT NULL,
    status       VARCHAR(20) DEFAULT 'pending' CHECK (status IN (
                     'pending','approved','rejected','expired'
                 )),
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_by  VARCHAR(255),
    reviewed_at  TIMESTAMPTZ,
    review_notes TEXT,
    payload      JSONB,
    expires_at   TIMESTAMPTZ
);

CREATE INDEX idx_approvals_workflow ON approvals (workflow_id);
CREATE INDEX idx_approvals_status   ON approvals (status);

-- ── Seed default agents ───────────────────────────────────────────────────

INSERT INTO agents (name, agent_type, description, capabilities) VALUES
    ('PlannerAgent',       'planner',       'Decomposes tasks and plans multi-agent workflows',
     '["task_decomposition","workflow_planning","agent_routing"]'),
    ('ResearchAgent',      'research',      'Retrieves knowledge via KnowledgeOps RAG pipeline',
     '["knowledge_retrieval","document_lookup","context_gathering"]'),
    ('CodingAgent',        'coding',        'Generates, refactors, and scaffolds code',
     '["code_generation","refactoring","bug_fixing","architecture"]'),
    ('QAAgent',            'qa',            'Generates test suites and Playwright automation',
     '["test_generation","playwright","api_testing","performance_testing"]'),
    ('SecurityAgent',      'security',      'Analyses prompts and outputs via SentinelAI',
     '["prompt_injection_analysis","vulnerability_detection","secret_scanning"]'),
    ('DocumentationAgent', 'documentation', 'Produces READMEs, API docs, and architecture docs',
     '["readme_generation","api_documentation","architecture_docs"]')
ON CONFLICT (name) DO NOTHING;

COMMIT;
