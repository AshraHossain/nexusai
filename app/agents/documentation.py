"""
Documentation Agent
Generates READMEs, architecture documents, API documentation,
release notes, and technical specifications.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentResult, BaseAgent


DOCUMENTATION_SYSTEM_PROMPT = """
You are the Documentation Agent for NexusAI — a technical writer and architect.

Output types you produce:
- README.md — project overview, quickstart, usage, API reference
- Architecture Documents — system design, component diagrams (Mermaid), data flow
- API Documentation — OpenAPI-style endpoint documentation
- Release Notes — changelog format
- Technical Specifications — detailed design docs for engineers

Quality rules:
- Be precise and complete — documentation that omits critical details is harmful
- Include code examples wherever helpful
- Use Mermaid diagrams for architecture (```mermaid ... ```)
- Structure everything with clear headings
- Write for your target audience: engineers who will implement or maintain this

Mermaid diagram conventions:
- flowchart TD for architecture flows
- sequenceDiagram for API interactions
- erDiagram for database schemas
"""


class DocumentationAgent(BaseAgent):
    name = "DocumentationAgent"
    agent_type = "documentation"

    @property
    def system_prompt(self) -> str:
        return DOCUMENTATION_SYSTEM_PROMPT

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        task = state.get("current_task", state.get("user_request", ""))
        doc_type = state.get("doc_type", "architecture")  # readme|architecture|api|release_notes|spec
        code_output = state.get("coding_output", "")
        research_output = state.get("research_output", "")
        security_output = state.get("security_output", "")

        context = ""
        if research_output:
            context += f"\n### Research Summary:\n{research_output[:3000]}"
        if code_output:
            context += f"\n### Code Produced:\n{code_output[:3000]}"
        if security_output:
            context += f"\n### Security Review Summary:\n{security_output[:1000]}"

        prompt = (
            f"Document type: {doc_type}\n"
            f"Task: {task}\n"
            f"{context}\n\n"
            "Produce comprehensive, production-ready documentation."
        )

        content, tokens = await self._call_llm(prompt, max_tokens=6000)

        # Detect Mermaid diagrams
        import re
        diagrams = re.findall(r"```mermaid\n(.*?)```", content, re.DOTALL)

        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            structured_output={
                "doc_type": doc_type,
                "word_count": len(content.split()),
                "diagram_count": len(diagrams),
                "diagrams": diagrams,
            },
            tokens_used=tokens,
        )
