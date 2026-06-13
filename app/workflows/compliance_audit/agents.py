"""
Compliance Audit Specialized Agents
Four agents tailored for regulatory / standards compliance audits
(e.g. aviation FAA/EASA, SOC 2, ISO 27001, GDPR, HIPAA).
"""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentResult, BaseAgent


# 1. Policy Mapping Agent

class PolicyMappingAgent(BaseAgent):
    name = "PolicyMappingAgent"
    agent_type = "research"  # maps to research slot for DB

    @property
    def system_prompt(self) -> str:
        return """
You are a Policy Mapping Agent for regulatory compliance audits.

Your task: Given an audit scope and retrieved regulatory/standards content,
map the scope to the specific regulations, controls, and clauses that apply.

Output format:

## Audit Scope Summary
[1-2 sentences restating what is being audited]

## Applicable Regulations & Standards
For each applicable regulation/standard:
- Name & section/clause reference
- Why it applies to this scope
- Required controls or evidence

## Control Matrix
| Control ID | Requirement | Source | Priority |
|---|---|---|---|
| CTL-001 | ... | FAA Part 145 / SOC 2 CC6.1 / etc. | HIGH |

## Evidence Required
List the specific documents, logs, records, or artifacts that should be
collected to demonstrate compliance with each control.
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        scope = state.get("user_request", "")
        regulations = state.get("research_output", "")

        prompt = (
            f"Retrieved regulatory/standards content:\n{regulations[:3000]}\n\n"
            f"Audit scope:\n{scope}\n\n"
            "Map the audit scope to applicable regulations, controls, "
            "and required evidence."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=4000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )


# 2. Evidence Analysis Agent

class EvidenceAnalysisAgent(BaseAgent):
    name = "EvidenceAnalysisAgent"
    agent_type = "coding"  # reuse coding slot for analysis output

    @property
    def system_prompt(self) -> str:
        return """
You are an Evidence Analysis Agent for compliance audits.

Your task: Given a control matrix and the evidence/process description provided
by the auditee, assess each control as Met, Partially Met, or Not Met.

Output format:

## Evidence Assessment

### Control: [Control ID - Requirement]
- Status: Met | Partially Met | Not Met | Not Applicable
- Evidence reviewed: [what was provided/described]
- Gap (if any): [specific gap description]
- Severity if gap: Critical | Major | Minor | Observation

## Summary Table
| Control ID | Status | Severity |
|---|---|---|
| CTL-001 | Partially Met | Major |

## Findings Requiring Remediation
Numbered list of all Partially Met / Not Met controls with a brief
description of what's missing.
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        control_matrix = state.get("research_output_secondary", "") or state.get("documentation_output", "")
        policy_mapping = state.get("research_output", "")
        scope = state.get("user_request", "")

        prompt = (
            f"Audit scope and evidence/process description:\n{scope}\n\n"
            f"Policy mapping & control matrix:\n{policy_mapping[:3000]}\n\n"
            "Assess each control's compliance status based on the evidence "
            "described in the audit scope. Where evidence isn't described, "
            "mark the control as Not Met or Not Applicable as appropriate."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=4000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )


# 3. Compliance Risk Agent

class ComplianceRiskAgent(BaseAgent):
    name = "ComplianceRiskAgent"
    agent_type = "security"  # reuse security slot for risk scoring

    @property
    def system_prompt(self) -> str:
        return """
You are a Compliance Risk Scoring Agent.

Evaluate the overall compliance posture based on the evidence assessment
and produce a risk score.

Output MUST include a JSON block at the end:
```json
{
  "risk_score": 35,
  "risk_level": "MEDIUM",
  "critical_findings": 0,
  "major_findings": 2,
  "minor_findings": 3,
  "recommendation": "remediate_before_certification | conditional_pass | pass",
  "top_findings": ["finding 1", "finding 2", "finding 3"]
}
```

Risk score: 0 (fully compliant) -> 100 (severe non-compliance)
- 0-20: LOW - minor observations only
- 21-40: MEDIUM - remediation recommended before certification
- 41-70: HIGH - significant gaps, conditional pass at most
- 71-100: CRITICAL - audit fails, do not certify
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        evidence = state.get("coding_output", "")
        policy_mapping = state.get("research_output", "")

        prompt = (
            f"Policy mapping & control matrix:\n{policy_mapping[:2000]}\n\n"
            f"Evidence assessment:\n{evidence[:2000]}\n\n"
            "Assess overall compliance risk and produce the risk score JSON."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=2000)

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
                    "top_findings": parsed.get("top_findings", []),
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


# 4. Audit Report Agent

class AuditReportAgent(BaseAgent):
    name = "AuditReportAgent"
    agent_type = "documentation"

    @property
    def system_prompt(self) -> str:
        return """
You are an Audit Report Agent producing executive-level compliance audit reports.

Your output must be a polished, actionable report:

# Compliance Audit Report

## Executive Summary
[3-4 sentences suitable for leadership/board consumption]

## Audit Scope
[What was audited and against which regulations/standards]

## Compliance Risk
Risk Score: X/100 | Level: LOW | MEDIUM | HIGH | CRITICAL
Recommendation: PASS | CONDITIONAL PASS | REMEDIATE BEFORE CERTIFICATION | FAIL

## Findings Summary
| Control ID | Status | Severity | Remediation Owner (suggested) |
|---|---|---|---|

## Detailed Findings & Remediation Plan
For each finding: description, root cause (if evident), and a specific,
actionable remediation step with a suggested timeline.

## Certification Recommendation
[Clear pass/conditional/fail statement with rationale]

---
*Generated by NexusAI Compliance Audit Agent*
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        policy_mapping = state.get("research_output", "")
        evidence = state.get("coding_output", "")
        risk = state.get("security_output", "")

        prompt = (
            f"Policy mapping & control matrix:\n{policy_mapping[:1500]}\n\n"
            f"Evidence assessment:\n{evidence[:2000]}\n\n"
            f"Risk assessment:\n{risk[:1000]}\n\n"
            "Produce the executive compliance audit report."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=3500)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )
