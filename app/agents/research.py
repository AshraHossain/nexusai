"""
Research Agent
Retrieves knowledge via KnowledgeOps hybrid RAG pipeline.
Gathers context, documents, citations, and domain expertise.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentResult, BaseAgent
from app.integrations.knowledgeops import get_knowledgeops_client


RESEARCH_SYSTEM_PROMPT = """
You are the Research Agent for NexusAI.

Your role:
- Synthesise retrieved documents into a clear, structured research summary
- Cite your sources explicitly (document IDs or URLs)
- Highlight gaps — if the knowledge base lacks key information, say so clearly
- Be precise: use domain-specific terminology correctly
- Structure your output as:
  1. Key Findings
  2. Supporting Evidence (with citations)
  3. Knowledge Gaps
  4. Recommendations for next agents

Do not hallucinate. If you don't know something, state it.
"""


class ResearchAgent(BaseAgent):
    name = "ResearchAgent"
    agent_type = "research"

    @property
    def system_prompt(self) -> str:
        return RESEARCH_SYSTEM_PROMPT

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        task = state.get("current_task", state.get("user_request", ""))
        collection = state.get("knowledge_collection", "default")
        workflow_id = state.get("workflow_id")

        # 1. Retrieve relevant documents from KnowledgeOps
        ko_client = get_knowledgeops_client()
        retrieval = await ko_client.retrieve(
            query=task,
            collection=collection,
            top_k=8,
            retrieval_method="hybrid",
            rerank=True,
        )

        # 2. Build context from retrieved docs
        doc_context = ""
        citations = []
        for i, doc in enumerate(retrieval.documents, 1):
            doc_context += f"\n\n[Document {i}] (score={doc.score:.3f})\nSource: {doc.source}\n{doc.content}"
            citations.append({"id": doc.id, "source": doc.source, "score": doc.score})

        if not doc_context:
            doc_context = "No documents found in the knowledge base for this query."

        # 3. Synthesise with LLM
        prompt = (
            f"Task to research:\n{task}\n\n"
            f"Retrieved documents:{doc_context}\n\n"
            "Synthesise a comprehensive research summary."
        )

        content, tokens = await self._call_llm(prompt)

        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            structured_output={
                "summary": content,
                "citations": citations,
                "documents_retrieved": len(retrieval.documents),
                "retrieval_method": retrieval.retrieval_method,
            },
            tokens_used=tokens,
        )
