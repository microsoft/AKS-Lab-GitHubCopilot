---
mode: agent
description: End-to-end ZavaShop workflow — turn a GitHub issue into a merged, deployed PR using the custom agents.
tools: ['codebase', 'search', 'usages', 'editFiles', 'runCommands', 'findTestFiles', 'problems', 'githubRepo', 'fetch']
---

# Workflow: Feature from Issue → Deployed PR

You are running the **full ZavaShop delivery loop** for one GitHub issue. You will invoke a different agent at each phase. **At every handoff, stop and ask the human to /-invocation the next agent** — do not silently impersonate other agents.

## Inputs

The user gives you either:
- a GitHub issue number (use `githubRepo` tool to fetch), or
- a freeform feature description.

## Phases (you must say where you are at all times)

### Phase 1 — Specification
**Mode: `requirements-analyst`**
Produce `specs/<slug>.md`. Stop. Ask user to review.

### Phase 2 — Domain implementation
For each `Affected agent` from the spec, in dependency order:
- If MCP server changes are needed → **mode: `mcp-builder`**.
- Then → **mode: `agent-builder`** for each specialist.
- Then → **mode: `orchestrator-architect`** if the workflow topology or shared modules change.

Each sub-phase produces one PR-sized diff. Stop after each.

### Phase 3 — Tests
**Mode: `test-author`**
Produce unit + integration + eval coverage for every acceptance criterion. Must reach `pytest --cov-fail-under=80`.

### Phase 4 — Local verification
Run:
```bash
docker compose up -d --build
ZAVA_ENDPOINT=http://localhost:8000 uv run python -m tests.evals.run_evals
```
If any eval fails, return to Phase 2 with the failing case as input.

### Phase 5 — PR
Push a feature branch and open a PR titled `feat: <slug>`. Body must:
- Link the issue.
- Quote the `Acceptance criteria` from the spec.
- Paste the `uv run poe check` and eval output.
- List the agents used at each phase.

### Phase 6 — Deploy
After merge, **mode: `deploy-engineer`**.
Run the full rollout sequence (see `.github/agents/deploy-engineer.agent.md`). Smoke `/plan` against the AKS LB. Run evals against the cloud endpoint.

## Rules

1. Never skip a phase. Never combine phases in a single turn.
2. If a phase fails, do **not** move forward — return to the failing phase's mode.
3. Always invoke the agent that owns the path you are about to edit. Each agent carries the right tools, skills, and refusal rules.
4. Every commit message starts with `feat:`, `fix:`, `chore(infra):`, or `test:` per `AGENTS.md` §7.
5. The Copilot SDK model is `gpt-5.5`. Always.

## Final report shape

Wrap up the workflow with:

```
✅ Issue #<n> shipped as PR #<m>, deployed at SHA <git-sha>.
- Spec: specs/<slug>.md
- Modes used: requirements-analyst → mcp-builder → agent-builder × N → test-author → deploy-engineer
- Evals: <pass>/<total>
- ACA revisions: ...
- AKS rollout: deploy/orchestrator-<rev>
```
