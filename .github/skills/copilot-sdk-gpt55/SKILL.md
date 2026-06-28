# Skill: GitHub Copilot SDK on `gpt-5.5`

> Reflects the actual `agent-framework[github-copilot]` 1.3.x API installed in this repo. Earlier `GitHubCopilotChatClient` / `ChatAgent(client=...)` syntax is **not** valid here.

## The two imports

```python
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.generated.rpc import PermissionDecisionApproveOnce
from copilot.session import PermissionRequestResult

from src.shared.copilot import build_copilot_client
```

## The one builder shape

```python
def _approve_all(_request: object, _context: dict[str, str]) -> PermissionRequestResult:
    return PermissionDecisionApproveOnce()


async def build_agent(settings: Settings) -> _RunnableAgent:
    agent = GitHubCopilotAgent(
        instructions=SYSTEM_PROMPT,
        client=build_copilot_client(),
        name="<name>",
        description="...",
        tools=list(TOOLS),                       # local @tool functions, NEVER MCP
        default_options=GitHubCopilotOptions(
            model=settings.copilot_model,        # default "gpt-5.5"
            timeout=settings.copilot_timeout_seconds,
            on_permission_request=_approve_all,  # MANDATORY — see §Permissions
            mcp_servers={                        # specialists only; orchestrator omits this
                "<key>": {
                    "type": "http",
                    "url": settings.<which>_mcp_url,
                    "tools": ["*"],
                    "timeout": int(settings.copilot_timeout_seconds * 1000),
                },
            },
        ),
    )
    return _RunnableAgent(agent=agent)
```

`_RunnableAgent` is a `@dataclass(frozen=True)` adapter exposing `async def run(self, message: str) -> AgentResponse[None]`. The shared `make_app` calls `.run(req.goal)` on it.

## Permissions (do NOT skip)

The Copilot SDK runs every tool call through a permission gate. The handler must return `PermissionDecisionApproveOnce()`. Without a handler, every call returns:

> `Permission denied and could not request permission from user`

This bug is silent — the LLM faithfully reports "all specialists rejected the request" with zero stack trace. Always wire `on_permission_request=_approve_all` for both MCP tools (specialists) and `@tool` function tools (orchestrator).

## Tool signatures — flat scalars, not Pydantic

The SDK injects tool arguments as a raw `dict` and does **not** marshal them into Pydantic models. A signature like `async def ask_inventory(req: _AskRequest)` raises `'dict' object has no attribute 'goal'` at call time.

✅ Correct:
```python
@tool(name="ask_inventory", description="...")
async def ask_inventory(goal: str) -> str:
    """...Args: goal: ... Returns: ..."""
```

❌ Wrong:
```python
@tool(...)
async def ask_inventory(req: _AskRequest) -> str: ...
```

Pydantic models stay valid for `models.py` (process-boundary types) and FastMCP `@mcp.tool()` (the MCP server itself does marshal).

## MCP wiring

MCP is configured **inside `GitHubCopilotOptions(mcp_servers={...})`**, not via the legacy `MCPStreamableHTTPTool` class. If a generated file imports `MCPStreamableHTTPTool`, reject it. Specialist `tools.py` should expose an empty `TOOLS: list[FunctionTool] = []` — every external call is an MCP tool.

## Authentication

- Local dev: fine-grained PAT in `GITHUB_TOKEN`. `build_copilot_client()` passes it explicitly to `CopilotClient(github_token=..., use_logged_in_user=False)`. `docker-compose.yml` fails fast (`${GITHUB_TOKEN:?...}`) if it's not exported — required even for `docker compose ps` / `down`.
- AKS: Key Vault → Secrets Store CSI → `GITHUB_TOKEN` env. Pod SA is federated to a UAMI (Workload Identity).
- ACA: Key Vault `secretref` → `GITHUB_TOKEN`. Container app uses a UAMI.

## Timeouts (hard rules)

Three separate timeouts must all be sized for chained tool calls:

| Knob | Where | Min value | Reason |
|---|---|---|---|
| `GitHubCopilotOptions.timeout` | per-agent | **120 s** | Orchestrator may chain 4 sequential `ask_*` tool calls (10–25 s each). 30 s is too tight and surfaces as `Timeout after 30.0s waiting for session.idle`. |
| `mcp_servers[*].timeout` | specialist agents | `int(seconds * 1000)` | The Copilot SDK's `MCPHTTPServerConfig.timeout` is milliseconds, not seconds. |
| `A2AClient` httpx timeout | orchestrator | `connect=10, read=120, write=30, pool=10` | An A2A POST `/invoke` waits on the peer's full LLM run. 30 s read surfaces as `httpx.ReadTimeout`. |

The lab default is `ZAVA_COPILOT_TIMEOUT_SECONDS=120` (set in `docker-compose.yml::x-agent-env`).

## Container runtime gotcha

The Copilot SDK extracts its bundled Node CLI into `$HOME/.cache` on first call. A non-root container whose `HOME` defaults to `/app` (root-owned) fails with:

```
Failed to extract bundled package: Error: EACCES: permission denied, mkdir '/app/.cache'
```

Fix in the runtime stage of `src/Dockerfile.base`:

```dockerfile
ENV HOME=/home/zava XDG_CACHE_HOME=/home/zava/.cache
RUN useradd --uid 10001 --home /home/zava ... \
 && mkdir -p /home/zava/.cache /app \
 && chown -R 10001:10001 /home/zava /app
```

## Forbidden in this repo

| ❌ Do not import | Reason |
|---|---|
| `GitHubCopilotChatClient` | Does not exist in agent-framework 1.3.x — only `GitHubCopilotAgent` |
| `ChatAgent(client=GitHubCopilotChatClient(...))` | Old API |
| `MCPStreamableHTTPTool` | MCP is wired via `GitHubCopilotOptions(mcp_servers=...)` |
| `OpenAIChatClient`, `AzureOpenAIChatClient` | Repo is Copilot-only |
| Anything reading `OPENAI_API_KEY` | Same |

If a generated file contains any of these, reject it.

## Logging fields

Every `agent.run.*` log line must bind:

- `agent.name`
- `agent.run_id`
- `agent.span_id`

Use `structlog.contextvars.bind_contextvars(...)` in the FastAPI request scope (the shared `make_app` does this for you).
