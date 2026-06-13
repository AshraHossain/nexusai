"""
Unit tests for LLM cost tracking:
- app.observability.pricing.calculate_cost
- BaseAgent._call_llm cost accumulation
- WorkflowRunResponse / WorkflowListItem cost fields
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from app.agents.base import AgentResult, BaseAgent
from app.integrations.sentinelai import ValidationResult
from app.models.workflow import WorkflowRunResponse, WorkflowListItem
from app.observability.pricing import calculate_cost, get_pricing


# ── pricing.calculate_cost ───────────────────────────────────────────────────

def test_calculate_cost_known_model():
    # gpt-4o: $2.50 / 1M prompt, $10.00 / 1M completion
    cost = calculate_cost("gpt-4o", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == pytest.approx(12.50)


def test_calculate_cost_zero_tokens():
    assert calculate_cost("gpt-4o", 0, 0) == 0.0


def test_calculate_cost_local_model_is_free():
    assert calculate_cost("llama3.2", 100_000, 100_000) == 0.0


def test_calculate_cost_unknown_model_uses_default_pricing():
    default_prompt_rate, default_completion_rate = get_pricing("totally-unknown-model-x")
    cost = calculate_cost("totally-unknown-model-x", 1_000_000, 1_000_000)
    assert cost == pytest.approx(default_prompt_rate + default_completion_rate)
    assert cost > 0


# ── BaseAgent cost accumulation ──────────────────────────────────────────────

class _FakeChatModel:
    def __init__(self, content: str, input_tokens: int, output_tokens: int):
        self._content = content
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    async def ainvoke(self, messages):
        return AIMessage(
            content=self._content,
            usage_metadata={
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "total_tokens": self._input_tokens + self._output_tokens,
            },
        )


class _FakeLLMProvider:
    def __init__(self, model_name: str, chat_model: _FakeChatModel):
        self._model_name = model_name
        self._chat_model = chat_model

    def get_chat_model(self, **kwargs):
        return self._chat_model

    def get_model_name(self, **kwargs) -> str:
        return self._model_name


class _FakeSentinel:
    async def validate_input(self, prompt, context=None, workflow_id=None):
        return ValidationResult(passed=True)

    async def validate_output(self, output, context=None, workflow_id=None):
        return ValidationResult(passed=True)


class _CostingAgent(BaseAgent):
    name = "CostingAgent"
    agent_type = "test"

    def __init__(self, llm_provider: _FakeLLMProvider, num_calls: int = 1):
        self._llm = llm_provider
        self._sentinel = _FakeSentinel()
        self._num_calls = num_calls

    @property
    def system_prompt(self) -> str:
        return "You are a test agent."

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        total_tokens = 0
        for _ in range(self._num_calls):
            content, tokens = await self._call_llm("hello")
            total_tokens += tokens
        return AgentResult(agent_name=self.name, success=True, output="ok", tokens_used=total_tokens)


@pytest.mark.asyncio
async def test_call_llm_accumulates_cost_into_result():
    # gpt-4o-mini: $0.15 / 1M prompt, $0.60 / 1M completion
    chat_model = _FakeChatModel("response", input_tokens=1_000_000, output_tokens=1_000_000)
    provider = _FakeLLMProvider("gpt-4o-mini", chat_model)
    agent = _CostingAgent(provider, num_calls=1)

    result = await agent.run({"workflow_id": "wf-1"})

    assert result.success is True
    expected_cost = calculate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert result.cost_usd == pytest.approx(expected_cost)
    assert expected_cost == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_call_llm_cost_accumulates_across_multiple_calls():
    chat_model = _FakeChatModel("response", input_tokens=500_000, output_tokens=500_000)
    provider = _FakeLLMProvider("gpt-4o-mini", chat_model)
    agent = _CostingAgent(provider, num_calls=2)

    result = await agent.run({"workflow_id": "wf-1"})

    single_call_cost = calculate_cost("gpt-4o-mini", 500_000, 500_000)
    assert result.cost_usd == pytest.approx(single_call_cost * 2)


@pytest.mark.asyncio
async def test_call_llm_local_model_zero_cost():
    chat_model = _FakeChatModel("response", input_tokens=10_000, output_tokens=10_000)
    provider = _FakeLLMProvider("llama3.2", chat_model)
    agent = _CostingAgent(provider, num_calls=1)

    result = await agent.run({"workflow_id": "wf-1"})
    assert result.cost_usd == 0.0


# ── Response model cost fields ──────────────────────────────────────────────

def test_workflow_run_response_includes_total_cost():
    state = {
        "workflow_id": "wf-1",
        "status": "completed",
        "workflow_type": "general",
        "total_tokens": 1000,
        "total_cost_usd": 0.0123,
    }
    resp = WorkflowRunResponse.from_state(state)
    assert resp.total_cost_usd == pytest.approx(0.0123)


def test_step_summary_default_cost_is_zero():
    state = {
        "workflow_id": "wf-1",
        "status": "completed",
        "workflow_type": "general",
        "step_outputs": [{"step": "plan", "success": True, "tokens": 50}],
    }
    resp = WorkflowRunResponse.from_state(state)
    assert resp.step_outputs[0].cost_usd == 0.0


def test_workflow_list_item_accepts_cost():
    item = WorkflowListItem(
        workflow_id="wf-1",
        status="completed",
        workflow_type="general",
        total_tokens=100,
        total_cost_usd=0.05,
        duration_ms=500,
        created_at="2026-06-10T00:00:00",
    )
    assert item.total_cost_usd == 0.05
