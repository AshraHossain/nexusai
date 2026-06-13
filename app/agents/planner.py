"""
Planner Agent
Decomposes the user request into a structured execution plan,
assigns agents, and determines step order and dependencies.
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.base import AgentResult, BaseAgent


PLANNER_SYSTEM_PROMPT = """
You are the Planner Agent for NexusAI — an enterprise AI orchestration platform.

Your role:
- Analyse the user's request thoroughly
- Decompose it into discrete, ordered workflow steps
- Assign the correct specialist agent to each step
- Identify dependencies between steps
- Produce a structured JSON execution plan

Available agents:
- research_agent      → knowledge retrieval, documentation lookup, FAA/compliance research
- coding_agent        → code generation, refactoring, architecture scaffolding
- qa_agent            → test generation, Playwright automation, API testing
- security_agent      → security review, vulnerability detection, risk assessment
- documentation_agent → README generation, API docs, architecture documents

Output ONLY valid JSON in this exact schema:
{
  "title": "short plan title",
  "steps": [
    {
      "step_id": "step_1",
      "agent": "research_agent",
      "task": "what this step does",
      "depends_on": [],
      "requires_human_approval": false,
      "estimated_tokens": 500
    }
  ],
  "total_steps": 1,
  "requires_approval": false
}

Rules:
- Always start with research_agent if the task needs domain knowledge
- Always include security_agent for production code or architecture reviews
- Mark requires_human_approval=true for steps that produce code/docs that go to production
- Order steps logically; parallel steps get the same depends_on list
"""


class PlannerAgent(BaseAgent):
    name = "PlannerAgent"
    agent_type = "planner"

    @property
    def system_prompt(self) -> str:
        return PLANNER_SYSTEM_PROMPT

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        user_request = state.get("user_request", "")
        workflow_type = state.get("workflow_type", "general")

        prompt = (
            f"Workflow type: {workflow_type}\n\n"
            f"User request:\n{user_request}\n\n"
            "Create the execution plan."
        )

        content, tokens = await self._call_llm(prompt)

        # Parse the JSON plan
        try:
            # Strip markdown fences if present
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            plan = json.loads(clean.strip())
        except json.JSONDecodeError:
            # Return raw content if JSON parsing fails — orchestrator handles gracefully
            plan = {"raw": content, "steps": []}

        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            structured_output=plan,
            tokens_used=tokens,
        )
