"""
Ollama LLM Provider
Fully local inference — no API key required.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama

from app.config import settings
from app.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    """Ollama local model provider via LangChain."""

    def get_chat_model(self, **kwargs: Any) -> ChatOllama:
        return ChatOllama(
            model=kwargs.get("model", settings.ollama_model),
            temperature=kwargs.get("temperature", settings.ollama_temperature),
            base_url=settings.ollama_base_url,
        )

    def get_model_name(self, **kwargs: Any) -> str:
        return kwargs.get("model", settings.ollama_model)

    async def astream(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        model = self.get_chat_model(**kwargs)
        async for chunk in model.astream(messages):
            if chunk.content:
                yield chunk.content
