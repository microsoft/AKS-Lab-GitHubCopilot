# Lab 04 test pyramid, evals, and CI

## Goal

Build a test pyramid for all five ZavaShop agents, four MCP servers, and the orchestrator's real MAF Workflow while preserving existing A2A and domain contracts. Add five seeded-data golden eval scenarios, enforce quality and coverage through Poe and Python 3.13 CI, and complete the required remote Copilot Coding Agent issue/PR regression-fix exercise.

## Non-goals

- Do not change the existing `Goal`, `Plan`, `InvokeRequest`, `InvokeResponse`, or `EvalScenario` contracts.
- Do not replace the GitHub Copilot SDK, change its configured model, or call a real model from unit or integration tests.
- Do not change agent or MCP production behavior except where a failing regression test is handed to the owning implementation agent for a separate fix.
- Do not run live golden evals during spec implementation; live evals require the explicitly gated eval workflow and credentials.
- Do not change Azure deployment infrastructure or add a new runtime dependency solely for test coverage.

## Personas

- **Store manager:** receives reliable stock recovery plans and clear protection against unsupported recommendations.
- **Supply planner:** relies on correct inventory, supplier, shipping, and pricing results for seeded products and locations.
- **Platform / QA engineer:** gets deterministic unit and ASGI integration coverage, actionable quality gates, and CI results.
- **Repository maintainer:** can validate real end-to-end behavior through a gated live eval and review regression fixes produced through the required remote Copilot issue/PR loop.

## Affected agents

- [x] `orchestrator` — exercise `/plan`, `/invoke`, the real MAF Workflow, A2A routing, and orchestration regression behavior.
- [x] `inventory` — unit and workflow coverage for inventory behavior.
- [x] `supplier` — unit and workflow coverage for supplier behavior.
- [x] `logistics` — unit and workflow coverage for shipping behavior.
- [x] `pricing` — unit and workflow coverage for pricing behavior.
- [x] MCP server `inventory` — direct tool happy-path and invalid-input coverage.
- [x] MCP server `supplier` — direct tool happy-path and invalid-input coverage.
- [x] MCP server `shipping` — direct tool happy-path and invalid-input coverage.
- [x] MCP server `pricing` — direct tool happy-path and invalid-input coverage.

Agent-to-agent calls remain through the existing typed A2A interfaces; tests must not import one specialist's implementation into another. MCP tool tests call the owning server tool directly.

## New / changed contracts

No production or test wire contract changes are authorized. Tests and evals must use the current frozen Pydantic shapes:

```python
from pydantic import BaseModel, ConfigDict, Field


class Goal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    store_id: str = Field(min_length=1)


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str
    store_id: str
    stock_view: str
    price_view: str
    po_view: str
    shipping_view: str
    summary: str
    next_actions: list[str]


class InvokeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1, max_length=64)
    goal: str = Field(min_length=1, max_length=4000)
    context: dict[str, str] = Field(default_factory=dict)


class InvokeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    output: str
    tool_calls: list[str] = Field(default_factory=list)
```

The golden eval input follows the existing `EvalScenario` schema in `tests/evals/run_evals.py`; include `sku` and `store_id` on every JSONL row:

```python
class EvalScenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    must_mention: list[str] = Field(default_factory=list)
    must_call: list[str] = Field(default_factory=list)
    forbid_call: list[str] = Field(default_factory=list)
    max_latency_s: float = Field(default=180, gt=0)
```

## Acceptance criteria

