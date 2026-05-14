# ZavaShop on AKS + ACA — built by **GitHub Copilot Multi Custom Coding Agents**

> A hands-on lab series that teaches you to deliver a multi-agent retail supply-chain solution **end-to-end through a team of six GitHub Copilot Custom Coding Agents** — from requirements through deployment.
> Stack: **Microsoft Agent Framework (MAF)** + **GitHub Copilot SDK** (`gpt-5.5`) + **AKS** + **Azure Container Apps**.

---

## 🧭 What makes this lab different

Every artifact in this repo — specs, agent code, MCP servers, tests, Bicep, Helm, CI — is authored by a **named GitHub Copilot Custom Coding Agent** that owns one slice of the repo and carries its own tools, skills, and refusal rules.

The labs teach the **operating model itself** — not just the code. By the end you will have shipped ZavaShop *and* internalised a repeatable Copilot Custom Agent workflow you can take to any project.

```
       ┌─────────────────────── GitHub Copilot Multi Custom Agents ───────────────────────┐
       │                                                                                  │
 Issue ─►  /requirements-analyst  ─►  specs/<slug>.md                                      │
                  │                                                                       │
                  ▼                                                                       │
          /mcp-builder  ───────►  src/mcp_servers/*                                        │
          /agent-builder  ─────►  src/agents/<specialist>/*                                │
          /orchestrator-architect ─► src/agents/orchestrator, src/shared, docker-compose   │
                  │                                                                       │
                  ▼                                                                       │
          /test-author  ───────►  tests/** (unit · integration · evals)                    │
                  │                                                                       │
                  ▼                                                                       │
          /deploy-engineer  ───►  infra/** + .github/workflows/** + ACR/ACA/AKS rollout    │
       └──────────────────────────────────────────────────────────────────────────────────┘
```

Each agent is a file under [.github/agents/](.github/agents/) (`*.agent.md`). You invoke it by typing `/<agent-name>` in Copilot Chat. Three workflow prompts in [.github/prompts/](.github/prompts/) chain the agents together: `/feature-from-issue`, `/spec-to-code`, `/ship-it`.

---

## 🛍 The Story: ZavaShop

**ZavaShop** is a fast-growing global retailer with 500+ stores. Their supply chain runs on a mix of legacy ERPs, supplier portals, and ad-hoc spreadsheets. The Ops team wants an AI-native control plane — a fleet of cooperating agents that:

| Application Agent | Responsibility |
|---|---|
| `InventoryAgent` | Monitor stock-out risk across stores and warehouses |
| `SupplierAgent` | Negotiate purchase orders with suppliers via MCP-backed tools |
| `LogisticsAgent` | Plan shipments, track ETAs, re-route on disruption |
| `PricingAgent` | Recommend dynamic pricing from demand + competitor signals |
| `OrchestratorAgent` | The "store manager" — powered by the **GitHub Copilot SDK**, routes goals to the specialist agents |

The orchestrator runs as a **long-lived service on AKS**. The specialist agents run as **event-driven workloads on ACA** with **KEDA scale-to-zero**. All agents share a fleet of **MCP servers** that wrap ZavaShop's domain tools (inventory DB, supplier API, shipping API, pricing API).

```
┌────────────────────────────────────────────────────────────────┐
│                       AKS  (control plane)                     │
│   ┌──────────────────────────────────────────────────────────┐ │
│   │  OrchestratorAgent  (GitHub Copilot SDK + MAF Workflow)  │ │
│   └─────────┬────────────────────────────────────────────────┘ │
└─────────────┼──────────────────────────────────────────────────┘
              │ A2A / HTTP
   ┌──────────┼──────────┬──────────────┬──────────────┐
   ▼          ▼          ▼              ▼              ▼
┌─────────┐┌─────────┐┌──────────┐┌────────────┐┌──────────┐
│Inventory││Supplier ││Logistics ││  Pricing   ││   MCP    │
│  ACA    ││  ACA    ││   ACA    ││    ACA     ││ Servers  │
└─────────┘└─────────┘└──────────┘└────────────┘└──────────┘
```

> ⚠️ Don't confuse the two layers:
> - **Application agents** (the table above) — the runtime ZavaShop fleet you deploy.
> - **GitHub Copilot Custom Coding Agents** (`/requirements-analyst` etc.) — the dev-time team that *writes* the application agents for you.

---

## 👥 Meet the GitHub Copilot Custom Coding Agents

| Phase | Coding Agent | Owns | File |
|---|---|---|---|
| Requirements | `/requirements-analyst` | `specs/*.md` only — refuses to write code | [.github/agents/requirements-analyst.agent.md](.github/agents/requirements-analyst.agent.md) |
| MCP impl | `/mcp-builder` | `src/mcp_servers/*` (one server per turn) | [.github/agents/mcp-builder.agent.md](.github/agents/mcp-builder.agent.md) |
| Agent impl | `/agent-builder` | `src/agents/<specialist>/*` (one specialist per turn) | [.github/agents/agent-builder.agent.md](.github/agents/agent-builder.agent.md) |
| Orchestration | `/orchestrator-architect` | `src/agents/orchestrator/*`, `src/shared/*`, `docker-compose.yml` | [.github/agents/orchestrator-architect.agent.md](.github/agents/orchestrator-architect.agent.md) |
| Tests | `/test-author` | `tests/**` only — never edits `src/` | [.github/agents/test-author.agent.md](.github/agents/test-author.agent.md) |
| Deploy | `/deploy-engineer` | `infra/**`, `.github/workflows/**` | [.github/agents/deploy-engineer.agent.md](.github/agents/deploy-engineer.agent.md) |

