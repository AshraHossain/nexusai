"""
Coding Agent
Generates production-quality code, scaffolds architectures,
refactors, and fixes bugs across Python, TypeScript, Java, and Go.
"""
from __future__ import annotations

import re
from typing import Any

from app.agents.base import AgentResult, BaseAgent


CODING_SYSTEM_PROMPT = """
You are the Coding Agent for NexusAI — an expert software engineer.

Capabilities:
- Code generation (Python, TypeScript, Java, Go)
- Architecture scaffolding
- Refactoring and bug fixing
- Test-driven development

Output format:
Always produce:
1. A brief explanation of the approach
2. Complete, runnable code (no placeholders, no TODOs unless noted)
3. Usage instructions

Code quality rules:
- Add docstrings/comments for non-obvious logic
- Use type hints (Python) or types (TS/Go/Java)
- Follow language idioms and best practices
- Handle errors explicitly
- Never expose secrets or credentials in code

When producing multiple files, use this structure:
## File: path/to/file.py
```python
# code here
```
"""


class CodingAgent(BaseAgent):
    name = "CodingAgent"
    agent_type = "coding"

    @property
    def system_prompt(self) -> str:
        return CODING_SYSTEM_PROMPT

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        task = state.get("current_task", state.get("user_request", ""))
        research_context = state.get("research_output", "")
        language = state.get("preferred_language", "Python")

        prompt = f"Language preference: {language}\n\n"

        if research_context:
            prompt += f"Research context and requirements:\n{research_context}\n\n"

        prompt += f"Coding task:\n{task}\n\nGenerate production-quality code."

        content, tokens = await self._call_llm(prompt, max_tokens=6000)

        # Extract code blocks for structured output
        code_blocks = re.findall(r"```(\w+)?\n(.*?)```", content, re.DOTALL)
        files = [
            {"language": lang or "text", "code": code.strip()}
            for lang, code in code_blocks
        ]

        return AgentResult(
            agent_name=self.name,
            success=True,
            output=content,
            structured_output={
                "files": files,
                "file_count": len(files),
                "language": language,
            },
            tokens_used=tokens,
        )