1. Add unit tests for each of the five agents: `inventory`, `supplier`, `logistics`, `pricing`, and `orchestrator`. Each agent has happy-path, refusal/out-of-scope, and tool-error cases using `MockChatClient`; patch `GitHubCopilotAgent` at that agent module's actual import binding (`src.agents.<name>.agent.GitHubCopilotAgent`). Never construct or invoke the real Copilot SDK client in a unit test. Assert response structure and relevant keyword presence, not exact generated prose; do not use `time.sleep`.
2. Add direct tool tests for all tools in all four MCP servers. For each tool, cover at least one successful result using the actual seeded data and one invalid-input case, including an unknown/invalid SKU where the tool accepts a SKU. Assert model/contract behavior and meaningful result fields without changing the existing tool contracts.
3. Add in-process ASGI integration tests using `httpx.AsyncClient` and `ASGITransport` for both orchestrator `POST /plan` and agent `POST /invoke`. Exercise the real `build_plan_workflow` / `execute_plan` MAF Workflow and typed A2A path; patch every `GitHubCopilotAgent` import site and use mocked model responses. Do not start a network server or replace the MAF Workflow with a fake workflow. Check response schemas, run IDs, specialist routing, and keyword/result fields without asserting exact LLM text.
4. Add a Key Vault regression test proving hydration is skipped when `ZAVA_KV_URL` is unset. Patch credential/client constructors to fail if called, invoke the helper (and/or the app startup path), and verify startup proceeds without Azure access or Key Vault calls.
5. Achieve at least **80% coverage for `src/agents`**. Configure `poe check` to run Ruff lint, Ruff format check, strict Pyright, and pytest with agent coverage enforcement (`--cov=src/agents --cov-fail-under=80`). Keep uncovered-code exclusions limited to the project-approved entrypoint exception; do not lower the threshold to pass.
6. Configure `poe audit` to run Bandit against `src` with the repository Bandit configuration and strict `pip-audit`. Configure `poe evals` to run `python -m tests.evals.run_evals`. `uv run poe check` and `uv run poe audit` must pass locally; `uv run poe evals` must be available as the live endpoint command.
7. The `deploy-engineer` owns and implements `.github/workflows/ci.yml` for pushes and pull requests using Python 3.13, `astral-sh/setup-uv@v3`, frozen dependency synchronization, and a uv cache keyed from `uv.lock`. Run `uv run poe check` and `uv run poe audit` as required CI checks.
8. Add a separate `run-evals` CI job gated on the pull request `run-evals` label. The job starts the Compose fleet, waits for service readiness, and runs the golden eval command against the orchestrator. Read the Copilot credential only from the GitHub Actions secret `COPILOT_TOKEN`, map it to the runtime `GITHUB_TOKEN` environment, and never echo or persist its value. Do not run this job on ordinary PRs lacking the label.
9. Include exactly five valid JSONL eval scenarios using the current `EvalScenario` schema and actual seeded entities/values. Cover stock-out, demand spike, supplier delay, price war, and seasonal promotion. Every row includes `id`, `goal`, `sku`, `store_id`, `must_mention`, `must_call`, `forbid_call`, and a positive `max_latency_s` appropriate for multi-agent fan-out (180 seconds is the default budget). Ground scenarios in seeded data such as SKU `ZS-1042`, locations `store-101` / `store-202` / `wh-east`, returned current price `$39.99`, supplier `sup-northstar` / `sup-fabrikam-rapid`, and carrier `Fabrikam RapidShip`; do not invent seeded records or require internal pricing data in golden outputs. The runner posts to `/plan`; `must_call` and `forbid_call` are informational review notes because `Plan` returns narrative views, not tool-call fields, and are not part of the pass gate.
10. Adapt Lab 04 Step 8's remote GitHub Copilot Coding Agent issue/PR exercise to investigate the observed intermittent S5 failure instead of introducing the tutorial's S3 regression. Use `evidence/lab-04/evals-before-fix.log` as evidence that S5 failed because the response missed "seasonal apparel", and `evidence/lab-04/s5-diagnostic.json` as evidence that an isolated rerun passed; treat the root cause as unconfirmed and do not infer that the isolated pass resolved the failure. Open an issue with this evidence and the existing workflow handoff instruction, then assign it to the remote Coding Agent. Require the agent to investigate before proposing a fix and open a PR limited to `src/agents/orchestrator/` and `tests/` with meaningful regression coverage. Review the PR locally, including the investigation, scope, coverage, and preservation of existing contracts and security policy. Require CI to run all five existing eval scenarios and pass with zero failures; preserve the scenarios, assertions, latency budgets, and workflow topology. Record the issue/PR outcome as lab evidence; perform this exercise later, not while writing this spec.
11. The CI image-security policy scans the base image and all nine service images. For every image, retain a complete vulnerability report from an unfiltered Trivy scan, then run a separate Trivy gate with `ignore-unfixed`, HIGH and CRITICAL severities, and exit code 1 to block fixable HIGH/CRITICAL findings. Keep unfixed distribution findings visible in the unfiltered reports and CI summary. Document the observed 44 Debian HIGH findings per image as accepted pending risks for this educational lab, but compute all report and summary counts dynamically rather than hardcoding 44. A green gate means no fixable HIGH/CRITICAL findings; it does not mean the images are vulnerability-free. Build and either scan's errors must fail CI, and publish the complete reports even when the vulnerability gate fails.

