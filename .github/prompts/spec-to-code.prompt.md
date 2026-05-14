---
mode: agent
description: Drive an existing spec (specs/*.md) through code + tests in one PR.
tools: ['search/codebase', 'search', 'edit/editFiles', 'execute/runInTerminal', 'execute/getTerminalOutput', 'findTestFiles', 'read/problems']
---

# Workflow: Spec → Code → Tests

## Inputs

A `specs/<slug>.md` file from `requirements-analyst`. If missing, refuse and ask the user to run `requirements-analyst` first.

## Steps

1. Read `specs/<slug>.md`. Echo the `Affected agents` checklist back to the user.
2. For each ticked agent / MCP server, ask the user to invoke the next agent:
   - MCP changes → `mcp-builder`
   - Specialist agent → `agent-builder`
   - Orchestrator / shared / docker-compose → `orchestrator-architect`
3. After all source changes, ask the user to switch to `test-author`. Provide the acceptance criteria from the spec as the test brief.
4. After tests pass locally, run:
   ```bash
   uv run poe check
   docker compose up -d --build
   ZAVA_ENDPOINT=http://localhost:8000 uv run python -m tests.evals.run_evals
   docker compose down
   ```
5. Open a draft PR with the spec quoted in the body.

## Don'ts

- Don't write any code while in this workflow mode — delegate to the specialist agents.
- Don't proceed to the next phase if `uv run poe check` is red.
