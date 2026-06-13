"""
LLM Provider Abstraction
Unified interface for OpenAI-compatible APIs and Ollama.
"""
from __future__ import annotations

import abc
from typing import Any, AsyncIterator

from langchain_core.messages import BaseMessage
from langchain_core.language_models import BaseChatModel


class LLMProvider(abc.ABC):
    """Abstract base for LLM providers."""

    @abc.abstractmethod
    def get_chat_model(self, **kwargs: Any) -> BaseChatModel:
        """Return a LangChain-compatible chat model."""

    @abc.abstractmethod
    def get_model_name(self, **kwargs: Any) -> str:
        """Return the configured model name (used for cost calculation)."""

    @abc.abstractmethod
    async def astream(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream response tokens."""


def get_llm_provider() -> LLMProvider:
    """Factory - returns the configured provider."""
    from app.config import settings, LLMProvider as LLMProviderEnum

    if settings.llm_provider == LLMProviderEnum.OPENAI:
        from app.llm.openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif settings.llm_provider == LLMProviderEnum.OLLAMA:
        from app.llm.ollama_provider import OllamaProvider
        return OllamaProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
