---
applyTo: "src/agents/**/*.py,src/mcp_servers/**/*.py"
---

# Microsoft Agent Framework + GitHub Copilot SDK conventions

## Imports

```python
from agent_framework import AgentResponse, FunctionTool, tool
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.generated.rpc import PermissionDecisionApproveOnce
from copilot.session import PermissionRequestResult

from src.shared.copilot import build_copilot_client
```

For MCP servers (FastMCP, not agents):

```python
from mcp.server.fastmcp import FastMCP
```

## Model

**Every agent in this repo uses `GitHubCopilotAgent` with `GitHubCopilotOptions(model="gpt-5.5")`.** Enforced — do not introduce `AzureOpenAIChatClient`, `OpenAIChatClient`, `GitHubCopilotChatClient`, or `ChatAgent(client=...)`. If a future lab needs a different model, add it via config but keep `gpt-5.5` as the default.

## Building an agent

`agent.py` exposes exactly one factory returning a `_RunnableAgent` adapter (so `make_app` only needs `.run(message)`):

```python
def _approve_all(_req: object, _ctx: dict[str, str]) -> PermissionRequestResult:
    return PermissionDecisionApproveOnce()


async def build_agent(settings: Settings) -> _RunnableAgent:
    agent = GitHubCopilotAgent(
        instructions=SYSTEM_PROMPT,
        client=build_copilot_client(),
        name="inventory",
        description="ZavaShop inventory specialist (...).",
        tools=list(TOOLS),               # usually [] — MCP is wired below
        default_options=GitHubCopilotOptions(
            model=settings.copilot_model,
            timeout=settings.copilot_timeout_seconds,
            on_permission_request=_approve_all,
            mcp_servers={
                "inventory": {
                    "type": "http",
                    "url": settings.inventory_mcp_url,
                    "tools": ["*"],
                    "timeout": int(settings.copilot_timeout_seconds * 1000),
                },
            },
        ),
    )
    return _RunnableAgent(agent=agent)
```

`client=build_copilot_client()` is mandatory so the lab `GITHUB_TOKEN` is passed explicitly to the Copilot SDK. `on_permission_request=_approve_all` is also mandatory. Without it the SDK denies every tool call and the LLM silently reports "all specialists rejected the request". `mcp_servers[*].timeout` is milliseconds, unlike `GitHubCopilotOptions.timeout`, which is seconds.

## The orchestrator (`src/agents/orchestrator/`)

- Same `GitHubCopilotAgent(... model="gpt-5.5" ...)` with `client=build_copilot_client()` — the `GITHUB_TOKEN` comes from Key Vault at runtime and is never checked in.
- Implements a MAF **Workflow** for the deterministic `/plan` endpoint. The LLM `/invoke` path uses four `@tool`-decorated A2A delegators (`ask_inventory`, `ask_supplier`, `ask_logistics`, `ask_pricing`).
- Wrap fan-out steps in `WorkflowBuilder` parallel edges so we can observe latency per branch.
- The orchestrator **also** needs `on_permission_request=_approve_all` — the `ask_*` function tools go through the same permission gate as MCP tools.

## Tools

Two flavours in this repo, with different rules:

### `@tool` (agent-side function tools — e.g. orchestrator's `ask_*`)

- Flat scalar parameters only (`goal: str`). **Do not** wrap in a Pydantic model — the Copilot SDK passes a raw `dict` and does not marshal it.
- Async.
- Docstring must include a one-line summary, `Args:`, `Returns:`.

```python
@tool(name="ask_inventory", description="Delegate a stock question to inventory.")
async def ask_inventory(goal: str) -> str:
    """Forward the goal verbatim to the inventory specialist.

    Args:
        goal: The goal text to forward.
    Returns:
        The specialist's plain-text `output` field.
    """
    resp = await client.invoke("inventory", goal)
    return resp.output
```

### `@mcp.tool()` (MCP-server-side tools — `src/mcp_servers/*/server.py`)

- Take and return a `pydantic.BaseModel` — the MCP server marshals dicts into models for you.
- Docstring rules same as above.

```python
@mcp.tool()
async def check_stock(req: StockQuery) -> StockReport:
    """Check current stock for a SKU at one or more locations.

    Args:
        req: SKU and list of location codes.
    Returns:
        Per-location quantity, reorder threshold, and stock-out ETA.
    """
    ...
```

## MCP servers

- One MCP server per backend system (`inventory`, `supplier`, `shipping`, `pricing`).
- Use `mcp.server.fastmcp.FastMCP`. Expose tools via `@mcp.tool()`.
- Each MCP server has its own Dockerfile and ACA deployment.
- Each MCP server exposes `/healthz`, `/readyz`, and streamable HTTP MCP on `/mcp`.

## Errors

- Tool failures → raise `agent_framework.ToolError` so the agent can self-correct.
- Model failures → bubble up; the FastAPI handler maps them to 502.

## Observability

- Use OpenTelemetry. The MAF tracer is configured in `src/shared/telemetry.py`. Import and call `setup_tracing()` once per process.
- Spans: `agent.run`, `agent.tool`, `mcp.call`. Attributes: `zavashop.sku`, `zavashop.store_id` when relevant.
