"""
NexusAI Configuration
Loads all settings from environment variables with sensible defaults.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class LLMProvider(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "NexusAI"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # ── LLM Provider ─────────────────────────────────────────────────────────
    llm_provider: LLMProvider = LLMProvider.OPENAI

    # OpenAI-compatible
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.1
    openai_max_tokens: int = 4096

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_temperature: float = 0.1

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://nexusai:nexusai@localhost:5432/nexusai"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Integrations ─────────────────────────────────────────────────────────
    sentinelai_url: str = "http://localhost:8001"
    sentinelai_api_key: Optional[str] = Field(default=None, env="SENTINELAI_API_KEY")

    evalops_url: str = "http://localhost:8002"
    evalops_api_key: Optional[str] = Field(default=None, env="EVALOPS_API_KEY")

    knowledgeops_url: str = "http://localhost:8003"
    knowledgeops_api_key: Optional[str] = Field(default=None, env="KNOWLEDGEOPS_API_KEY")

    # ── Orchestrator ──────────────────────────────────────────────────────────
    max_agent_retries: int = 3
    workflow_timeout_seconds: int = 300
    human_approval_timeout_seconds: int = 3600  # 1 hour
    max_concurrent_workflows: int = 50

    # ── Security ──────────────────────────────────────────────────────────────
    api_key_header: str = "X-API-Key"
    internal_api_key: Optional[str] = Field(default=None, env="NEXUSAI_API_KEY")
    sentinel_risk_threshold: int = 50  # reject if risk_score > this

    # ── Observability ─────────────────────────────────────────────────────────
    otel_enabled: bool = True
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "nexusai"

    # ── Evaluation ────────────────────────────────────────────────────────────
    evalops_min_quality: float = 0.7
    evalops_min_groundedness: float = 0.75

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
