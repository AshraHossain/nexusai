"""
BaseAgent - shared contract for all NexusAI agents.
Every agent receives a WorkflowState slice, runs its LLM chain,
integrates with SentinelAI for I/O validation, and returns structured output.
"""
from __future__ import annotations

import abc
import logging
import time
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.config import settings
from app.integrations.sentinelai import get_sentinel_client
from app.observability.pricing import calculate_cost

logger = logging.getLogger(__name__)


# Agent Result


class AgentResult(BaseModel):
    agent_name: str
    success: bool
    output: str
    structured_output: dict[str, Any] = {}
    tokens_used: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    error: str | None = None
    metadata: dict[str, Any] = {}


# Base Agent


class BaseAgent(abc.ABC):
    """
    Abstract base for all NexusAI specialized agents.

    Subclasses implement:
      - system_prompt (property) - agent's role definition
      - execute(state) - core agent logic
    """

    name: str = "BaseAgent"
    agent_type: str = "base"

    def __init__(self) -> None:
        from app.llm.base import get_llm_provider
        self._llm = get_llm_provider()
        self._sentinel = get_sentinel_client()

    @property
    @abc.abstractmethod
    def system_prompt(self) -> str:
        """Agent role definition for the system message."""

    @abc.abstractmethod
    async def execute(self, state: dict[str, Any]) -> AgentResult:
        """
        Core agent logic.
        Receives the current WorkflowState dict, returns AgentResult.
        """

    async def run(self, state: dict[str, Any]) -> AgentResult:
        """
        Public entry point.
        Validates input -> executes -> validates output -> returns result.
        """
        start = time.monotonic()
        workflow_id = state.get("workflow_id")
        self._cost_accumulator: float = 0.0

        # 1. Validate input with SentinelAI
        user_input = state.get("user_request", "")
        if user_input:
            validation = await self._sentinel.validate_input(
                prompt=user_input,
                context={"agent": self.name},
                workflow_id=workflow_id,
            )
            if validation.blocked:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    output="",
                    error=f"Input blocked by SentinelAI: {validation.flags}",
                    latency_ms=int((time.monotonic() - start) * 1000),
                )

        # 2. Execute agent logic
        try:
            result = await self.execute(state)
        except Exception as exc:
            logger.exception("Agent %s failed", self.name)
            return AgentResult(
                agent_name=self.name,
                success=False,
                output="",
                error=str(exc),
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        # 3. Validate output with SentinelAI
        if result.success and result.output:
            out_validation = await self._sentinel.validate_output(
                output=result.output,
                context={"agent": self.name},
                workflow_id=workflow_id,
            )
            if out_validation.blocked:
                result.success = False
                result.error = f"Output blocked by SentinelAI: {out_validation.flags}"

        result.latency_ms = int((time.monotonic() - start) * 1000)
        result.cost_usd = round(result.cost_usd + self._cost_accumulator, 6)
        logger.info(
            "Agent %s completed in %dms | success=%s",
            self.name, result.latency_ms, result.success,
        )
        return result

    async def _call_llm(
        self,
        user_message: str,
        extra_system: str = "",
        **kwargs: Any,
    ) -> tuple[str, int]:
        """
        Helper: build messages, call LLM, return (content, token_count).
        """
        system_text = self.system_prompt
        if extra_system:
            system_text += f"\n\n{extra_system}"

        messages = [
            SystemMessage(content=system_text),
            HumanMessage(content=user_message),
        ]
        model = self._llm.get_chat_model(**kwargs)
        response = await model.ainvoke(messages)
        usage = getattr(response, "usage_metadata", {})
        if isinstance(usage, dict):
            total_tokens = usage.get("total_tokens", 0)
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)
        else:
            total_tokens = prompt_tokens = completion_tokens = 0

        model_name = self._llm.get_model_name(**kwargs)
        call_cost = calculate_cost(model_name, prompt_tokens, completion_tokens)
        self._cost_accumulator = round(
            getattr(self, "_cost_accumulator", 0.0) + call_cost, 6
        )

        return response.content, total_tokens