Shared, agent-agnostic knowledge lives in [.github/skills/](.github/skills/) — every coding agent declares which skills it must consult before writing code.

Workflow prompts in [.github/prompts/](.github/prompts/):

- **`/feature-from-issue`** — issue → spec → code → tests → PR → deploy.
- **`/spec-to-code`** — drive an existing spec through code + tests.
- **`/ship-it`** — quality gate → build → push → ACR/ACA/AKS rollout → smoke + evals.

> **Hard rule (see [AGENTS.md](AGENTS.md) §1.1):** for every code change, invoke the right `/<agent>` from the table above. Each agent carries the tools, skills, and refusal rules needed for its slice of the repo.

---

## 🗺 Lab Index

| # | Lab | Coding agents you'll drive | What you build |
|---|---|---|---|
| 01 | [Environment Setup](./labs/lab-01-environment-setup/README.md) | — | Azure subscription, AKS cluster, ACA env, ACR, Key Vault, Workload Identity, then **install the 6 Copilot Custom Agents** |
| 02 | [Agent Creation](./labs/lab-02-agent-creation/README.md) | `/requirements-analyst` → `/mcp-builder` ×4 → `/agent-builder` ×4 → `/orchestrator-architect` | The five ZavaShop application agents in Python with MAF + Copilot SDK |
| 03 | [Multi-Agent Orchestration & Config](./labs/lab-03-orchestration/README.md) | `/requirements-analyst` → `/spec-to-code` → `/orchestrator-architect` | MAF Workflow, A2A wiring, MCP tools, Key Vault hydration, Docker Compose |
| 04 | [Testing](./labs/lab-04-testing/README.md) | `/test-author` (unit + MCP + integration + evals) → remote **GitHub Copilot Coding Agent** PR loop | Full test pyramid; assign GitHub-side Copilot to a failing-eval issue |
| 05 | [Deployment & Run](./labs/lab-05-deployment/README.md) | `/deploy-engineer` + `/ship-it` | Helm for AKS, Bicep for ACA, OIDC-federated CD, Day-2 partial roll |

---

## ✅ Prerequisites

- Azure subscription with **Owner** on a resource group
- Azure CLI ≥ 2.65, `kubectl`, `helm`, `docker`, `uv` (or `pip`)
- Python **3.11+**
- A **GitHub Copilot** subscription (Individual / Business / Enterprise)
- VS Code with **GitHub Copilot** + **GitHub Copilot Chat** extensions
  - After cloning, run **`Developer: Reload Window`** so VS Code discovers `.github/agents/*.agent.md` and the six ZavaShop agents appear in the `/`-invocation picker.

---

## 📚 How to use Copilot in this lab

1. **Read [AGENTS.md](./AGENTS.md)** — the house rules every coding agent obeys.
2. Open Copilot Chat. Type `/` and confirm you see `requirements-analyst`, `mcp-builder`, `agent-builder`, `orchestrator-architect`, `test-author`, `deploy-engineer`.
3. Start every task by **invoking the right coding agent**, not by free-form prompting:
   ```
   /requirements-analyst
   We need a returns-handling pipeline. Goal, contracts, eval scenarios.
   ```
4. When an agent finishes, it ends with a **handoff line** naming the next `/<agent>` to invoke. Follow it.
5. For multi-step changes, run a workflow prompt: `/feature-from-issue`, `/spec-to-code`, or `/ship-it`.

---

## 📂 Repository Layout

```
.
├── AGENTS.md                        # House rules — read this first
├── .github/
│   ├── copilot-instructions.md      # Always-on Copilot context
│   ├── agents/                      # 6 Copilot Custom Coding Agents (*.agent.md)
│   ├── skills/                      # Shared knowledge consulted by the agents
│   ├── prompts/                     # Workflow prompts (/feature-from-issue, /spec-to-code, /ship-it)
│   ├── instructions/                # Scoped *.instructions.md (python, k8s, agent-framework)
│   └── workflows/                   # CI/CD (authored by /deploy-engineer)
├── labs/                            # The 5 step-by-step labs
├── specs/                           # Authored by /requirements-analyst
├── src/
│   ├── agents/                      # ZavaShop application agents (one folder each)
│   ├── mcp_servers/                 # MCP tool servers (one folder each)
│   └── shared/                      # Settings, telemetry, A2A server factory, KV helper
├── infra/
│   ├── aks/                         # Helm chart + WIF docs (authored by /deploy-engineer)
│   └── aca/                         # ACA Bicep + deploy.sh   (authored by /deploy-engineer)
└── tests/                           # Unit · integration · evals (authored by /test-author)
```

## License

MIT
