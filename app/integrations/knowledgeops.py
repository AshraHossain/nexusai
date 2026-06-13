"""
KnowledgeOps Integration Client
Enterprise RAG — hybrid retrieval with vector search + BM25 + cross-encoder reranking.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import httpx
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)


# ── Response models ────────────────────────────────────────────────────────


class Document(BaseModel):
    id: str
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = {}
    citations: list[str] = []
    source: str = ""


class RetrievalResult(BaseModel):
    documents: list[Document]
    query: str
    total_found: int
    retrieval_method: str = "hybrid"  # hybrid|vector|bm25


# ── Client ────────────────────────────────────────────────────────────────


class KnowledgeOpsClient:
    """Async HTTP client for KnowledgeOps."""

    def __init__(self) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if settings.knowledgeops_api_key:
            headers["X-API-Key"] = settings.knowledgeops_api_key

        self._client = httpx.AsyncClient(
            base_url=settings.knowledgeops_url,
            headers=headers,
            timeout=30.0,
        )

    async def retrieve(
        self,
        query: str,
        collection: str = "default",
        top_k: int = 5,
        retrieval_method: str = "hybrid",
        rerank: bool = True,
        filters: dict[str, Any] | None = None,
    ) -> RetrievalResult:
        """
        POST /retrieve
        Hybrid retrieval with optional cross-encoder reranking.
        """
        try:
            resp = await self._client.post(
                "/retrieve",
                json={
                    "query": query,
                    "collection": collection,
                    "top_k": top_k,
                    "retrieval_method": retrieval_method,
                    "rerank": rerank,
                    "filters": filters or {},
                },
            )
            resp.raise_for_status()
            return RetrievalResult(**resp.json())
        except httpx.HTTPError as exc:
            logger.warning("KnowledgeOps retrieve failed: %s", exc)
            if settings.debug:
                return RetrievalResult(
                    documents=[],
                    query=query,
                    total_found=0,
                )
            raise

    async def retrieve_stream(
        self,
        query: str,
        collection: str = "default",
        top_k: int = 5,
    ) -> AsyncIterator[str]:
        """
        POST /retrieve/stream
        Streaming retrieval response (Server-Sent Events).
        """
        async with self._client.stream(
            "POST",
            "/retrieve/stream",
            json={"query": query, "collection": collection, "top_k": top_k},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield line[6:]

    async def ingest(
        self,
        documents: list[dict[str, Any]],
        collection: str = "default",
    ) -> dict[str, Any]:
        """POST /ingest — add documents to the knowledge base."""
        resp = await self._client.post(
            "/ingest",
            json={"documents": documents, "collection": collection},
        )
        resp.raise_for_status()
        return resp.json()

    async def list_collections(self) -> list[str]:
        """GET /collections — available knowledge collections."""
        resp = await self._client.get("/collections")
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "KnowledgeOpsClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()


# ── Singleton ─────────────────────────────────────────────────────────────
_knowledgeops_client: KnowledgeOpsClient | None = None


def get_knowledgeops_client() -> KnowledgeOpsClient:
    global _knowledgeops_client
    if _knowledgeops_client is None:
        _knowledgeops_client = KnowledgeOpsClient()
    return _knowledgeops_client
