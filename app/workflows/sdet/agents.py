"""
AI SDET Specialized Agents
Four agents for comprehensive AI-driven software testing.
"""
from __future__ import annotations

import re
from typing import Any

from app.agents.base import AgentResult, BaseAgent


# ── 1. Requirements Analyzer ───────────────────────────────────────────────

class RequirementsAnalyzerAgent(BaseAgent):
    name = "RequirementsAnalyzerAgent"
    agent_type = "research"

    @property
    def system_prompt(self) -> str:
        return """
You are a Requirements Analyzer for software testing.

Given a feature description, user story, or codebase, extract:

## Test Requirements

### Functional Requirements
- What the system must DO
- Each requirement numbered (FR-001, FR-002, ...)

### Non-Functional Requirements
- Performance, security, reliability constraints
- Each numbered (NFR-001, ...)

### Acceptance Criteria
- Given/When/Then format for each scenario

### Edge Cases
- Boundary conditions, empty inputs, concurrent operations, error states

### Test Data Requirements
- What data is needed, volume, formats, constraints

## Test Strategy
- Recommended test types: unit | integration | e2e | performance | security
- Priority order
- Estimated coverage targets
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        request = state.get("user_request", "")
        research = state.get("research_output", "")

        prompt = (
            f"Context from knowledge base:\n{research[:2000]}\n\n"
            f"Feature/System to test:\n{request}\n\n"
            "Extract test requirements and define test strategy."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=3000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )


# ── 2. Test Case Generator ────────────────────────────────────────────────

class TestCaseGeneratorAgent(BaseAgent):
    name = "TestCaseGeneratorAgent"
    agent_type = "qa"

    @property
    def system_prompt(self) -> str:
        return """
You are a Test Case Generator producing exhaustive pytest test suites.

Rules:
- Use pytest with async support (pytest-asyncio)
- Use parametrize for data-driven tests
- Use fixtures for setup/teardown
- Each test has a docstring: what, why, expected outcome
- Cover: happy path, edge cases, error cases, boundary conditions
- Include performance assertions where relevant

Output format:
```python
import pytest
from pytest import mark

# imports...

@pytest.fixture
def ...

class TestFeatureName:
    def test_happy_path(self, ...):
        \"\"\"What is being tested and why.\"\"\"
        # Arrange
        # Act
        # Assert

    @mark.parametrize("input,expected", [...])
    def test_edge_cases(self, input, expected):
        ...
```
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        requirements = state.get("research_output", "")
        code = state.get("coding_output", "")

        prompt = (
            f"Test requirements:\n{requirements[:2000]}\n\n"
            f"Code to test:\n{code[:3000]}\n\n"
            "Generate a comprehensive pytest test suite."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=8000)

        # Extract test code blocks
        tests = re.findall(r"```python\n(.*?)```", content, re.DOTALL)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            structured_output={"test_files": tests, "count": len(tests)},
            tokens_used=tokens,
        )


# ── 3. Playwright E2E Agent ────────────────────────────────────────────────

class PlaywrightAgent(BaseAgent):
    name = "PlaywrightAgent"
    agent_type = "qa"

    @property
    def system_prompt(self) -> str:
        return """
You are a Playwright E2E Test Automation Expert.

Generate production-ready Playwright tests in Python (playwright-pytest).

Rules:
- Use Page Object Model (POM) pattern
- Include fixtures for browser setup
- Test both desktop and mobile viewports
- Assert on: visibility, content, URLs, network responses
- Include screenshot on failure
- Use expect() assertions (not raw assert)
- Handle async properly with async/await

Structure:
```python
# conftest.py
import pytest
from playwright.async_api import async_playwright, Page, Browser

@pytest.fixture(scope="session")
async def browser():
    ...

# pages/page_name.py
class PageName:
    def __init__(self, page: Page):
        self.page = page
        # locators

    async def action(self):
        ...

# tests/test_e2e_feature.py
class TestFeatureE2E:
    async def test_scenario(self, page: Page):
        ...
```
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        requirements = state.get("research_output", "")
        feature = state.get("user_request", "")

        prompt = (
            f"Feature requirements:\n{requirements[:2000]}\n\n"
            f"Feature to test:\n{feature}\n\n"
            "Generate Playwright E2E tests with Page Object Model."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=6000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )


# ── 4. API Test Agent ─────────────────────────────────────────────────────

class APITestAgent(BaseAgent):
    name = "APITestAgent"
    agent_type = "qa"

    @property
    def system_prompt(self) -> str:
        return """
You are an API Testing Expert generating comprehensive API test suites.

Use httpx + pytest for async API tests.

Coverage required:
- All HTTP methods (GET, POST, PUT, PATCH, DELETE)
- Status codes: 200, 201, 400, 401, 403, 404, 422, 500
- Request validation (missing fields, wrong types, boundary values)
- Response schema validation
- Authentication flows
- Rate limiting behavior
- Concurrent request handling

Output format:
```python
import pytest
import httpx
from pytest import mark

BASE_URL = "http://localhost:8000"

@pytest.fixture
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        yield c

class TestEndpointName:
    async def test_success(self, client):
        \"\"\"Test description\"\"\"
        response = await client.post("/endpoint", json={...})
        assert response.status_code == 200
        data = response.json()
        assert "field" in data
```
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        requirements = state.get("research_output", "")
        feature = state.get("user_request", "")

        prompt = (
            f"API requirements:\n{requirements[:2000]}\n\n"
            f"API to test:\n{feature}\n\n"
            "Generate comprehensive API test suite with httpx + pytest."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=6000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )


# ── 5. Defect Analyzer ─────────────────────────────────────────────────────

class DefectAnalyzerAgent(BaseAgent):
    name = "DefectAnalyzerAgent"
    agent_type = "security"

    @property
    def system_prompt(self) -> str:
        return """
You are a Defect Analysis Agent.

Given test results, failure logs, or bug reports, produce:

## Defect Analysis Report

### Root Cause Analysis
For each failure:
- **Defect ID**: D-001
- **Title**: [descriptive title]
- **Severity**: CRITICAL | HIGH | MEDIUM | LOW
- **Root Cause**: [technical explanation]
- **Affected Components**: [list]
- **Reproduction Steps**: [numbered steps]
- **Fix Recommendation**: [concrete code fix or configuration change]

### Defect Summary
| ID | Title | Severity | Component | Status |
|---|---|---|---|---|

### Regression Risk
Components at risk of regression if defects are fixed naively.

### Priority Queue
Ordered fix priority with rationale.
"""

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        test_results = state.get("qa_output", "")
        code = state.get("coding_output", "")
        request = state.get("user_request", "")

        prompt = (
            f"Test results / failure logs:\n{test_results[:3000]}\n\n"
            f"Code context:\n{code[:1000]}\n\n"
            f"Additional context: {request}\n\n"
            "Analyze defects and produce root cause report."
        )
        content, tokens = await self._call_llm(prompt, max_tokens=4000)
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            tokens_used=tokens,
        )
