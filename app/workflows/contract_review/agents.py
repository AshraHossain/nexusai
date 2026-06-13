"""
Contract Review Specialized Agents
Four agents tailored for legal contract analysis.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentResult, BaseAgent


# ── 1. Contract Analysis Agent ─────────────────────────────────────────────

class ContractAnalysisAgent(BaseAgent):
    name = "ContractAnalysisAgent"
    agent_type = "coding"  # maps to coding agent type for DB

    @property
    def system_prompt(self) -> str:
        return """
You are a specialized Contract Analysis Agent.

Your task: Extract and structure all meaningful elements from a contract.

Output the following sections:

## Parties
List all parties with their roles.

## Key Obligations
For each party, list their primary obligations.

## Critical Clauses
Identify: limitation of liability, indemnification, IP ownership,
termination, dispute resolution, governing law, confidentiality.

## Non-Standard Terms
Flag any unusual, one-sided, or potentially problematic clauses.

## Timeline & Deadlines
Extract all dates, deadlines, and notice periods.

## Financial Terms
Payment terms, penalties, caps on liability.

Be precise. Quote the contract text where relevant.
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        contract = state.get("user_request", "")
        research = state.get("research_output", "")

        prompt = (
            f"Relevant legal precedents and standards:\n{research[:2000]}\n\n"
            f"Contract to analyze:\n{contract}\n\n"
            "Extract and structure all contract elements."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=5000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )


# ── 2. Legal Research Agent ────────────────────────────────────────────────

class LegalResearchAgent(BaseAgent):
    name = "LegalResearchAgent"
    agent_type = "research"

    @property
    def system_prompt(self) -> str:
        return """
You are a Legal Research Agent specializing in contract compliance.

Your task: Compare the analyzed contract clauses against:
- Retrieved legal precedents and standards
- Applicable regulations and statutes
- Industry-standard contract norms

Output format:

## Compliance Analysis

### Clause: [Name]
- Standard practice: [what is normal]
- Contract says: [what this contract says]
- Deviation: [favorable | unfavorable | neutral]
- Risk: [LOW | MEDIUM | HIGH | CRITICAL]
- Recommendation: [specific action]

## Regulatory Red Flags
List any clauses that may violate applicable laws or regulations.

## Overall Legal Assessment
[2-3 paragraph executive assessment]
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        analysis = state.get("coding_output", "")
        research = state.get("research_output", "")

        prompt = (
            f"Legal standards and precedents:\n{research[:3000]}\n\n"
            f"Contract analysis:\n{analysis[:3000]}\n\n"
            "Perform compliance analysis against retrieved standards."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=4000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )


# ── 3. Contract Risk Agent ─────────────────────────────────────────────────

class ContractRiskAgent(BaseAgent):
    name = "ContractRiskAgent"
    agent_type = "security"

    @property
    def system_prompt(self) -> str:
        return """
You are a Contract Risk Assessment Agent.

Evaluate the contract for business, legal, and financial risk.

Output MUST include a JSON block at the end:
```json
{
  "risk_score": 35,
  "risk_level": "MEDIUM",
  "critical_issues": 0,
  "high_issues": 2,
  "medium_issues": 3,
  "recommendation": "negotiate | accept | reject",
  "top_risks": ["risk 1", "risk 2", "risk 3"]
}
```

Risk score: 0 (no risk) → 100 (reject immediately)
- 0-20: LOW — acceptable, minor negotiation
- 21-40: MEDIUM — negotiate specific clauses
- 41-70: HIGH — significant renegotiation required
- 71-100: CRITICAL — recommend rejection
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        analysis = state.get("coding_output", "")
        legal = state.get("architecture_output", "")

        prompt = (
            f"Contract analysis:\n{analysis[:2000]}\n\n"
            f"Legal compliance findings:\n{legal[:2000]}\n\n"
            "Assess overall contract risk and produce risk score JSON."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=2000)

        # Extract JSON risk data
        import json, re
        risk_data = {"risk_score": 25, "passed": True}
        match = re.search(r"```json\n(.*?)```", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                risk_data = {
                    "risk_score": parsed.get("risk_score", 25),
                    "risk_level": parsed.get("risk_level", "MEDIUM"),
                    "passed": parsed.get("risk_score", 25) < 70,
                    "recommendation": parsed.get("recommendation", "review"),
                    "top_risks": parsed.get("top_risks", []),
                }
            except json.JSONDecodeError:
                pass

        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            structured_output=risk_data,
            tokens_used=tokens,
        )


# ── 4. Contract Summary Agent ─────────────────────────────────────────────

class ContractSummaryAgent(BaseAgent):
    name = "ContractSummaryAgent"
    agent_type = "documentation"

    @property
    def system_prompt(self) -> str:
        return """
You are a Contract Summary Agent producing executive-level contract briefings.

Your output must be a polished, actionable report:

# Contract Review Report

## Executive Summary
[3-4 sentences suitable for C-suite consumption]

## Risk Assessment
Risk Score: X/100 | Level: LOW | MEDIUM | HIGH | CRITICAL
Recommendation: ACCEPT | NEGOTIATE | REJECT

## Key Issues Requiring Attention
Numbered list of the most important issues, with specific clause references.

## Recommended Negotiation Points
For each issue: current language → proposed alternative language.

## Approval Recommendation
[Clear yes/negotiate/no with rationale]

---
*Generated by NexusAI Contract Review Agent*
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        analysis = state.get("coding_output", "")
        legal = state.get("architecture_output", "")
        risk = state.get("security_output", "")

        prompt = (
            f"Contract analysis:\n{analysis[:2000]}\n\n"
            f"Legal findings:\n{legal[:2000]}\n\n"
            f"Risk assessment:\n{risk[:1000]}\n\n"
            "Produce the executive contract review report."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=3000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )
