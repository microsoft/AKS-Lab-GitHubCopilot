# Lab 05 — Deployment & Run via Custom Agents

> ⏱ ~60 min · The **`deploy-engineer`** custom mode owns this entire lab. You drive the rollout through `/ship-it` and verify with smoke + evals against the live AKS endpoint.

## What you'll produce

| Path | Owner (agent) |
|---|---|
| `infra/aca/agent.bicep` | `deploy-engineer` |
| `infra/aca/deploy.sh` | `deploy-engineer` |
| `infra/aks/helm/zavashop/**` | `deploy-engineer` |
| `infra/aks/wif/README.md` | `deploy-engineer` |
| `.github/workflows/deploy.yml` | `deploy-engineer` |

All authored by the custom mode using `.github/skills/aca-bicep/SKILL.md` + `.github/skills/aks-helm/SKILL.md`.

---

## Step 1 — Spec the rollout (mode: `requirements-analyst`)

### Invoke `/requirements-analyst`

```
We need the deploy story:
- ACA Bicep module reused for 4 specialists + 4 MCP servers (8 ACA apps total).
- Helm chart for the orchestrator on AKS, with Workload Identity, CSI-projected
  GITHUB_TOKEN from Key Vault, topology spread, 2 replicas.
- One `/ship-it` workflow that builds, pushes, rolls, smokes.
- A GitHub Actions workflow that runs the same `/ship-it` steps on push to main.
```

Output: `specs/lab-05-deploy.md`. Handoff → `deploy-engineer`.

---

## Step 2 — Build base + service images (mode: `deploy-engineer`)

### Invoke `/deploy-engineer`

```
Generate src/Dockerfile.base per .github/skills/aca-bicep/SKILL.md style
(multi-stage, non-root zava uid 10001, EXPOSE 8000). Then build all 10
images (1 base + 9 services) tagged $ACR.azurecr.io/zavashop/<name>:$(git rev-parse --short HEAD)
and push to ACR. Run the quality gate first; refuse if dirty or red.
```

The mode will refuse if `git status` is non-empty or `uv run poe check` fails. Resolve those first.

### Acceptance

```bash
az acr repository list -n $ACR -o tsv | sort
# base inventory inventory-mcp logistics orchestrator pricing
# pricing-mcp shipping-mcp supplier supplier-mcp
```

---

## Step 3 — ACA Bicep + deploy.sh (still in `deploy-engineer`)

```
Generate infra/aca/agent.bicep per .github/skills/aca-bicep/SKILL.md and
infra/aca/deploy.sh that deploys all 4 MCPs + 4 specialists, captures their
internal FQDNs into .env.fqdns. Validate with `az bicep build`.
```

The mode runs `bash -n infra/aca/deploy.sh && az bicep build --file infra/aca/agent.bicep --stdout > /dev/null` itself.

---

## Step 4 — Helm chart for the orchestrator (still in `deploy-engineer`)

```
Generate infra/aks/helm/zavashop/ per .github/skills/aks-helm/SKILL.md.
Run `helm lint` and `helm template` with placeholder values.
```

Mode acceptance output should include:

```
helm lint infra/aks/helm/zavashop      → 0 chart(s) failed
helm template ... | yq '.kind' | sort -u
# Deployment Service ServiceAccount SecretProviderClass
```

---

## Step 5 — WIF + CSI docs (still in `deploy-engineer`)

```
Generate infra/aks/wif/README.md documenting:
1. Re-federating the UAMI to system:serviceaccount:zavashop:orchestrator-sa
   (link back to Lab 01 §4).
2. Installing the Secrets Store CSI driver + Azure provider on the AKS cluster.
3. Seeding GITHUB-TOKEN in Key Vault.
4. Production migration to GitHub App + OIDC token broker (stub).
```

---

## Step 6 — First rollout via `/ship-it`

In Copilot Chat, with `deploy-engineer` mode still active, run the workflow:

```
/ship-it
```

The workflow prompt will:

1. Refuse if `git status` dirty.
2. Run `uv run poe check`.
3. Compute the changed-services set (on first run: all of them).
4. Build + push only changed images.
5. `bash infra/aca/deploy.sh`.
6. `helm upgrade --install zavashop infra/aks/helm/zavashop --set image.tag=$GIT_SHA …`.
7. `kubectl -n zavashop rollout status deploy/orchestrator`.
8. Wait for external IP + `/healthz` readiness, then run smoke + evals against the public IP.

### Acceptance

```bash
az containerapp list -g $RG -o table     # 8 healthy apps
kubectl -n zavashop get pods             # orchestrator 2/2 Running
ORCH=$(kubectl -n zavashop get svc orchestrator -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
# If ORCH is empty right after rollout, wait and retry.
# The CD workflow already includes this guard and waits for /healthz before /plan.
# Real AKS+ACA orchestration runs 60–120 s end-to-end (Copilot SDK + 4 specialists
# + 4 MCPs), so widen the per-scenario budget from the loopback default of 30 s.
ZAVA_EVAL_LATENCY_BUDGET=400 ZAVA_ENDPOINT=http://$ORCH uv run python -m tests.evals.run_evals
# Expect: 0 failures
```

