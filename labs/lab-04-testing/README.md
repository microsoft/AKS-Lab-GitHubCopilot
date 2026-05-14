# Lab 04 — Testing via Custom Agents

> ⏱ ~50 min · You will hand the entire test suite to the **`test-author`** custom mode, and practice the **GitHub Copilot Coding Agent loop** for fixing failing evals.

## The pyramid

```
┌─ Evals (golden set, run against deployed orchestrator)
├─ Integration (in-process ASGI loopback)
├─ Unit (MockChatClient + patched MCP)
└─ Per-MCP tool tests (direct calls)
```

All four layers are produced by the **same agent** — `test-author`. It reads `.github/skills/a2a-loopback-tests/SKILL.md` and `.github/skills/pydantic-contracts/SKILL.md` before writing anything.

---

## Step 1 — Spec the test brief (mode: `requirements-analyst`)

### Invoke `/requirements-analyst`

```
We need a test suite covering:
- per-agent unit tests (happy/refusal/tool-error)
- per-MCP tool tests
- integration over ASGI loopback for /plan and /invoke
- golden eval set with ≥ 5 scenarios
- poe task graph (check, audit, evals) and a GitHub Actions CI workflow
```

Expected output: `specs/lab-04-tests.md` with explicit acceptance criteria per layer and the JSONL schema.

---

## Step 2 — Unit tests for every agent (mode: `test-author`)

### Invoke `/test-author`

```
Implement the "Unit (agent)" section of specs/lab-04-tests.md for all four
specialists and the orchestrator. Three cases per agent: happy, refusal,
tool error. Use MockChatClient. Patch GitHubCopilotChatClient at the
import site in each agent module.
```

The mode runs:
```bash
uv run pytest tests/agents -q
```
itself and reports.

### Acceptance

- [ ] `tests/agents/{inventory,supplier,logistics,pricing,orchestrator}/test_agent.py` exist.
- [ ] No test imports `GitHubCopilotChatClient` for real (`grep -L MockChatClient tests/agents -r` empty).
- [ ] No `time.sleep`.
- [ ] No exact-string assertions on LLM output.

If any test imports the real client, the agent is in violation. Re-prompt: *"`test-author.agent.md` rule 1 — patch the import, don't call the real client."*

---

## Step 3 — MCP server tool tests (still in `test-author`)

```
Add tests/mcp_servers/<each>/test_tools.py — call each @mcp.tool() directly
with Pydantic inputs. Cover at least one happy case and one validation error
(invalid SKU) per tool.
```

### Acceptance

```bash
uv run pytest tests/mcp_servers -q
```

---

## Step 4 — Integration over ASGI loopback (still in `test-author`)

```
Implement the "Integration" layer per specs/lab-04-tests.md. Build the fleet
fixture exactly as .github/skills/a2a-loopback-tests/SKILL.md describes —
patch every agent's GitHubCopilotChatClient and mount each FastAPI app
behind ASGITransport. Exercise POST /plan and POST /invoke.
```

### Acceptance

```bash
uv run pytest tests/integration -q
uv run pytest --cov=src/agents --cov-report=term-missing --cov-fail-under=80
```

---

## Step 5 — Evals (still in `test-author`)

```
Generate tests/evals/scenarios.jsonl with 5 ZavaShop scenarios (stock-out,
demand spike, supplier delay, price war, seasonal promo) per
specs/lab-04-tests.md, plus tests/evals/run_evals.py per
.github/skills/a2a-loopback-tests/SKILL.md.
```

### Acceptance

```bash
docker compose up -d
ZAVA_ENDPOINT=http://localhost:8000 uv run python -m tests.evals.run_evals
# Expect: 0 failures
```

---

## Step 6 — Quality gate (mode: `test-author` runs it)

Ask the agent:

```
Add [tool.poe.tasks] to pyproject.toml:
  check = ruff check + ruff format --check + pyright + pytest -q --cov=src/agents --cov-fail-under=80
  audit = bandit -r src + pip-audit
  evals = python -m tests.evals.run_evals
Then run `uv run poe check` and `uv run poe audit` and report.
```

---

## Step 7 — CI (mode: `deploy-engineer`)

### Invoke `/deploy-engineer`

```
Generate .github/workflows/ci.yml:
- Trigger: push + pull_request.
- Job `check`: setup-uv@v3, uv sync --frozen, uv run poe check, uv run poe audit.
- Job `evals` (conditional on label `run-evals`): docker compose up -d,
  python -m tests.evals.run_evals.
- Cache uv venv on uv.lock hash.
```

---

## Step 8 — The Coding Agent loop (real GitHub Copilot)

This is the punchline of the lab. You now hand bug-fixing to the **remote GitHub Copilot Coding Agent** — the same agent that's been driving the agents, but now driven from a GitHub issue.

### 8.1 Force a failing eval

Pick scenario `S3` (supplier delay). Make the orchestrator's prompt slightly wrong:

```bash
# Use `test-author` mode if you want — but it's a one-liner
sed -i.bak 's/parallel/sequential/g' src/agents/orchestrator/prompts.py
docker compose restart orchestrator
ZAVA_ENDPOINT=http://localhost:8000 uv run python -m tests.evals.run_evals
# Expect: 1 failure (S3)
```

### 8.2 Open an issue with the failure

Push the repo. Open an issue:

> **Title:** Eval S3 fails — orchestrator no longer parallelizes stock + price
>
> **Body:** Paste the failing JSON output. Add at the bottom:
> ```
> Run with the `feature-from-issue.prompt.md` workflow.
> Start in `requirements-analyst` mode if the spec needs updating, else jump straight to `orchestrator-architect`.
> ```

### 8.3 Assign Copilot

In the issue sidebar → **Assignees** → choose **Copilot**.

### 8.4 Verify Copilot's PR

Within a few minutes Copilot opens a PR. **invoke `/test-author`** locally to review:

```
Review PR #<n> against specs/lab-04-tests.md and the agent rules in
AGENTS.md §1.1. List any violations. Do not approve if any agent
boundary is crossed (e.g. infra changes in a src/ PR).
```

The PR is acceptable when:
- [ ] Only `src/agents/orchestrator/` and `tests/` are touched.
- [ ] `GitHubCopilotChatClient(model="gpt-5.5")` is preserved.
- [ ] The failing eval now passes in CI.
- [ ] The PR description references the `/<agent>` chain that produced it.

---

## ✅ Lab 04 done when…

- [ ] `uv run poe check` and `uv run poe audit` both green.
- [ ] `uv run poe evals` returns 0 failures.
- [ ] At least one fix in this lab landed via the **remote Coding Agent PR loop**.
- [ ] CI green on `main`.
- [ ] `git log` for this lab shows no manual code edits — only Copilot diffs and the Coding Agent commit.

Next: [Lab 05 — Deployment & Run](../lab-05-deployment/README.md).