## Eval scenarios

```jsonl
{"id":"S1-stockout-zs1042-store101","goal":"SKU ZS-1042 has only a short stock window at store-101. Build a recovery plan using nearby store-202 and wh-east stock, supplier replenishment, pricing, and shipping.","sku":"ZS-1042","store_id":"store-101","must_mention":["ZS-1042","store-101","store-202","wh-east","stock"],"must_call":["inventory","supplier","logistics","pricing"],"forbid_call":[],"max_latency_s":180}
{"id":"S2-demand-spike-zs1042","goal":"Demand for SKU ZS-1042 is spiking at store-101. Assess the seeded stock and replenishment options and provide a recovery plan.","sku":"ZS-1042","store_id":"store-101","must_mention":["ZS-1042","store-101","store-202","wh-east","84","420"],"must_call":["inventory","supplier","logistics","pricing"],"forbid_call":[],"max_latency_s":180}
{"id":"S3-supplier-delay-zs1042","goal":"A supplier delay threatens SKU ZS-1042 at store-101. Compare the seeded Northstar and Fabrikam lead times and the available expedited shipping option.","sku":"ZS-1042","store_id":"store-101","must_mention":["ZS-1042","store-101","Fabrikam RapidShip","ETA"],"must_call":["inventory","supplier","logistics"],"forbid_call":[],"max_latency_s":180}
{"id":"S4-price-war-zs1042","goal":"A competitor price war affects SKU ZS-1042 at store-101. Use the returned pricing information to recommend a price response and coordinate replenishment for the low-stock store.","sku":"ZS-1042","store_id":"store-101","must_mention":["ZS-1042","store-101","39.99","price"],"must_call":["inventory","pricing","supplier"],"forbid_call":[],"max_latency_s":180}
{"id":"S5-seasonal-promotion-zs1042","goal":"Plan a seasonal apparel promotion for SKU ZS-1042 at store-101 using the returned pricing information, stock position, and replenishment/shipping choices.","sku":"ZS-1042","store_id":"store-101","must_mention":["ZS-1042","store-101","seasonal apparel","39.99","store-202","Fabrikam RapidShip"],"must_call":["inventory","pricing","supplier","logistics"],"forbid_call":[],"max_latency_s":180}
```

## Out of scope for this iteration

- Changing production agent prompts, tools, contracts, MCP server behavior, seed data, or deployment manifests as part of test authoring.
- Changing the current `EvalScenario` schema, `/plan` response schema, MAF Workflow topology, or A2A contract to expose tool calls in the plan response.
- Running live model evaluations as part of local unit/integration verification; live evals are restricted to explicit developer invocation or the labeled CI job.
- Broadly expanding the regression-fix PR beyond the orchestrator parallelism fix and its tests.

## Handoff

Next agent: `deploy-engineer`.

Prompt:

```text
Keep the adapted Lab 04 Step 8 issue/PR requirements in acceptance criterion 10 intact; this handoff is only for acceptance criterion 11 and does not authorize changes to the S5 investigation, eval scenarios, contracts, or workflow topology.
Implement acceptance criterion 11 from specs/lab-04-tests.md in .github/workflows/ci.yml only. Scan the base image and all nine service images. Retain complete reports from unfiltered Trivy scans, then use a separate ignore-unfixed gate for fixable HIGH/CRITICAL findings. Publish reports even when the gate fails, keep unfixed distribution findings visible in reports and the CI summary, and compute counts dynamically. Document the observed 44 Debian HIGH findings per image as accepted pending educational-lab risks without hardcoding the count. Keep scanner/build errors failing CI and preserve all existing jobs, triggers, other acceptance criteria, scenarios, and contracts. Do not change any other files.
```