---

## Step 7 — Day-2: change a prompt, ship the diff

### Invoke `/agent-builder`

```
Tighten PricingAgent's refusal rule for inventory questions.
Update only src/agents/pricing/prompts.py. Run uv run poe check.
```

### Invoke `/deploy-engineer`

```
/ship-it
```

The workflow detects that only `src/agents/pricing/` changed, so it builds + pushes one image and runs **`az containerapp update --image …`** for the `pricing` app only. Helm/AKS is untouched.

### Acceptance

```bash
az containerapp revision list -g $RG -n pricing -o table   # new active revision at $GIT_SHA
az containerapp revision list -g $RG -n supplier -o table  # unchanged
```

---

## Step 8 — CD pipeline (mode: `deploy-engineer`)

```
Generate .github/workflows/deploy.yml that runs the same `/ship-it` steps
on push to main, gated by the `check` job from .github/workflows/ci.yml.
Use OIDC federation (azure/login@v2 with federated-token) — never a client secret.
Pin Python to 3.13 with actions/setup-python@v5 BEFORE astral-sh/setup-uv@v3;
do not pass python-version on setup-uv (it is silently ignored on v3).
```

### Preflight: the OIDC identity must hold the right roles

The workflow logs in as the UAMI (`$UAMI`, federated to `repo:OWNER/REPO:ref:refs/heads/main`). Before merging, confirm the role set is complete:

```bash
PRINCIPAL=$(az identity show -n $UAMI -g $RG --query principalId -o tsv)
az role assignment list --assignee "$PRINCIPAL" --all \
  --query "[].{role:roleDefinitionName, scope:scope}" -o table
```

Required entries (all four must be present):

| Role | Scope |
|---|---|
| `Contributor` | `rg-zavashop-lab` |
| `Azure Kubernetes Service Cluster User Role` | `aks-zavashop` |
| `AcrPull` | `acrzavashop<rand>` |
| `Key Vault Secrets User` | `kv-zava-<rand>` |

If any row is missing, go back to [Lab 01 §3/§4/§7](../lab-01-environment-setup/README.md). The `Contributor` row is the one most teams forget — its absence surfaces as the misleading "**The resource with name '<acr>' ... could not be found**" in CI.

Also confirm the federated credential `gha-aks-lab-main` exists with `subject = repo:OWNER/REPO:ref:refs/heads/main`:

```bash
az identity federated-credential list --identity-name $UAMI -g $RG \
  --query "[].{name:name, subject:subject, issuer:issuer}" -o table
```

Acceptance:

- [ ] `permissions: id-token: write, contents: read` on the job.
- [ ] No `client-secret:` key in the workflow.
- [ ] `secrets.AZURE_CLIENT_ID` (= `UAMI_CLIENT_ID`), `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` set in repo secrets and referenced in the workflow.
- [ ] Image tag = `${{ github.sha }}` (short sha).
- [ ] Both `ci.yml` and `deploy.yml` use `actions/setup-python@v5` → `python-version: "3.13"` *before* `astral-sh/setup-uv@v3`.
- [ ] All four UAMI roles above are present.
- [ ] Federated credential `gha-aks-lab-main` exists.
- [ ] Smoke step waits/retries for external IP and `GET /healthz` before `POST /plan` (avoid fail-fast `curl (7)`).

---

## Step 9 — Tear-down

```bash
az group delete -n $RG --yes --no-wait
```

---

## ✅ Lab 05 done when…

- [ ] All four `infra/` artifacts were authored by `deploy-engineer` mode.
- [ ] `kubectl -n zavashop get pods` shows orchestrator `2/2 Running`.
- [ ] `az containerapp list -g $RG -o table` shows 8 healthy apps at the deploy SHA.
- [ ] `/plan` against the AKS LB returns a structured `Plan` for SKU `ZS-1042` / `store-101`.
- [ ] `ZAVA_EVAL_LATENCY_BUDGET=400 ZAVA_ENDPOINT=http://$ORCH uv run python -m tests.evals.run_evals` → 0 failures.
- [ ] `grep -rE ':latest' infra/` returns nothing.
- [ ] The Day-2 prompt-change ran through `agent-builder` → `/ship-it` without touching any other workload.
- [ ] `git log` for this lab shows only agent-authored commits and the CD pipeline run.

🎉 You've delivered ZavaShop on AKS + ACA, fully on **GitHub Copilot SDK + `gpt-5.5`**, with the **GitHub Copilot Custom Agents** as the primary author of every spec, code change, test, and infra artifact in this repo.

## What's next

- **Open issue and assign Copilot** to swap the in-memory MCP stores for Cosmos DB. The Coding Agent will follow `feature-from-issue.prompt.md`.
- **Replace the PAT** with a GitHub App + OIDC token broker (see `infra/aks/wif/README.md` stub).
- **Continuous evals** — add a CronJob on AKS that runs `tests/evals/` against production hourly and opens issues (assigned to Copilot) when scores drop.
- **OTel → Application Insights** — one env var per workload, wired through `deploy-engineer`.
