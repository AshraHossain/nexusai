"""
NexusAI SQLAlchemy ORM Models
Tables: agents, agent_runs, agent_messages, tool_calls,
        workflow_runs, workflow_steps, evaluations,
        security_events, audit_logs, approvals
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# Agents

class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(100), nullable=False, unique=True)
    agent_type = Column(String(50), nullable=False)  # planner|research|coding|qa|security|documentation
    description = Column(Text)
    capabilities = Column(JSON, default=list)
    config = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    runs = relationship("AgentRun", back_populates="agent", cascade="all, delete-orphan")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    agent_id = Column(UUID(as_uuid=False), ForeignKey("agents.id"), nullable=False)
    workflow_step_id = Column(UUID(as_uuid=False), ForeignKey("workflow_steps.id"), nullable=True)
    status = Column(String(20), default="pending")  # pending|running|completed|failed
    input_data = Column(JSON)
    output_data = Column(JSON)
    tokens_used = Column(Integer, default=0)
    latency_ms = Column(Integer)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agent = relationship("Agent", back_populates="runs")
    workflow_step = relationship("WorkflowStep", back_populates="agent_runs")
    messages = relationship("AgentMessage", back_populates="run", cascade="all, delete-orphan")
    tool_calls = relationship("ToolCall", back_populates="run", cascade="all, delete-orphan")


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    run_id = Column(UUID(as_uuid=False), ForeignKey("agent_runs.id"), nullable=False)
    role = Column(String(20), nullable=False)  # system|user|assistant|tool
    content = Column(Text, nullable=False)
    extra_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("AgentRun", back_populates="messages")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    run_id = Column(UUID(as_uuid=False), ForeignKey("agent_runs.id"), nullable=False)
    tool_name = Column(String(100), nullable=False)
    tool_input = Column(JSON)
    tool_output = Column(JSON)
    status = Column(String(20), default="pending")
    latency_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("AgentRun", back_populates="tool_calls")


# Workflows

class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    workflow_type = Column(String(100), nullable=False)  # general|contract_review|sdet|compliance_audit
    title = Column(String(255))
    status = Column(String(20), default="pending")  # pending|running|awaiting_approval|completed|failed
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_message = Column(Text)
    total_tokens = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)
    duration_ms = Column(Integer)
    created_by = Column(String(255))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    steps = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan")
    evaluations = relationship("Evaluation", back_populates="workflow", cascade="all, delete-orphan")
    security_events = relationship("SecurityEvent", back_populates="workflow", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="workflow", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    workflow_id = Column(UUID(as_uuid=False), ForeignKey("workflow_runs.id"), nullable=False)
    step_name = Column(String(100), nullable=False)
    step_order = Column(Integer, nullable=False)
    status = Column(String(20), default="pending")
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("WorkflowRun", back_populates="steps")
    agent_runs = relationship("AgentRun", back_populates="workflow_step")


# Evaluation

class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    workflow_id = Column(UUID(as_uuid=False), ForeignKey("workflow_runs.id"), nullable=False)
    quality_score = Column(Float)
    completeness_score = Column(Float)
    groundedness_score = Column(Float)
    hallucination_score = Column(Float)
    agent_efficiency = Column(Float)
    raw_response = Column(JSON)
    passed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("WorkflowRun", back_populates="evaluations")


# Security

class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    workflow_id = Column(UUID(as_uuid=False), ForeignKey("workflow_runs.id"), nullable=True)
    event_type = Column(String(50), nullable=False)  # input_validation|output_validation|risk_score
    risk_score = Column(Integer)
    flags = Column(JSON, default=list)   # ["injection", "pii", "policy"]
    blocked = Column(Boolean, default=False)
    raw_response = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("WorkflowRun", back_populates="security_events")


# Audit

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    workflow_id = Column(UUID(as_uuid=False), ForeignKey("workflow_runs.id"), nullable=True)
    action = Column(String(100), nullable=False)
    actor = Column(String(255))
    resource_type = Column(String(100))
    resource_id = Column(String(255))
    details = Column(JSON, default=dict)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("WorkflowRun", back_populates="audit_logs")


# Human Approval

class Approval(Base):
    __tablename__ = "approvals"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    workflow_id = Column(UUID(as_uuid=False), ForeignKey("workflow_runs.id"), nullable=False)
    step_name = Column(String(100), nullable=False)
    status = Column(String(20), default="pending")  # pending|approved|rejected|expired
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_by = Column(String(255))
    reviewed_at = Column(DateTime(timezone=True))
    review_notes = Column(Text)
    payload = Column(JSON)  # content to review
    expires_at = Column(DateTime(timezone=True))

    workflow = relationship("WorkflowRun", back_populates="approvals")
