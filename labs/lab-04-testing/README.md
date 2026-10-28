# Lab 04 — Testing via Custom Agents

> ⏱ ~50 min · You will hand the entire test suite to the **`test-author`** custom mode, and practice the **GitHub Copilot Coding Agent loop** for fixing failing evals.

## ZavaShop story

ZavaShop's supply-chain agents are now talking to each other, but the business cannot afford a regression where the orchestrator confidently recommends adjusting a price for a SKU that doesn't exist. The platform team builds a **test pyramid** that protects each layer: per-agent unit tests with `MockChatClient` so prompts can change safely, per-MCP tool tests so a SQL change in the warehouse cannot break the contract, in-process ASGI integration tests so `/plan` is rehearsed without the cloud, and a small set of **golden eval scenarios** (`S1`–`S5`) that pin the behaviour of the whole fleet. Then they wire `uv run poe check` to GitHub Actions, so every PR Copilot opens is gated by the same quality bar a human PR would be. This lab is where ZavaShop's agents become *trustworthy*.

## Microsoft Learn knowledge for this lab

- [pytest with the Azure SDK](https://learn.microsoft.com/azure/developer/python/sdk/azure-sdk-test-overview) — async-friendly testing patterns used here.
- [Continuous integration with GitHub Actions](https://learn.microsoft.com/training/modules/github-actions-ci/) — the `ci.yml` quality gate the orchestrator workflow runs under.
- [Evaluation in Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/) — why the eval harness lives next to the agents, not in a separate repo.
- [OWASP LLM Top 10 for AI applications](https://learn.microsoft.com/azure/ai-services/openai/concepts/safety-system) — the threat model behind the refusal-rule unit tests.
- [pyright strict mode for Python](https://learn.microsoft.com/azure/developer/python/sdk/azure-sdk-library-installation) — the contract enforcement that lets Copilot Coding Agent open PRs safely.

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


---

## Execution Results and Evidence
### Quality checks and evaluations
- `uv run poe check`: passed — 46 tests, 93.56% agent coverage,
  Ruff and Pyright clean.
- `uv run poe audit`: passed — no known vulnerabilities reported.
- The full live eval suite passed all five scenarios with zero failures.
  All scenarios completed within their 180-second budgets.

| Scenario | Result | Latency |
|---|---|---|
| S1 — Stock-out | PASS | 32.85s |
| S2 — Demand spike | PASS | 33.90s |
| S3 — Supplier delay | PASS | 45.46s |
| S4 — Price war | PASS | 34.97s |
| S5 — Seasonal promotion | PASS | 45.74s |

Earlier runs showed intermittent missing mentions in S3 and S5.
The final run passed without a production-code fix; the root cause
remains unconfirmed. Optional sanitized JSON diagnostics and offline
tests were added to support future investigation.

The `/plan` endpoint does not expose tool-call traces. Therefore,
`recorded_calls` is `null`, and expected-specialist notes are not
evidence of actual calls.

### Image security
Image-security CI passed on `lab04-ci-checkpoint`.
Complete reports retain unfixed vulnerabilities; the blocking gate
rejects HIGH/CRITICAL findings with an available fix.

The documented scan reported 44 unfixed Debian HIGH findings per image.
These remain open risks under the policy documented in
`specs/lab-04-tests.md`. A passing gate does not mean vulnerability-free
images.

#### CI before and after remediation
- **Before (`ci-before-fix.png`):** the earlier CI execution failed during
  image-security validation.
- **After (`ci-after-fix.png`):** CI passed after correcting the Trivy action
  reference, removing unnecessary runtime installer components containing
  vulnerable Python packages, and applying the documented vulnerability policy.

The final gate blocks fixable HIGH/CRITICAL vulnerabilities. Unfixed
findings remain visible in the complete reports; they were not resolved
by changing the gate.

![CI before remediation](../../PROJECT EVIDENCE/lab-04/ci-before-fix.png)
![CI after remediation](../../PROJECT EVIDENCE/lab-04/ci-after-fix.png)
[Complete image-security reports](../../PROJECT EVIDENCE/lab-04/Security%20Reports.zip)

### Step 8 limitation
[Issue #1](https://github.com/Luisvvargas/AKS-Lab-GitHubCopilot/issues/1)
records the observed S5 failure. The investigation used that failure
instead of introducing the tutorial's S3 regression.

The remote GitHub Copilot Coding Agent was unavailable under the
account's Copilot Free license. Investigation and diagnostic changes
were performed using local Copilot in VS Code.

**The remote Coding Agent PR requirement remains incomplete.**
Local Copilot work is not presented as fulfilling that requirement.

### Evidence
![Final quality checks: 46 tests, 93.56% coverage](../../PROJECT EVIDENCE/lab-04/check04.png)
![Dependency and source audit passed](../../PROJECT EVIDENCE/lab-04/audit04.png)
![All five eval scenarios passed](../../PROJECT EVIDENCE/lab-04/evals04.png)
![CI passed on the checkpoint branch](../../PROJECT EVIDENCE/lab-04/ci-after-fix.png)

- [Final eval output](../../PROJECT EVIDENCE/lab-04/evals-final-validation.txt)
- [Sanitized eval diagnostics](../../PROJECT EVIDENCE/lab-04/evals-final-validation.json)