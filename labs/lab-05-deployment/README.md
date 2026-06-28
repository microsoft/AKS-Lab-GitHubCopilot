# Lab 05 — Deployment & Run via Custom Agents

> ⏱ ~60 min · The **`deploy-engineer`** custom mode owns this entire lab. You drive the packaged rollout through `/ship-it` and verify with smoke + evals against the live AKS endpoint.

## ZavaShop story

ZavaShop's first store goes live next week. The orchestrator needs steady, predictable capacity in front of a load balancer — that lives on **AKS**, behind Microsoft Entra ID, Azure RBAC, Workload Identity, Azure Policy, Defender for Cloud, and a CSI-mounted token. The four specialists and four MCP servers are bursty (peak hour vs. midnight), so they live on **Azure Container Apps** with scale-to-zero. The whole application is packaged as versioned container images and rolled out by a single `/ship-it` workflow that the on-call engineer can trigger from chat. The same workflow runs again on every push to `main` via GitHub Actions, using OIDC federation to the same UAMI from Lab 01. By the end of this lab, ZavaShop has a real, observable production endpoint that survives a Day-2 prompt change without touching infra.

## Microsoft Learn knowledge for this lab

- [AKS Helm quickstart](https://learn.microsoft.com/azure/aks/quickstart-helm) — the chart pattern under `infra/aks/helm/zavashop/`.
- [AKS landing zone accelerator](https://learn.microsoft.com/azure/cloud-adoption-framework/scenarios/app-platform/aks/landing-zone-accelerator) — design areas used as deployment gates for identity, networking, security, monitoring, and automation.
- [Microsoft Entra ID integration with AKS](https://learn.microsoft.com/azure/aks/enable-authentication-microsoft-entra-id) — cluster authentication and human operator access.
- [Use Azure RBAC for Kubernetes Authorization](https://learn.microsoft.com/azure/aks/manage-azure-rbac) — authorization through Azure role assignments rather than local cluster secrets.
- [Microsoft Defender for Containers](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-introduction) — Defender for Cloud coverage for AKS, ACR, and Kubernetes workloads.
- [Azure Policy for AKS](https://learn.microsoft.com/azure/aks/use-azure-policy) — policy add-on used for guardrails and compliance reporting.
- [Azure Container Apps with Bicep](https://learn.microsoft.com/azure/container-apps/microservices-bicep) — the parameterized module reused for 8 ACA apps.
- [ACR Tasks](https://learn.microsoft.com/azure/container-registry/container-registry-tasks-overview) — `az acr build` for daemon-free, native `linux/amd64` builds.
- [Secrets Store CSI driver on AKS](https://learn.microsoft.com/azure/aks/csi-secrets-store-driver) — how the orchestrator Pod reads `GITHUB-TOKEN` without an environment variable.
- [AKS Workload Identity](https://learn.microsoft.com/azure/aks/workload-identity-overview) — the SA → UAMI federation that lets `DefaultAzureCredential` work in-pod.
- [GitHub Actions OIDC federation to Azure](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect) — the `gha-aks-lab-main` credential the CD workflow uses (no client secret).
- [KEDA scale rules on Container Apps](https://learn.microsoft.com/azure/container-apps/scale-app) — HTTP scale rule used by the 4 specialists and 4 MCPs.
- [Bicep `what-if` deployments](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if) — recommended preflight before any `/ship-it` re-run.

## What you'll produce

| Path | Owner (agent) |
|---|---|
| `infra/aca/agent.bicep` | `deploy-engineer` |
| `infra/aca/deploy.sh` | `deploy-engineer` |
| `infra/aks/helm/zavashop/**` | `deploy-engineer` |
| `infra/aks/wif/README.md` | `deploy-engineer` |
| `.github/workflows/deploy.yml` | `deploy-engineer` |

All authored by the custom mode using `.github/skills/aca-bicep/SKILL.md` + `.github/skills/aks-helm/SKILL.md`.

## Landing zone deployment gates

Before `/ship-it` changes live workloads, verify these Lab 01 platform controls are present. For a workshop subscription, the checks are intentionally lightweight; for production, map each item to your organization's management group policy assignments and hub-spoke network design.

| Gate | Required state |
|---|---|
| Resource organization | `project=zavashop` and `lab=<lab-number>` tags on resource groups and deployed resources |
| Identity | AKS uses Microsoft Entra ID and Azure RBAC; no local admin kubeconfig in CI |
| Workload identity | Orchestrator service account federates to the UAMI; GitHub Actions uses OIDC to the same UAMI |
| Secrets | `GITHUB-TOKEN` comes from Key Vault through CSI, never plaintext Helm values |
| Security | Defender for Containers and Key Vault plans are `Standard`; AKS Defender profile is enabled |
| Governance | Azure Policy add-on is enabled on AKS |
| Management | Container Insights sends AKS telemetry to the Lab 01 Log Analytics workspace |
| Automation | Image tags are the git SHA; no `:latest` in manifests or workflows |

Preflight commands:

```bash
source .env.lab

az aks show -g $RG -n $AKS --query aadProfile -o yaml

az aks show -g $RG -n $AKS \
  --query addonProfiles.azurepolicy.enabled -o tsv

az aks show -g $RG -n $AKS \
  --query securityProfile.defender.securityMonitoring.enabled -o tsv

az security pricing show -n Containers \
  --query pricingTier -o tsv

az security pricing show -n KeyVaults \
  --query pricingTier -o tsv
```

---

## Step 1 — Spec the rollout (mode: `requirements-analyst`)

### Invoke `/requirements-analyst`

```
We need the deploy story:
- Package the generated app so demos can deploy quickly: one base image, one image per service, all tagged with the git SHA.
- ACA Bicep module reused for 4 specialists + 4 MCP servers (8 ACA apps total).
- Helm chart for the orchestrator on AKS, with Workload Identity, CSI-projected
  GITHUB_TOKEN from Key Vault, topology spread, 2 replicas.
- AKS deployment must assume the Lab 01 landing zone baseline: Entra ID,
  Azure RBAC, Azure Policy, Container Insights, and Defender for Cloud.
- One `/ship-it` workflow that builds, pushes, rolls, smokes.
- A GitHub Actions workflow that runs the same `/ship-it` steps on push to main.
```

Output: `specs/lab-05-deploy.md`. Handoff → `deploy-engineer`.

---

## Step 2 — Build base + service images (mode: `deploy-engineer`)

### Invoke `/deploy-engineer`

```
Generate src/Dockerfile.base per .github/skills/aca-bicep/SKILL.md style
(multi-stage, non-root zava uid 10001, EXPOSE 8000). Then package the
application as all 10 images (1 base + 9 services) tagged with the git SHA:
$ACR.azurecr.io/zavashop/<name>:$(git rev-parse --short HEAD). Push to ACR.
Run the quality gate first; refuse if dirty or red.
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
The chart must assume a landing-zone AKS cluster: Entra ID and Azure RBAC are
cluster-level controls, while the chart must set Workload Identity labels,
non-root pod security context, resource requests/limits, topology spread,
readiness/liveness probes, and CSI-based Key Vault secret projection. Run
`helm lint` and `helm template` with placeholder values.
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
4. Validating Entra ID + Azure RBAC access for human operators.
5. Validating Defender for Cloud, Azure Policy, and Container Insights.
6. Production migration to GitHub App + OIDC token broker (stub).
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
5. Re-run the landing zone preflight checks for Entra ID, Azure Policy, monitoring, and Defender.
6. `bash infra/aca/deploy.sh`.
7. `helm upgrade --install zavashop infra/aks/helm/zavashop --set image.tag=$GIT_SHA …`.
8. `kubectl -n zavashop rollout status deploy/orchestrator`.
9. Wait for external IP + `/healthz` readiness, then run smoke + evals against the public IP.

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

For human operators, the Entra ID admin group from Lab 01 should also have `Azure Kubernetes Service RBAC Cluster Admin` on the AKS cluster scope. CI should not need that role; CI only needs enough access to deploy through the workflow.

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
- [ ] Landing zone preflight runs before deploy and fails closed if Defender, Azure Policy, or Entra/Azure RBAC checks are missing.
- [ ] Both `ci.yml` and `deploy.yml` use `actions/setup-python@v5` → `python-version: "3.13"` *before* `astral-sh/setup-uv@v3`.
- [ ] All four UAMI roles above are present.
- [ ] Federated credential `gha-aks-lab-main` exists.
- [ ] No workflow step calls `az aks get-credentials --admin`.
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
- [ ] AKS shows Entra ID + Azure RBAC enabled; Azure Policy add-on enabled; Defender profile enabled.
- [ ] Defender for Cloud `Containers` and `KeyVaults` plans return `Standard`.
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
