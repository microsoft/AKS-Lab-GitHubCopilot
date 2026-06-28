# Lab 02 — Agent Creation via Custom Agents

> ⏱ ~75 min · You will **invoke custom agents** with `/<name>` in Copilot Chat. Each agent is a GitHub Copilot Custom Agent with its own tools, skills, and refusal rules.

## ZavaShop story

With the Azure foundation in place, the ZavaShop platform team turns to the actual product: a fleet of small, role-scoped agents that can answer a real supply-chain question — *"SKU `ZS-1042` is out at store 101, what should we do?"* — without anyone hand-coding the orchestration. Each ZavaShop role becomes one MAF `ChatAgent`: the **inventory** agent reads stock, **supplier** opens POs, **logistics** moves stock between stores, **pricing** adjusts margins, and the **orchestrator** stitches them together. External side-effects (the warehouse DB, the supplier API, the shipping system, the pricing engine) are kept out of the agents and exposed as MCP servers, so the LLM never holds business state. This lab is where ZavaShop's agent code is born — all six implementations come from a Copilot Custom Agent, not hand-typed.

## Microsoft Learn knowledge for this lab

- [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/) — the `ChatAgent`, `Workflow`, and provider model used by every agent in this repo.
- [Build agents with the GitHub Copilot provider](https://learn.microsoft.com/agent-framework/) — the `GitHubCopilotAgent` + `GitHubCopilotOptions(model="gpt-5.5")` pattern this repo standardizes on.
- [Model Context Protocol (MCP) on Microsoft Learn](https://learn.microsoft.com/azure/developer/ai/) — why every external tool is exposed as an MCP server rather than an in-agent function.
- [Customize GitHub Copilot Chat with custom agents](https://docs.github.com/copilot/customizing-copilot/about-customizing-github-copilot-chat-responses) — the `.github/agents/*.agent.md` format you invoke with `/<name>`.
- [Pydantic v2 models](https://learn.microsoft.com/azure/developer/python/sdk/azure-sdk-overview) — every cross-boundary payload in ZavaShop is a `BaseModel` (request/response contracts, MCP tool args).

## Before you start

### Fast path for quick deployment

If your goal is to deploy a working demo quickly, run the workflow prompt instead of manually designing every implementation prompt:

```text
/feature-from-issue
Build the ZavaShop stock-out response app as a packaged deployable fleet:
five MAF agents, four MCP servers, tests, Docker packaging, and a handoff to
/ship-it. Target AKS for the orchestrator and ACA for specialists/MCPs.
```

Follow the handoffs it gives you to the owning custom agents. Use the detailed steps below when you want to teach or inspect each generated component. Both paths must produce the same deployable shape under `src/`, `tests/`, and `infra/`.

Verify the custom agents are installed:

```bash
ls .github/agents/*.agent.md   # 6 agents
ls .github/skills/*/SKILL.md         # 7 skills
ls .github/prompts/*.prompt.md       # 5 workflows
```

In VS Code:

1. Open Copilot Chat.
2. Open the **agent picker** (type `/` in the chat input).
3. Confirm the six ZavaShop agents appear in the `/`-invocation list:
   `requirements-analyst`, `mcp-builder`, `agent-builder`, `orchestrator-architect`, `test-author`, `deploy-engineer`.

If they don't appear, run **`Developer: Reload Window`** so VS Code picks up `.github/agents/`.

> 💡 If you want to read existing code, invoke any agent and ask — every agent has the `codebase` and `search` tools.

---

## Step 1 — Write the first spec (mode: `requirements-analyst`)

### Invoke `/requirements-analyst`

Paste this brief:

```
Stand up the ZavaShop fleet from scratch — five MAF agents (orchestrator,
inventory, supplier, logistics, pricing) plus four MCP servers. Single goal:
when given a stock-out goal for a SKU and store, the orchestrator must return
a structured Plan with stock_view, price_view, po_view, shipping_view, summary.
```

### Expected output

The mode produces `specs/lab-02-fleet.md` containing all 10 sections from the agent spec (Goal, Non-goals, Personas, Affected agents, Contracts, Acceptance, Eval scenarios, Out-of-scope, Handoff).

### Acceptance

- [ ] `specs/lab-02-fleet.md` exists.
- [ ] Acceptance criteria are numbered and each independently testable.
- [ ] At least one JSONL eval scenario uses `sku: "ZS-1042"` and `store_id: "store-101"`.
- [ ] Handoff line names the next mode (should be `mcp-builder` or `orchestrator-architect`).

If anything is missing or vague, stay with this agent and ask: *"Tighten section 6 — the StockReport fields are still ambiguous."*

---

## Step 2 — Shared scaffolding (mode: `orchestrator-architect`)

### Invoke `/orchestrator-architect`

Paste:

```
Implement Step 2 of labs/lab-02-agent-creation/README.md from specs/lab-02-fleet.md:
generate src/shared/settings.py, src/shared/telemetry.py, src/shared/server.py.
Run uv run poe check and report.
```

The mode will consult `.github/skills/pydantic-contracts/SKILL.md` and `.github/skills/copilot-sdk-gpt55/SKILL.md` automatically.

### Acceptance

- [ ] `src/shared/{settings,telemetry,server}.py` exist.
- [ ] `Settings` reads `ZAVA_` env vars; `copilot_model` defaults to `gpt-5.5`.
- [ ] `make_app` exposes `/healthz`, `/readyz`, `/invoke`.
- [ ] `uv run pyright src/shared` clean.

If the agent tries to put HTTP calls inline (it shouldn't), say: *"Move that into A2AClient — `orchestrator-architect.agent.md` rule 2."*

---

## Step 3 — MCP servers (mode: `mcp-builder`)

### Invoke `/mcp-builder`

Run **four** turns. Between turns, **keep the same agent** — `mcp-builder` only does MCP work.

| Turn | Prompt |
|---|---|
| 1 | `Generate src/mcp_servers/inventory/ per specs/lab-02-fleet.md. Tools: check_stock(StockQuery)->StockReport.` |
| 2 | `Generate src/mcp_servers/supplier/. Tools: list_suppliers(sku), draft_po(sku,qty,supplier_id).` |
| 3 | `Generate src/mcp_servers/shipping/. Tools: quote_shipment(po_id, destination).` |
| 4 | `Generate src/mcp_servers/pricing/. Tools: recommend_price(sku, demand_signal).` |

### Acceptance per MCP

The mode runs the verification itself (see `mcp-builder.agent.md`). Read its output for ✅ on:

- [ ] FastMCP on port 8080, transport `streamable-http`.
- [ ] All tools use Pydantic models in/out.
- [ ] In-memory store has SKU `ZS-1042` and locations `store-101`, `store-202`, `wh-east`.
- [ ] `# TODO: replace with Cosmos DB` is present.

---

## Step 4 — Specialist agents (mode: `agent-builder`)

> ⚠️ **This step must produce 4 `src/agents/<name>/` folders**: `inventory`, `supplier`, `logistics`, `pricing`. Lab 03's `docker compose up` depends on all four. Generating only `inventory` will cause the orchestrator container to fail with `dependency supplier/logistics/pricing failed to start`.

### Invoke `/agent-builder` — **four** turns, same agent

Prompt template per turn:

```
Implement src/agents/<name>/ from specs/lab-02-fleet.md.
MCP setting: <mcp_url_attr>.
Refusal rules: <refusals>.
```

| Turn | `<name>` | `<mcp_url_attr>` | `<refusals>` |
|---|---|---|---|
| 1 | `inventory` | `inventory_mcp_url` | refuse pricing and supplier negotiation questions |
| 2 | `supplier`  | `supplier_mcp_url`  | refuse pricing and shipping questions |
| 3 | `logistics` | `shipping_mcp_url`  | refuse pricing and supplier-negotiation questions |
| 4 | `pricing`   | `pricing_mcp_url`   | refuse inventory and supplier questions |

> Note: the `logistics` agent uses the `shipping` MCP.

The mode will:
1. Read `.github/skills/maf-agent-skeleton/SKILL.md`.
2. Read `.github/skills/copilot-sdk-gpt55/SKILL.md`.
3. Generate the folder.
4. Run `ruff` + `pyright` + import sanity.

### Acceptance (per specialist)

- [ ] Each `agent.py` uses `agent_framework.github.GitHubCopilotAgent` + `GitHubCopilotOptions(model=settings.copilot_model, timeout=settings.copilot_timeout_seconds, on_permission_request=_approve_all, mcp_servers={...})`.
- [ ] `on_permission_request=_approve_all` is wired — the handler returns `PermissionRequestResult(kind="approved")`. **Without this every tool call silently denies and the LLM reports "all specialists rejected the request".**
- [ ] MCP is attached via `GitHubCopilotOptions(mcp_servers={...})`, **not** `MCPStreamableHTTPTool`.
- [ ] `tools.py` stays an empty list (all external I/O goes through MCP).
- [ ] Each `prompts.py` ends with explicit *Refusal rules*.
- [ ] `grep -R "AzureOpenAI\|gpt-4\|GitHubCopilotChatClient\|MCPStreamableHTTPTool\|ChatAgent(" src/agents/` returns nothing.

If the agent tries to import a different client, **reject the diff** and re-prompt: *“AGENTS.md §4 — only `GitHubCopilotAgent` from `agent_framework.github`. Fix this turn.”*

### Gate: verify all four specialists before Step 5

```bash
for a in inventory supplier logistics pricing; do
  test -f src/agents/$a/agent.py  || { echo "MISSING: src/agents/$a/agent.py"; exit 1; }
  test -f src/agents/$a/server.py || { echo "MISSING: src/agents/$a/server.py"; exit 1; }
done
echo "all four specialist agents present"
```

Any `MISSING:` line blocks Step 5 — re-invoke `/agent-builder` to fill the gap.

---

## Step 5 — Orchestrator (mode: `orchestrator-architect`)

### Invoke `/orchestrator-architect`

```
Implement src/agents/orchestrator/{a2a.py, agent.py, prompts.py, server.py}
from specs/lab-02-fleet.md. Skip workflow.py — Lab 03 owns it.
The agent must delegate to all four specialists via A2AClient using
the four ZAVA_<NAME>_A2A_URL env vars with sensible local defaults.
```

### Acceptance

- [ ] `src/agents/orchestrator/a2a.py` — `A2AClient` with `httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)`. **A 30 s read timeout will not survive a specialist's LLM + chained MCP calls.**
- [ ] `agent.py` exposes 4 delegator tools (`ask_inventory`, `ask_supplier`, `ask_logistics`, `ask_pricing`) using `@tool` from `agent_framework`. Each tool signature is **flat** (`async def ask_inventory(goal: str) -> str`) — not a Pydantic input model. The Copilot SDK injects a raw `dict`; a Pydantic parameter raises `'dict' object has no attribute 'goal'` at call time.
- [ ] `GitHubCopilotOptions` for the orchestrator also includes `on_permission_request=_approve_all` — the four `ask_*` tools go through the same permission gate as specialist MCP tools.
- [ ] `pyright src/agents/orchestrator` clean.

---

## Step 6 — Smoke test (still in `orchestrator-architect` mode)

Ask the agent:

```
Run the inventory smoke test from labs/lab-02-agent-creation/README.md Step 6
and report the response JSON. Set GITHUB_TOKEN from .env.lab.
```

The mode executes:

```bash
uv run python -m src.mcp_servers.inventory.server &
sleep 2
ZAVA_INVENTORY_MCP_URL=http://localhost:8080/mcp \
  uv run uvicorn src.agents.inventory.server:app --port 8001 &
sleep 3
curl -s -X POST localhost:8001/invoke \
  -H 'content-type: application/json' \
  -d '{"run_id":"r1","goal":"Check stock for ZS-1042 in store-101, store-202"}' | jq
```

The JSON output must mention `store-101` and a recommendation. If not, ask the agent to triage.

---

## ✅ Lab 02 done when…

- [ ] `specs/lab-02-fleet.md` was generated by `requirements-analyst`.
- [ ] `src/shared/`, orchestrator, and the four specialist folders all exist: `src/agents/{inventory,supplier,logistics,pricing,orchestrator}/`.
- [ ] All four MCP folders exist: `src/mcp_servers/{inventory,supplier,shipping,pricing}/`.
- [ ] `uv run poe check` is green.
- [ ] `grep -RE "AzureOpenAI|gpt-4|GitHubCopilotChatClient|MCPStreamableHTTPTool|ChatAgent\(" src/` returns nothing.
- [ ] Inventory smoke test returns JSON mentioning `store-101`.

Next: [Lab 03 — Orchestration & Configuration](../lab-03-orchestration/README.md).

---

## Troubleshooting (real bugs seen in this lab)

| Symptom | Root cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'agent_framework.github_copilot'` | Old API. Correct import is `from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions`. | Update `agent.py`; ensure `pyproject.toml` has `agent-framework[github-copilot]`. |
| LLM replies “all four specialists returned **Permission denied** …” | `on_permission_request` not set on `GitHubCopilotOptions`. | Add `_approve_all` handler in **every** agent including the orchestrator. |
| Tool call raises `'dict' object has no attribute 'goal'` | Function-tool parameter is a Pydantic model; SDK passes a raw dict. | Make the tool take flat scalars: `async def ask_inventory(goal: str)`. |
| `httpx.ReadTimeout` from orchestrator after ≈30 s | `A2AClient` httpx default of 30 s is too tight for a specialist LLM run. | Use `httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)`. |
