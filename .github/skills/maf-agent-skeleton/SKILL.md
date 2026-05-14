# Skill: MAF Agent Skeleton

Use this skill when generating any specialist agent under `src/agents/<name>/`.

## Reference layout

```
src/agents/<name>/
├── __init__.py
├── prompts.py
├── tools.py
├── agent.py
├── server.py
├── Dockerfile
└── tests/__init__.py
```

## `agent.py` template (specialist with MCP)

```python
from __future__ import annotations

from dataclasses import dataclass

from agent_framework import AgentResponse
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.session import PermissionRequestResult

from src.shared.settings import Settings
from .prompts import SYSTEM_PROMPT
from .tools import TOOLS  # usually empty: list[FunctionTool] = []


def _approve_all(_req: object, _ctx: dict[str, str]) -> PermissionRequestResult:
    return PermissionRequestResult(kind="approved")


@dataclass(frozen=True)
class _RunnableAgent:
    """Adapter satisfying the shared `make_app` `_Runnable` protocol."""
    agent: GitHubCopilotAgent

    async def run(self, message: str, /) -> AgentResponse[None]:
        return await self.agent.run(message)


async def build_agent(settings: Settings) -> _RunnableAgent:
    agent = GitHubCopilotAgent(
        instructions=SYSTEM_PROMPT,
        name="<name>",
        description="ZavaShop <name> specialist (...).",
        tools=list(TOOLS),
        default_options=GitHubCopilotOptions(
            model=settings.copilot_model,
            timeout=settings.copilot_timeout_seconds,
            on_permission_request=_approve_all,
            mcp_servers={
                "<key>": {
                    "type": "http",
                    "url": settings.<which>_mcp_url,
                    "tools": ["*"],
                    "timeout": int(settings.copilot_timeout_seconds),
                },
            },
        ),
    )
    return _RunnableAgent(agent=agent)
```

Rules:

- One `build_agent` per agent. Async. Returns the `_RunnableAgent` adapter — `make_app` only needs `.run(message)`.
- Settings is the only configuration source. No env reads inside `agent.py`.
- `GitHubCopilotAgent` + `GitHubCopilotOptions` is the only allowed chat surface. **No** `GitHubCopilotChatClient`, **no** `ChatAgent(client=...)`, **no** `MCPStreamableHTTPTool` — those do not exist in agent-framework 1.3.x.
- `on_permission_request=_approve_all` is mandatory; without it every tool call silently denies and the LLM hallucinates "all specialists rejected".
- For the orchestrator (no MCP), drop `mcp_servers` and put four `@tool`-decorated `async def ask_<peer>(goal: str)` functions in `agent.py` itself, each calling `A2AClient.invoke(...)`. Tool signatures must be flat scalars, never Pydantic models (the SDK passes a raw dict).

## `prompts.py` template

```python
SYSTEM_PROMPT = """\
You are <Name>Agent for ZavaShop. Role: <one sentence>.

Decision rules:
1. ...
2. ...

Refusal rules:
- Refuse <out-of-scope topic>; redirect to the right agent.
- Never invent SKUs, prices, or supplier names.

Output: a JSON object with keys {...}.
"""
```

## `server.py` template

```python
from src.shared.server import make_app
from .agent import build_agent

app = make_app(name="<name>", build=build_agent)
```

No business logic in `server.py`. Ever.

## `tools.py` rules

- Specialist agents normally export **`TOOLS: list[FunctionTool] = []`** — external I/O lives in their MCP server, not in `tools.py`.
- If a tool *is* defined locally (orchestrator's `ask_*` delegators), use `@tool` from `agent_framework`. Signature must be flat scalars (`goal: str`), not a Pydantic input — the Copilot SDK does not marshal dicts into models.
- Docstring must include a one-line summary, `Args:`, `Returns:`.
- Export the `TOOLS` list at the bottom — `agent.py` consumes it.

## Acceptance

```bash
uv run ruff check src/agents/<name>
uv run pyright src/agents/<name>
uv run python -c "from src.agents.<name>.agent import build_agent; print(build_agent)"
```
