---
mode: agent
description: Roll the current SHA to ACR + ACA + AKS, with quality gate and smoke test.
tools: ['codebase', 'runCommands', 'editFiles']
---

# Workflow: Ship It

## Inputs

`.env.lab` sourced. `kubectl` and `az` already authenticated.

## Steps (you run these via `runCommands`, do not just print them)

1. Refuse if `git status --porcelain` is non-empty.
2. `uv run poe check`. Refuse if red.
3. Compute `GIT_SHA=$(git rev-parse --short HEAD)` and the changed-services list:
   ```bash
   git diff --name-only origin/main... | awk -F/ '/^src\/(agents|mcp_servers)\//{print $3}' | sort -u
   ```
4. For each changed service, build and push `$ACR.azurecr.io/zavashop/<svc>:$GIT_SHA`.
5. For each changed specialist or MCP → `az containerapp update --image …`.
6. If `src/agents/orchestrator/` changed → `helm upgrade --install zavashop infra/aks/helm/zavashop --set image.tag=$GIT_SHA …` and `kubectl rollout status`.
7. Smoke + evals against the public orchestrator IP.
8. Report SHA, services updated, revisions, eval result.

## Refuse to

- Push if `:latest` appears in any built tag.
- Update a workload whose image does not exist in ACR.
- Continue past a failed smoke test — instead, switch to `deploy-engineer` mode for triage.
