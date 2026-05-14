# AGENTS.md — House rules for AI coding agents

> Inspired by [`microsoft/agent-framework/python/AGENTS.md`](https://github.com/microsoft/agent-framework/tree/main/python). Read this before you write any code in this repo — whether you are a human, GitHub Copilot, or the Copilot Coding Agent.

## 1. Project Context

This repository implements **ZavaShop**, a multi-agent retail supply-chain demo. It runs on **AKS** (long-lived orchestrator) and **Azure Container Apps** (event-driven specialist agents). Agents are built with **Microsoft Agent Framework (MAF)** and the **GitHub Copilot SDK** Python provider.

Treat every change as production-style: typed, tested, observable.

## 1.1 How we build: GitHub Copilot Custom Agents

This repo is delivered through **GitHub Copilot Custom Agents**. Every code change flows through one of the six agents below. Each agent owns a slice of the repo and has its own tools, skills, and refusal rules. Invoke an agent by typing `/<name>` in Copilot Chat.

| Phase | Agent | Owns | File |
|---|---|---|---|
| Requirements | `requirements-analyst` | `specs/*.md` | `.github/agents/requirements-analyst.agent.md` |
| MCP impl | `mcp-builder` | `src/mcp_servers/*` | `.github/agents/mcp-builder.agent.md` |
| Agent impl | `agent-builder` | `src/agents/<specialist>/*` | `.github/agents/agent-builder.agent.md` |
| Orchestration | `orchestrator-architect` | `src/agents/orchestrator/*`, `src/shared/*`, `docker-compose.yml` | `.github/agents/orchestrator-architect.agent.md` |
| Tests | `test-author` | `tests/**` | `.github/agents/test-author.agent.md` |
| Deploy | `deploy-engineer` | `infra/**`, `.github/workflows/**` | `.github/agents/deploy-engineer.agent.md` |

Workflow prompts that chain the agents live in `.github/prompts/`:

- `feature-from-issue.prompt.md` — issue → spec → code → tests → PR → deploy.
- `spec-to-code.prompt.md` — drive an existing spec through code + tests.
- `ship-it.prompt.md` — roll the current SHA to ACR + ACA + AKS.

Shared, agent-agnostic knowledge lives in `.github/skills/<skill>/SKILL.md` (inspired by the [agent-framework Python skills](https://github.com/microsoft/agent-framework/tree/main/python/.github/skills) layout). Every agent lists which skills it must consult before writing code.

**Hard rule for humans:** every code change must be authored by one of the six agents above. Pick the agent whose `Owns` cell matches the path you are touching, and invoke it with `/<name>`.

## 2. Languages & Tooling

- **Python 3.11+** only. Use modern syntax (`match`, `|` unions, `Self`).
- Package manager: **`uv`** (`uv sync`, `uv run`, `uv add`).
- Lint + format: **`ruff`** (config in `pyproject.toml`). Line length **120**.
- Type-check: **`pyright`** in `strict` mode for `src/`.
- Tests: **`pytest`** + `pytest-asyncio`. Coverage target ≥ 80% for `src/agents/*`.

Run `uv run poe check` (alias for `ruff check && ruff format --check && pyright && pytest`) before every commit.

## 3. Code style

- **Async-first.** Every agent entrypoint is `async def`. Never call blocking I/O from agent code — wrap in `asyncio.to_thread` if you must.
- Prefer **`pydantic.BaseModel`** for any data crossing a process boundary (HTTP, A2A, MCP, queue).
- Public functions need type hints. **No `Any`** unless commented `# noqa: ANN401 — reason`.
- Logging via `structlog` only. No `print`. Every agent emits `agent.name`, `agent.run_id`, `agent.span_id` fields.
- One agent = one folder under `src/agents/<agent_name>/` with this layout:

  ```
  src/agents/<agent_name>/
  ├── __init__.py
  ├── agent.py          # build_agent() factory returning a MAF ChatAgent
  ├── tools.py          # @ai_function tools the agent owns
  ├── prompts.py        # SYSTEM_PROMPT constant + few-shots
  ├── server.py         # FastAPI / A2A server entrypoint
  └── tests/
  ```

## 4. Agent rules

- **All agents** (orchestrator and specialists) use the **GitHub Copilot SDK** provider (`GitHubCopilotChatClient`) with **`model="gpt-5.5"`**. No other model or provider is permitted in this repo.
- The GitHub token used by the Copilot SDK is mounted via Workload Identity Federation (AKS) or Key Vault → `secretref` (ACA). Never read it from a checked-in file.
- Specialist agents communicate via **A2A** (HTTP) — never import each other's Python modules.
- Tools that touch external systems (DB, supplier API) live in a **MCP server**, not inline in the agent. Agents consume them via `MCPStreamableHTTPTool`.
- Every `@ai_function` tool docstring must contain: a one-line summary, an `Args:` block, and a `Returns:` block. Copilot uses these as the model-facing description.

## 5. Kubernetes & ACA conventions

- Container images: `acr.azurecr.io/zavashop/<agent>:<git-sha>`. No `:latest` in any manifest.
- Every agent container exposes:
  - `GET /healthz` — liveness, returns 200 if the chat client init succeeded
  - `GET /readyz` — readiness, returns 200 once MCP tools are connected
  - `POST /invoke` — A2A endpoint (Pydantic `InvokeRequest` / `InvokeResponse`)
- **Workload Identity** for Azure auth — no client secrets in env vars. Use `DefaultAzureCredential`.
- AKS manifests live in `infra/aks/helm/` (one Helm chart, one values file per agent).
- ACA manifests live in `infra/aca/` as `bicep` modules. Scale rule: `keda` HTTP, min 0, max 10.

## 6. Tests

- Unit tests mock the model with `agent_framework.testing.MockChatClient`.
- Integration tests run two agents over a real loopback A2A connection (`httpx.AsyncClient(transport=ASGITransport(...))`).
- Eval suite (`tests/evals/`) uses the MAF `evals` runner against a golden dataset of supply-chain scenarios.

## 7. Commits & PRs

- Conventional commits (`feat:`, `fix:`, `chore(infra):` …).
- A PR may only touch one of `{src/agents/*, src/mcp_servers/*, infra/*, labs/*}`. Cross-cutting changes need an issue first.
- The **GitHub Copilot Coding Agent** is allowed to open PRs against `src/` and `tests/` only — never against `infra/` without human review.

## 8. Secrets

- **Never** commit secrets. Use Key Vault → CSI driver on AKS, and `secretref` on ACA.
- The only env var carrying credentials is `AZURE_CLIENT_ID` (Workload Identity).

## 9. When in doubt

1. Re-read this file.
2. Check `.github/instructions/*.instructions.md` for the area you are editing.
3. Run `uv run poe check`.
4. Ask in the PR description — do not silently deviate.
