"""
QA Agent
Generates comprehensive test suites: unit tests, Playwright E2E,
Selenium, API tests, and performance tests.
"""
from __future__ import annotations

import re
from typing import Any

from app.agents.base import AgentResult, BaseAgent


QA_SYSTEM_PROMPT = """
You are the QA Agent for NexusAI — an expert in software quality assurance.

Capabilities:
- Unit test generation (pytest, Jest, JUnit, Go testing)
- Playwright E2E automation
- Selenium automation
- API test suites (httpx, supertest, REST Assured)
- Performance testing (Locust, k6)

Test quality rules:
- Arrange-Act-Assert structure
- Cover happy paths AND edge cases AND error paths
- Use fixtures and parametrize where applicable
- Include async test patterns where relevant
- Make tests independent — no shared mutable state
- Add clear docstrings explaining WHAT is being tested and WHY

Output format:
For each test file:
## Test: descriptive-test-name.py (or .spec.ts, etc.)
```python
# test code
```

Then provide a coverage summary table:
| Category | Tests | Coverage |
|---|---|---|
"""


class QAAgent(BaseAgent):
    name = "QAAgent"
    agent_type = "qa"

    @property
    def system_prompt(self) -> str:
        return QA_SYSTEM_PROMPT

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        task = state.get("current_task", state.get("user_request", ""))
        code_output = state.get("coding_output", "")
        test_type = state.get("test_type", "comprehensive")  # unit|e2e|api|performance|comprehensive

        prompt = f"Test type: {test_type}\n\n"

        if code_output:
            prompt += f"Code to test:\n{code_output}\n\n"

        prompt += (
            f"QA task:\n{task}\n\n"
            "Generate a comprehensive test suite with high coverage."
        )

        content, tokens = await self._call_llm(prompt, max_tokens=8000)

        # Extract test files
        test_files = re.findall(r"##\s*Test:\s*(.+?)\n```\w*\n(.*?)```", content, re.DOTALL)
        files = [{"name": name.strip(), "code": code.strip()} for name, code in test_files]

        # Fallback: extract any code blocks
        if not files:
            code_blocks = re.findall(r"```(\w+)?\n(.*?)```", content, re.DOTALL)
            files = [{"name": f"test_{i}.{lang or 'py'}", "code": code.strip()}
                     for i, (lang, code) in enumerate(code_blocks)]

        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            structured_output={
                "test_files": files,
                "test_count": len(files),
                "test_type": test_type,
            },
            tokens_used=tokens,
        )
