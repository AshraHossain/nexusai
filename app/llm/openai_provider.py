"""
OpenAI-Compatible LLM Provider
Works with OpenAI, Azure OpenAI, Groq, Together, vLLM, or any OpenAI-spec endpoint.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible provider via LangChain."""

    def get_chat_model(self, **kwargs: Any) -> ChatOpenAI:
        return ChatOpenAI(
            model=kwargs.get("model", settings.openai_model),
            temperature=kwargs.get("temperature", settings.openai_temperature),
            max_tokens=kwargs.get("max_tokens", settings.openai_max_tokens),
            openai_api_key=settings.openai_api_key,
            openai_api_base=settings.openai_base_url,
            streaming=kwargs.get("streaming", False),
        )

    def get_model_name(self, **kwargs: Any) -> str:
        return kwargs.get("model", settings.openai_model)

    async def astream(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        model = self.get_chat_model(streaming=True, **kwargs)
        async for chunk in model.astream(messages):
            if chunk.content:
                yield chunk.content
