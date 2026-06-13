"""
LLM Cost Tracking
Per-provider/per-model token pricing and cost calculation helpers.

Prices are USD per 1,000,000 tokens (prompt / completion), based on
publicly listed provider rates at time of writing. Update PRICING as
providers change their rates. Unknown models fall back to
DEFAULT_PRICING so cost tracking never raises.
"""
from __future__ import annotations

# model name -> (prompt $ / 1M tokens, completion $ / 1M tokens)
PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    # Local / self-hosted models are free of marginal API cost.
    "llama3.2": (0.0, 0.0),
    "llama3.1": (0.0, 0.0),
    "mistral": (0.0, 0.0),
}

# Used when a model isn't in PRICING (e.g. unreleased or custom models).
DEFAULT_PRICING: tuple[float, float] = (5.00, 15.00)


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Return the USD cost for a single LLM call.

    Falls back to DEFAULT_PRICING for unrecognized model names so that
    cost tracking degrades gracefully rather than under-reporting as $0.
    """
    prompt_rate, completion_rate = PRICING.get(model, DEFAULT_PRICING)
    cost = (prompt_tokens / 1_000_000) * prompt_rate + (completion_tokens / 1_000_000) * completion_rate
    return round(cost, 6)


def get_pricing(model: str) -> tuple[float, float]:
    """Return (prompt_rate, completion_rate) per 1M tokens for a model."""
    return PRICING.get(model, DEFAULT_PRICING)
