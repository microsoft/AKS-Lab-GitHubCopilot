# Lab 03 — Orchestration & Configuration via Custom Agents

> ⏱ ~60 min · This lab introduces the **`feature-from-issue` workflow** — the chained-mode loop you'll use for every future change.

## ZavaShop story

ZavaShop's leadership wants a deterministic, auditable answer to a stock-out — not a free-form chat. So the orchestrator stops being a one-shot LLM call and becomes a **MAF `Workflow`**: read stock → check supplier capacity → consider transfer → adjust price → summarize. Each step is a typed contract with a specialist; if a specialist refuses or times out, the workflow can degrade gracefully instead of hallucinating. At the same time the team retires the `GITHUB_TOKEN` from local `.env` files and starts pulling it from Key Vault, and brings the entire fleet up locally via Docker Compose so a developer can debug a /plan run end-to-end without any cloud round trip. This lab is the moment ZavaShop's agents become a *system*.

## Microsoft Learn knowledge for this lab

- [Microsoft Agent Framework Workflows](https://learn.microsoft.com/agent-framework/) — the `Workflow` primitive replacing ad-hoc orchestration calls.
- [Azure Key Vault secrets — secure hydration patterns](https://learn.microsoft.com/azure/key-vault/secrets/about-secrets) — why secrets are fetched at start-up rather than baked into images.
- [`DefaultAzureCredential` chain](https://learn.microsoft.com/python/api/overview/azure/identity-readme) — the local-vs-cloud auth flow that makes `az login` work for the dev loop and Workload Identity work in production with the same code path.
- [Docker Compose for multi-container development](https://learn.microsoft.com/visualstudio/docker/tutorials/multi-container-apps) — the local equivalent of the ACA + AKS topology.
- [structlog & JSON logs in Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-overview) — why every ZavaShop agent emits `agent.name`/`agent.run_id`/`agent.span_id` fields.

## Goals

1. Promote the orchestrator to a real MAF `Workflow`.
2. Externalize secrets through Key Vault hydration.
3. Stand the whole fleet up with Docker Compose.
4. Practice the **agent handoff** pattern.

---

## Prerequisites

Before starting Lab 03, **finish Lab 02 in full**:

- [ ] All 4 MCP servers exist: `inventory`, `supplier`, `shipping`, `pricing`.
- [ ] All 4 specialist agents exist under `src/agents/`: `inventory`, `supplier`, `logistics`, `pricing`.
- [ ] `src/agents/orchestrator/` is wired with A2A clients for all four specialists.
- [ ] The Lab 02 Step 6 inventory smoke test returns JSON mentioning `store-101`.

If any specialist is missing, switch to `/agent-builder` and complete it before Step 1 — otherwise Lab 03 Step 7's `/plan` and `/invoke` calls cannot complete end-to-end.

> ℹ️ The GitHub Copilot SDK wires MCP via `GitHubCopilotOptions(mcp_servers={...})`, **not** via `tools=[MCPStreamableHTTPTool(...)]`. Tool calls also require an `on_permission_request` handler that returns `PermissionRequestResult(kind="approved")`. Re-use the inventory agent pattern for every specialist.

---

## Step 1 — Spec first (mode: `requirements-analyst`)

Create a GitHub issue (or a stub `ISSUE.md`) titled:

> **Add a deterministic `/plan` workflow to the orchestrator**

### Invoke `/requirements-analyst`

Paste the issue title + this context:

```
We need a non-LLM, deterministic plan endpoint. Inputs: goal, sku, store_id.
The MAF Workflow runs stock + price in parallel, then PO, then shipping,
then reconciles into a Plan. Inter-agent calls go over A2A.
Also: hydrate GITHUB_TOKEN and four *_MCP_URL secrets from Azure Key Vault
when ZAVA_KV_URL is set.
```

Expected: `specs/lab-03-plan-workflow.md` with the workflow topology drawn in ASCII, Pydantic `Goal` / `Plan` shapes, and at least 2 eval scenarios. Handoff line: → `orchestrator-architect`.

> ⛔ **Do not skip Step 1.** `spec-to-code` will refuse if `specs/lab-03-plan-workflow.md` does not exist yet. Verify with `ls specs/lab-03-plan-workflow.md` before moving on.

---

## Step 2 — Run the workflow prompt

Instead of driving each mode manually, kick off the chained workflow.

In Copilot Chat, run:

```
/spec-to-code
```

Provide:

```
Spec: specs/lab-03-plan-workflow.md
```

`spec-to-code.prompt.md` will:
1. Echo back the `Affected agents` checklist.
2. Ask you to switch to `orchestrator-architect` for `workflow.py`, `server.py /plan`, `src/shared/keyvault.py`, and `docker-compose.yml`.
3. After source is done, ask you to switch to `test-author`.

> ⚠️ You **must** physically invoke the next agent each time `spec-to-code` asks. The workflow prompt has no power to invoke other agents itself.

---

## Step 3 — Workflow implementation (mode: `orchestrator-architect`)

After switching, paste:

```
Implement specs/lab-03-plan-workflow.md sections "New / changed contracts"
and acceptance criteria #1–#3. Files in scope:
  - src/agents/orchestrator/workflow.py
  - src/agents/orchestrator/server.py   (add POST /plan)
The contracts Goal/Plan are frozen — do not rename fields.
```

### Verification the agent runs for you

```bash
uv run pyright src/agents/orchestrator
uv run uvicorn src.agents.orchestrator.server:app --port 8000 &
curl -s http://localhost:8000/openapi.json | jq '.paths | keys'
# Expect: ["/healthz","/invoke","/plan","/readyz"]
```

---

## Step 4 — Key Vault hydration (still in `orchestrator-architect`)

```
Implement src/shared/keyvault.py per specs/lab-03-plan-workflow.md acceptance
criteria #4. Then wire every src/agents/*/server.py and src/mcp_servers/*/server.py
to call hydrate_from_keyvault when ZAVA_KV_URL is set.
```

Acceptance:

- [ ] `azure.keyvault.secrets.aio.SecretClient` used (not the sync one).
- [ ] Credentials closed in `finally`.
- [ ] Env vars already set are not overwritten.
- [ ] All 9 servers (5 agents + 4 MCPs) call the helper.

---

## Step 5 — Seed Key Vault (manual, ops step)

You run this directly in the terminal — no agent needed for raw `az` ops:

```bash
source .env.lab
az keyvault secret set --vault-name $KV --name "GITHUB-TOKEN"      --value "$GITHUB_TOKEN"
az keyvault secret set --vault-name $KV --name "INVENTORY-MCP-URL" --value "http://inventory-mcp:8080/mcp"
az keyvault secret set --vault-name $KV --name "SUPPLIER-MCP-URL"  --value "http://supplier-mcp:8080/mcp"
az keyvault secret set --vault-name $KV --name "SHIPPING-MCP-URL"  --value "http://shipping-mcp:8080/mcp"
az keyvault secret set --vault-name $KV --name "PRICING-MCP-URL"   --value "http://pricing-mcp:8080/mcp"
```

---

## Step 6 — Local fleet via Docker Compose (mode: `orchestrator-architect`)

```
Generate src/Dockerfile.base (multi-stage, non-root zava uid 10001 with a
writable HOME=/home/zava and XDG_CACHE_HOME=/home/zava/.cache) and
docker-compose.yml with 9 services per specs/lab-03-plan-workflow.md.
Healthchecks must hit /healthz. Do NOT depend on Key Vault locally —
compose passes GITHUB_TOKEN through from the host env (use the
${GITHUB_TOKEN:?...} fail-fast pattern) and sets
ZAVA_COPILOT_TIMEOUT_SECONDS=120 in x-agent-env so chained tool calls
don't hit the 30 s default.
```

### Dockerfile.base requirements (non-negotiable)

The runtime stage **must**:

- `ENV HOME=/home/zava XDG_CACHE_HOME=/home/zava/.cache`
- `useradd --uid 10001 --home /home/zava ...` and `mkdir -p /home/zava/.cache /app && chown -R 10001:10001 /home/zava /app`
- `USER 10001:10001`

Why: the GitHub Copilot SDK extracts a bundled Node CLI to `$HOME/.cache` on the first call. If `HOME` defaults to `/app` (root-owned), every `/invoke` returns 500 with `EACCES: permission denied, mkdir '/app/.cache'`. Symptom is opaque — `/healthz` keeps returning 200 because the SDK only starts on the first real call.

### Acceptance

```bash
export GITHUB_TOKEN=<your-fine-grained-PAT>   # required even for `docker compose ps`/`down`
docker compose build
docker compose up -d
docker compose ps   # 9 services, all healthy after ~30s
```

---

## Step 7 — Run the scenarios

### Deterministic path (workflow):

```bash
curl -s -X POST localhost:8000/plan \
  -H 'content-type: application/json' \
  -d '{
        "goal":"Store 101 will stock out of ZS-1042 by Friday — fix it.",
        "sku":"ZS-1042",
        "store_id":"store-101"
      }' | jq
```

### LLM path (free-form):

```bash
curl -s -X POST localhost:8000/invoke \
  -H 'content-type: application/json' \
  -d '{"run_id":"r2","goal":"Mid-season demand spike on ZS-1042 at store-101."}' | jq
```

> ℹ️ The goal must reference a **single** `(sku, store_id)` pair. Regional phrasing like `"in the Northeast"` will be refused by the orchestrator's `SYSTEM_PROMPT` — that is the correct behaviour (multi-store refusal rule), not a bug.

If either fails, **do not** read code by hand. Switch to `orchestrator-architect` and say:

```
docker compose logs orchestrator inventory supplier --tail=200 shows X.
Identify the failing workflow node and propose a one-file fix.
```

The mode will diagnose, propose a diff, run `poe check`, and report.

---

## ✅ Lab 03 done when…

- [ ] `specs/lab-03-plan-workflow.md` exists and is checked into git.
- [ ] `/plan` returns a `Plan` mentioning `store-101` and `ZS-1042`.
- [ ] `/invoke` returns a coherent plan invoking ≥ 2 specialists (use a single-store goal).
- [ ] `docker compose logs orchestrator | jq -r 'select(.event=="agent.run.end")'` shows spans.
- [ ] `grep -RE "ghp_|sk-|github_pat_" -- ':!*.md' ':!.env.lab'` is empty.
- [ ] Every change came from a `/<agent>` invocation (see `git log` PR descriptions).

Next: [Lab 04 — Testing](../lab-04-testing/README.md).

---

## Troubleshooting (real bugs seen in this lab)

| Symptom | Root cause | Fix |
|---|---|---|
| `docker compose ps` fails with `GITHUB_TOKEN must be exported` | `${GITHUB_TOKEN:?...}` fail-fast in compose. | `export GITHUB_TOKEN=<PAT>` before every compose command (even `down`/`ps`). |
| `/invoke` returns 500 immediately; logs show `EACCES: permission denied, mkdir '/app/.cache'` | Non-root container HOME defaulted to `/app` (root-owned); Copilot SDK can't extract its bundled Node CLI. | Rebuild `src/Dockerfile.base` with `HOME=/home/zava`, `XDG_CACHE_HOME=/home/zava/.cache`, and `chown -R 10001:10001 /home/zava /app`. |
| `/invoke` returns a plan that says “all four specialists returned Permission denied” | Orchestrator's `GitHubCopilotOptions` missing `on_permission_request`. Specialists are fine; the four `ask_*` function tools silently deny. | Add `_approve_all` handler to the orchestrator's `GitHubCopilotOptions`. |
| `agent run failed` with `'dict' object has no attribute 'goal'` | One of the `ask_*` `@tool` functions took a Pydantic input. | Flatten to `async def ask_inventory(goal: str)`. |
| `plan workflow failed` after ~30 s; orchestrator logs show `httpx.ReadTimeout` from supplier | `A2AClient` httpx default of 30 s. A specialist's `/invoke` does LLM + chained MCP calls and routinely needs >30 s. | Use `httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)` in `a2a.py`. |
| `/invoke` returns 500 with `Timeout after 30.0s waiting for session.idle` | Per-agent Copilot session timeout still at 30 s default. | Set `ZAVA_COPILOT_TIMEOUT_SECONDS=120` in `docker-compose.yml::x-agent-env`. |
| `/invoke` is refused with “multi-store rule” when goal contains `"Northeast"` / region | Working as designed — orchestrator's `SYSTEM_PROMPT` refuses multi-store goals. | Resend with a single `store_id`. |
