# GitHub Copilot — always-on instructions

You are assisting on **ZavaShop**, a multi-agent retail supply-chain demo deployed to **AKS + Azure Container Apps**, written in **Python 3.11+** with **Microsoft Agent Framework** and the **GitHub Copilot SDK**.

**Before generating code, read `AGENTS.md` at the repo root.** It is the source of truth.

## Hard rules

1. Python 3.11+, fully typed, **async-first**. No blocking I/O inside coroutines.
2. Use `uv` for dependency management, `ruff` for lint/format, `pyright --strict` for types, `pytest` for tests.
3. Use `structlog` for logging — never `print`.
4. Data crossing a process boundary → `pydantic.BaseModel`.
5. Agent folder layout: `agent.py`, `tools.py`, `prompts.py`, `server.py`, `tests/`.
6. **All agents** use `GitHubCopilotAgent` from `agent_framework.github` with `GitHubCopilotOptions(model="gpt-5.5", timeout=settings.copilot_timeout_seconds, on_permission_request=_approve_all, mcp_servers={...})`. **Never** import `GitHubCopilotChatClient`, `ChatAgent`, or `MCPStreamableHTTPTool` — they do not exist in this repo's agent-framework version.
7. External I/O lives in MCP servers, not agent code.
8. Auth = Workload Identity + `DefaultAzureCredential`. No secrets in env.
9. K8s/ACA images are tagged with the git SHA, never `:latest`.

## Style cues

- Prefer `match` over chains of `isinstance`.
- Use `Self` from `typing`, `|` unions, `list[T]` not `List[T]`.
- Pydantic v2 (`model_config = ConfigDict(frozen=True)`).
- Imports: stdlib → third-party → first-party, separated by blank lines.

## When generating an agent

Always include:
- `SYSTEM_PROMPT` constant in `prompts.py` — terse, role-scoped, with explicit refusal rules.
- A `build_agent()` factory in `agent.py` returning a `ChatAgent`.
- A FastAPI app in `server.py` with `/healthz`, `/readyz`, `/invoke`.
- A `Dockerfile` based on `python:3.11-slim` with non-root user, multi-stage build.
- A test file mocking the model with `MockChatClient`.

## When generating infra

- Helm chart values: never inline secrets, always reference `secretProviderClass`.
- Bicep modules: pass `userAssignedIdentityId`, never create role assignments inline without a comment.
- All resources tagged `project=zavashop`, `lab=<lab-number>`.

## Refuse to do

- Add a new top-level dependency without justifying it in the chat.
- Generate code that calls a model without an explicit timeout.
- Write Bash one-liners > 80 chars in lab READMEs — split into multiple lines.
