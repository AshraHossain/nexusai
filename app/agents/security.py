"""
Security Agent
Performs deep security review of code and architecture via SentinelAI.
Produces structured risk reports with remediation guidance.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentResult, BaseAgent
from app.integrations.sentinelai import get_sentinel_client


SECURITY_SYSTEM_PROMPT = """
You are the Security Agent for NexusAI — an expert in application security.

Your role:
- Review code, architecture, and prompts for security vulnerabilities
- Classify findings by severity: CRITICAL | HIGH | MEDIUM | LOW | INFO
- Provide concrete remediation for every finding
- Check OWASP Top 10, CWE, and NIST guidelines
- Identify: injection flaws, insecure dependencies, secrets in code,
  auth weaknesses, broken access control, SSRF, XXE, deserialization issues

Output format:
## Security Review Report

### Executive Summary
[2-3 sentences on overall posture]

### Findings

| ID | Severity | Title | CWE | Status |
|---|---|---|---|---|
| SEC-001 | CRITICAL | ... | CWE-89 | Open |

### Detailed Findings
For each finding:
**SEC-001 — [Title]**
- Severity: CRITICAL
- CWE: CWE-89
- Location: [file:line or component]
- Description: [what and why it's a risk]
- Remediation: [specific fix with code example]

### Risk Score: X/100
"""


class SecurityAgent(BaseAgent):
    name = "SecurityAgent"
    agent_type = "security"

    @property
    def system_prompt(self) -> str:
        return SECURITY_SYSTEM_PROMPT

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        task = state.get("current_task", state.get("user_request", ""))
        code_output = state.get("coding_output", "")
        architecture = state.get("architecture_output", "")
        workflow_id = state.get("workflow_id")

        # Build review target
        review_target = ""
        if code_output:
            review_target += f"\n### Code to Review:\n{code_output}"
        if architecture:
            review_target += f"\n### Architecture to Review:\n{architecture}"
        if not review_target:
            review_target = f"\n### Description:\n{task}"

        # Get SentinelAI risk score for the content
        sentinel = get_sentinel_client()
        risk_result = await sentinel.risk_score(
            content=review_target,
            content_type="code_review",
            workflow_id=workflow_id,
        )

        prompt = (
            f"SentinelAI Pre-scan Risk Score: {risk_result.risk_score}/100\n"
            f"Pre-scan Flags: {', '.join(risk_result.flags) or 'none'}\n\n"
            f"Review target:{review_target}\n\n"
            f"Task: {task}\n\n"
            "Perform a comprehensive security review."
        )

        content, tokens = await self._call_llm(prompt, max_tokens=5000)

        # Extract risk score from output
        import re
        score_match = re.search(r"Risk Score:\s*(\d+)/100", content)
        final_score = int(score_match.group(1)) if score_match else risk_result.risk_score

        # Count findings by severity
        critical = len(re.findall(r"\|\s*CRITICAL\s*\|", content))
        high = len(re.findall(r"\|\s*HIGH\s*\|", content))
        medium = len(re.findall(r"\|\s*MEDIUM\s*\|", content))

        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            structured_output={
                "risk_score": final_score,
                "sentinel_risk_score": risk_result.risk_score,
                "sentinel_flags": risk_result.flags,
                "findings": {
                    "critical": critical,
                    "high": high,
                    "medium": medium,
                },
                "passed": final_score < 50 and critical == 0,
            },
            tokens_used=tokens,
        )
