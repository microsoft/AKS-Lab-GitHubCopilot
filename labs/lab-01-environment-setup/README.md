# Lab 01 — Environment Setup

> ⏱ ~60 min · Provision the Azure foundation that the rest of the labs will deploy onto.

## ZavaShop story

**ZavaShop** is a fictional retail chain whose supply chain runs on a multi-agent system: an orchestrator on AKS coordinates four specialist agents (inventory, supplier, logistics, pricing) and four MCP tool servers running on Azure Container Apps. Before any agent code can ship, the platform team has to lay the Azure foundation — a registry to hold images, a cluster to host the orchestrator, an event-driven serverless surface for the specialists, a vault for the GitHub Copilot token, Entra-backed access control, Defender for Cloud coverage, and a single managed identity that ties them together. This lab is that foundation, framed as ZavaShop's "day 0" cloud bootstrap.

This lab follows the AKS landing zone accelerator design areas at workshop scale: resource organization, identity and access management, network topology, security, management/monitoring, and platform automation. The Microsoft Learn AKS landing zone accelerator article is marked for retirement, so use it as a design checklist and pair it with the current Azure Architecture Center AKS guidance when adapting this lab for production.

## Microsoft Learn knowledge for this lab

- [Azure Kubernetes Service (AKS) overview](https://learn.microsoft.com/azure/aks/intro-kubernetes) — why the orchestrator runs on AKS (long-lived, multi-replica, custom networking).
- [AKS landing zone accelerator](https://learn.microsoft.com/azure/cloud-adoption-framework/scenarios/app-platform/aks/landing-zone-accelerator) — the design areas this lab maps to: identity, networking, security, governance, monitoring, automation, and resource organization.
- [AKS architecture guidance](https://learn.microsoft.com/azure/architecture/reference-architectures/containers/aks-start-here) — the current production reference for AKS architecture decisions.
- [Azure Container Apps overview](https://learn.microsoft.com/azure/container-apps/overview) — why the 8 specialist + MCP services run on ACA (scale-to-zero, KEDA, no cluster ops).
- [Azure Container Registry introduction](https://learn.microsoft.com/azure/container-registry/container-registry-intro) — single registry shared by AKS and ACA, attached via `--attach-acr`.
- [Azure Key Vault overview](https://learn.microsoft.com/azure/key-vault/general/overview) — central store for the `GITHUB-TOKEN` secret consumed by every workload.
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview) — the UAMI is the single identity AKS pods, ACA apps, and GitHub Actions all federate to.
- [Microsoft Entra ID integration with AKS](https://learn.microsoft.com/azure/aks/enable-authentication-microsoft-entra-id) — cluster authentication uses Entra ID instead of local admin credentials.
- [Use Azure RBAC for Kubernetes Authorization](https://learn.microsoft.com/azure/aks/manage-azure-rbac) — authorization is controlled by Azure role assignments.
- [AKS Workload Identity](https://learn.microsoft.com/azure/aks/workload-identity-overview) — how the orchestrator pod borrows the UAMI without any secret in the cluster.
- [Workload Identity Federation](https://learn.microsoft.com/entra/workload-id/workload-identity-federation) — the mechanism behind both the AKS SA federation and the `gha-aks-lab-main` GitHub federation.
- [Configure GitHub Actions OIDC with Azure](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect) — exact subject format for the `repo:OWNER/REPO:ref:refs/heads/main` credential the CD workflow needs.
- [Microsoft Defender for Containers](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-introduction) — threat detection and posture management for AKS, ACR, and Kubernetes workloads.
- [Azure Monitor Container Insights](https://learn.microsoft.com/azure/azure-monitor/containers/container-insights-overview) — operational telemetry for AKS nodes, pods, and containers.

## What you build

By the end of this lab you'll have:

| Resource | Why |
|---|---|
| Resource group `rg-zavashop-lab` | Container for everything |
| Azure Container Registry (`acrzavashop<rand>`) | Stores agent images |
| AKS cluster (`aks-zavashop`) | Runs the orchestrator with Entra ID, Azure RBAC, Azure Policy, monitoring, and Defender enabled |
| Azure Container Apps env (`cae-zavashop`) | Runs specialist agents |
| Key Vault (`kv-zavashop-<rand>`) | Stores the GitHub Copilot token + MCP URLs |
| Log Analytics workspace (`law-zavashop-<rand>`) | Collects AKS monitoring and Defender signals |
| User-Assigned Managed Identity (UAMI) | Workload Identity for AKS/ACA |
| Entra ID security group | Human operator access to AKS through Azure RBAC |
| Defender for Cloud plans | Container and Key Vault threat protection |
| Local Python 3.11 env with `uv` | Dev loop |
| GitHub Copilot signed in in VS Code | Coding assistance |

## 0. Tooling check

```bash
az version            # ≥ 2.65
kubectl version --client
helm version          # ≥ 3.14
docker version
python --version      # 3.11+ (CI runs on 3.13 — match it locally to avoid surprises)
uv --version          # https://docs.astral.sh/uv/
```

Install anything missing:
- `brew install azure-cli kubectl helm uv` (macOS)
- `winget install --id Microsoft.AzureCLI` (Windows)

## 1. Sign in

```bash
az login --use-device-code
az account set --subscription "<your-subscription-id>"

# Variables we'll reuse
export LOCATION="eastus2"
export RG="rg-kinfey-zavashop-lab"
export RAND="$RANDOM"
export ACR="acrzavashop${RAND}"
export AKS="aks-zavashop"
export CAE="cae-zavashop"
export KV="kv-zava-${RAND}"
export LAW="law-zava-${RAND}"
export UAMI="uami-zavashop"
export AKS_ADMINS_GROUP="zavashop-aks-admins"
```

> 💡 **Copilot tip:** open VS Code in this repo, then open Copilot Chat and type `/explain` against `AGENTS.md` — Copilot will load the house rules into its context for the rest of the session.

## 2. Create the resource group + ACR + Log Analytics

```bash
az group create -n $RG -l $LOCATION \
  --tags project=zavashop lab=01

az acr create -n $ACR -g $RG --sku Standard --admin-enabled false

az monitor log-analytics workspace create \
  -g $RG -n $LAW -l $LOCATION \
  --tags project=zavashop lab=01

export LAW_ID=$(az monitor log-analytics workspace show \
  -g $RG -n $LAW --query id -o tsv)
```

> Landing zone note: production environments usually place shared monitoring, DNS, firewall, and policy in platform subscriptions. This lab keeps everything in one resource group so the end-to-end flow is easy to tear down.

## 3. Create the User-Assigned Managed Identity

```bash
az identity create -n $UAMI -g $RG -l $LOCATION
export UAMI_CLIENT_ID=$(az identity show -n $UAMI -g $RG --query clientId -o tsv)
export UAMI_PRINCIPAL_ID=$(az identity show -n $UAMI -g $RG --query principalId -o tsv)
export UAMI_RESOURCE_ID=$(az identity show -n $UAMI -g $RG --query id -o tsv)
```

Grant it the four roles it will need (data-plane pulls + control-plane deploys + KV + AKS kubeconfig):

```bash
ACR_ID=$(az acr show -n $ACR -g $RG --query id -o tsv)
RG_ID=$(az group show -n $RG --query id -o tsv)

# 1. Pod-level image pull (data plane)
az role assignment create \
  --assignee-object-id $UAMI_PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope $ACR_ID

# 2. Control-plane access for `az acr build`, ACA Bicep deploy, AKS updates.
#    NOTE: AcrPull alone is NOT enough — it omits Microsoft.ContainerRegistry/registries/read,
#    so `az acr show` returns the misleading "could not be found" error in CI.
az role assignment create \
  --assignee-object-id $UAMI_PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role Contributor \
  --scope $RG_ID
```

> 💡 **Why both?** `AcrPull` is data-plane only (the kubelet uses it). `Contributor` on the RG gives the GitHub Actions OIDC identity the control-plane reads + writes it needs for `az acr build`, `az containerapp ...`, and `az aks ...` during `/ship-it`. The AKS-specific Cluster User role is added in step 4 once the cluster exists.

## 3.5. Add Microsoft Entra ID operator access

Create a dedicated Entra ID security group for human AKS administrators. This keeps cluster access auditable and avoids assigning broad subscription roles directly to individual users.

```bash
az ad group create \
  --display-name $AKS_ADMINS_GROUP \
  --mail-nickname $AKS_ADMINS_GROUP

export AKS_ADMINS_GROUP_ID=$(az ad group show \
  --group $AKS_ADMINS_GROUP --query id -o tsv)

export MY_OID=$(az ad signed-in-user show --query id -o tsv)

az ad group member add \
  --group $AKS_ADMINS_GROUP_ID \
  --member-id $MY_OID
```

> If your tenant blocks group creation, ask an Entra administrator to create the group and give you the object ID. Continue with `export AKS_ADMINS_GROUP_ID="<group-object-id>"`.

## 4. Create the AKS cluster (with OIDC + Workload Identity)

```bash
az aks create \
  -g $RG -n $AKS \
  --location $LOCATION \
  --node-count 2 \
  --node-vm-size Standard_D4s_v6 \
  --enable-aad \
  --enable-azure-rbac \
  --aad-admin-group-object-ids $AKS_ADMINS_GROUP_ID \
  --enable-oidc-issuer \
  --enable-workload-identity \
  --enable-addons monitoring,azure-policy \
  --workspace-resource-id $LAW_ID \
  --network-plugin azure --network-plugin-mode overlay \
  --attach-acr $ACR \
  --generate-ssh-keys \
  --tags project=zavashop lab=01

az aks get-credentials -g $RG -n $AKS --overwrite-existing
kubectl get nodes
```

Federate the UAMI to the orchestrator service account (we'll create the SA in Lab 05, but federate now):

```bash
export AKS_OIDC=$(az aks show -g $RG -n $AKS --query oidcIssuerProfile.issuerUrl -o tsv)

az identity federated-credential create \
  --name fc-orchestrator \
  --identity-name $UAMI \
  --resource-group $RG \
  --issuer $AKS_OIDC \
  --subject system:serviceaccount:zavashop:orchestrator-sa \
  --audiences api://AzureADTokenExchange
```

Federate the UAMI to **GitHub Actions** (`main` branch) so `/ship-it` can OIDC-login without a client secret:

```bash
# Replace OWNER/REPO with your fork (e.g. kinfey/AKS-Lab).
export GH_REPO_SLUG="OWNER/REPO"

az identity federated-credential create \
  --name gha-aks-lab-main \
  --identity-name $UAMI \
  --resource-group $RG \
  --issuer https://token.actions.githubusercontent.com \
  --subject "repo:${GH_REPO_SLUG}:ref:refs/heads/main" \
  --audiences api://AzureADTokenExchange
```

Also grant the UAMI **AKS Cluster User** so the GitHub Actions runner can fetch a kubeconfig via `az aks get-credentials`:

```bash
AKS_ID=$(az aks show -g $RG -n $AKS --query id -o tsv)
az role assignment create \
  --assignee-object-id $UAMI_PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Azure Kubernetes Service Cluster User Role" \
  --scope $AKS_ID

az role assignment create \
  --assignee $AKS_ADMINS_GROUP_ID \
  --role "Azure Kubernetes Service RBAC Cluster Admin" \
  --scope $AKS_ID
```

> Landing zone note: this lab uses Azure CNI Overlay to keep IP consumption low. In production, validate hub-and-spoke connectivity, private endpoints, firewall egress, ingress controller choice, DNS, and private cluster requirements against your platform landing zone.

## 5. Create the Azure Container Apps environment

```bash
az extension add -n containerapp --upgrade
az provider register -n Microsoft.App --wait

az containerapp env create \
  -n $CAE -g $RG -l $LOCATION \
  --logs-destination none \
  --tags project=zavashop lab=01
```

## 6. Model provider — GitHub Copilot SDK (`gpt-5.5`)

**This repo uses a single model provider for every agent: the GitHub Copilot SDK with `model="gpt-5.5"`.** No Azure OpenAI deployment is required. Authentication is via a GitHub token that the SDK reads from `GITHUB_TOKEN`.

For the lab we use a **fine-grained Personal Access Token** with the Copilot read scope. In production replace it with a GitHub App + OIDC federation (see Lab 05 § 3.3).

```bash
# https://github.com/settings/personal-access-tokens/new
# Scopes: Copilot (read), no repo write.
export GITHUB_TOKEN="<your-fine-grained-PAT>"

# Sanity check the token can reach the Copilot SDK
uv run python - <<'PY'
import asyncio
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions

async def main():
    agent = GitHubCopilotAgent(
        name="smoke",
        instructions="Reply briefly.",
        options=GitHubCopilotOptions(model="gpt-5.5"),
    )
    result = await agent.run("Say hi from gpt-5.5")
    print(result.output_text)

asyncio.run(main())
PY
```

> If you don't yet have the `agent-framework` `github-copilot` extra installed, jump to step 8 first and come back.

## 7. Create Key Vault

```bash
az keyvault create -n $KV -g $RG -l $LOCATION --enable-rbac-authorization
KV_ID=$(az keyvault show -n $KV -g $RG --query id -o tsv)

az role assignment create \
  --assignee-object-id $UAMI_PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope $KV_ID

# Also grant your own user so you can write secrets in later labs
MY_OID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create \
  --assignee $MY_OID \
  --role "Key Vault Secrets Officer" \
  --scope $KV_ID
```

## 7.5. Enable Defender for Cloud baseline

Enable Defender for Containers and Key Vault at subscription scope, then attach the AKS Defender profile to the Log Analytics workspace. This gives the workshop deployment the same security guardrails expected in an AKS landing zone: runtime threat detection, image and cluster posture signals, and centralized findings in Defender for Cloud.

```bash
az provider register -n Microsoft.Security --wait

az security pricing create -n Containers --tier Standard
az security pricing create -n KeyVaults --tier Standard

az aks update \
  -g $RG -n $AKS \
  --enable-defender \
  --defender-config logAnalyticsWorkspaceResourceId=$LAW_ID

az security assessment-metadata list \
  --query "[?contains(displayName, 'Kubernetes')].displayName" \
  -o table
```

If your subscription is governed by central security policy, these settings might already be enforced or blocked from a lab subscription. In that case, capture the existing policy assignment and continue; Lab 05 will still verify that Defender and Azure Policy coverage are visible.

## 8. Bootstrap the local Python project

```bash
cd /path/to/AKS-Lab
uv init --python 3.11 --no-readme .
uv add fastapi 'uvicorn[standard]' httpx structlog pydantic-settings \
       azure-identity azure-keyvault-secrets opentelemetry-sdk
uv add 'agent-framework[github-copilot]'
uv add --dev pytest pytest-asyncio ruff pyright poethepoet
```

> The `github-copilot` extra pulls in the Copilot SDK provider (bundled inside `agent-framework` ≥ 1.3). Copilot Chat can help: ask `/explain how to install the agent-framework github-copilot extra in this repo`.

Create `pyproject.toml` poe tasks (Copilot can do this — open the file and type `# poe tasks: check = ruff + pyright + pytest` then accept the suggestion).

## 9. Sign in to GitHub Copilot and load the custom agents

In VS Code:
1. Install **GitHub Copilot** and **GitHub Copilot Chat** extensions.
2. `Cmd/Ctrl+Shift+P` → **GitHub Copilot: Sign In**.
3. `Cmd/Ctrl+Shift+P` → **Developer: Reload Window** — this lets VS Code discover `.github/agents/*.agent.md`.
4. Open Copilot Chat → open the **agent picker** (type `/` in the chat input). You should see the six ZavaShop custom agents:
   - `requirements-analyst`
   - `mcp-builder`
   - `agent-builder`
   - `orchestrator-architect`
   - `test-author`
   - `deploy-engineer`
5. Verify chat settings: `Cmd/Ctrl+,` → search `chat.agent.allowedNetworkDomains` → ensure `github.com`, `*.azurecr.io`, and your ACR FQDN are allowed.

> **From here on, every code change goes through a custom agent** (see `AGENTS.md` §1.1). Pick the agent whose `Owns` slice matches the file you are editing and invoke it with `/<name>`.

## 10. Save environment to `.env.lab` (and gitignore it!)

> ⚠️ `.env.lab` holds local deployment metadata, not the live `GITHUB_TOKEN`. Keep the token in your shell only long enough to seed Key Vault, then let Lab 05 project it through CSI. Never commit `.env.lab`, and use a glob so a copy dropped under `src/` or any subfolder is also ignored.

```bash
# Always written at the repo root, never under src/.
export AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
export AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)

cat > .env.lab <<EOF
LOCATION=$LOCATION
RG=$RG
RAND=$RAND
ACR=$ACR
AKS=$AKS
CAE=$CAE
COPILOT_MODEL=gpt-5.5
KV=$KV
LAW=$LAW
LAW_ID=$LAW_ID
UAMI=$UAMI
UAMI_CLIENT_ID=$UAMI_CLIENT_ID
UAMI_PRINCIPAL_ID=$UAMI_PRINCIPAL_ID
UAMI_RESOURCE_ID=$UAMI_RESOURCE_ID
AKS_OIDC=$AKS_OIDC
AKS_ADMINS_GROUP=$AKS_ADMINS_GROUP
AKS_ADMINS_GROUP_ID=$AKS_ADMINS_GROUP_ID
AKS_ID=$AKS_ID
KV_ID=$KV_ID
ACR_ID=$ACR_ID
RG_ID=$RG_ID
AZURE_SUBSCRIPTION_ID=$AZURE_SUBSCRIPTION_ID
AZURE_TENANT_ID=$AZURE_TENANT_ID
GH_REPO_SLUG=$GH_REPO_SLUG
EOF

# Glob-ignore so any *.env.lab anywhere in the tree is excluded.
grep -qxF '**/.env.lab' .gitignore || echo '**/.env.lab' >> .gitignore
grep -qxF '*.env.lab'    .gitignore || echo '*.env.lab'    >> .gitignore

# Refuse to continue if the file was ever tracked.
if git ls-files --error-unmatch .env.lab src/.env.lab >/dev/null 2>&1; then
  echo "ERROR: .env.lab is tracked in git history — rotate the token and run \`git rm --cached\`." >&2
  exit 1
fi
```

## 11. Register the three GitHub Actions secrets

The deploy workflow (`/ship-it`, `.github/workflows/deploy.yml`) OIDC-logs in as the UAMI you just federated. Set these once in **GitHub → repo → Settings → Secrets and variables → Actions**:

```bash
export SUB=$(az account show --query id -o tsv)
export TENANT=$(az account show --query tenantId -o tsv)

# Using the gh CLI (recommended):
gh secret set AZURE_SUBSCRIPTION_ID --body "$SUB"            --repo "$GH_REPO_SLUG"
gh secret set AZURE_TENANT_ID       --body "$TENANT"         --repo "$GH_REPO_SLUG"
gh secret set AZURE_CLIENT_ID       --body "$UAMI_CLIENT_ID" --repo "$GH_REPO_SLUG"
```

## ✅ Verification

```bash
kubectl get nodes -o wide
az containerapp env show -n $CAE -g $RG --query properties.provisioningState   # Succeeded
az aks show -g $RG -n $AKS --query aadProfile -o yaml

az aks show -g $RG -n $AKS \
  --query addonProfiles.azurepolicy.enabled -o tsv

az aks show -g $RG -n $AKS \
  --query securityProfile.defender.securityMonitoring.enabled -o tsv

az security pricing show -n Containers \
  --query pricingTier -o tsv                 # Standard

az security pricing show -n KeyVaults \
  --query pricingTier -o tsv                 # Standard
uv run python -c "import agent_framework; print(agent_framework.__version__)"
uv run python -c "from agent_framework.github import GitHubCopilotAgent; print('copilot sdk ok')"
```

If these checks pass, you're ready for [Lab 02 — Agent Creation](../lab-02-agent-creation/README.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Copilot SDK returns 401 | Your `GITHUB_TOKEN` is missing the Copilot scope, or your account doesn't have Copilot enabled. Re-issue a fine-grained PAT. |
| Copilot SDK returns 403 on `gpt-5.5` | Your Copilot plan may not include `gpt-5.5`. Confirm in github.com/settings/copilot. |
| `az aks create` hangs > 15 min | Check `az aks show ... --query provisioningState` in another shell; if `Failed`, delete and retry in a different region. |
| `kubectl` `Unauthorized` | Re-run `az aks get-credentials --overwrite-existing`. |
| Copilot Chat unable to reach GitHub | Corp proxy — set `HTTPS_PROXY` env var in VS Code's terminal profile. |
| GitHub Actions: `The resource with name '<acr>' ... could not be found` | The UAMI is missing `Contributor` (or any role that grants `Microsoft.ContainerRegistry/registries/read`) on the RG. `AcrPull` is data-plane only and produces this **misleading "not found"** error. Re-run step 3. |
| GitHub Actions OIDC: `AADSTS70021` / `no matching federated identity record` | The federated credential `gha-aks-lab-main` is missing or its `subject` doesn't match `repo:OWNER/REPO:ref:refs/heads/main`. Re-run the `az identity federated-credential create` in step 4. |
| `.env.lab` accidentally committed | Rotate the GitHub PAT *immediately*, then `git rm --cached path/to/.env.lab && git commit && git push`. For full history scrub use `git filter-repo` (destructive — coordinate with collaborators). |
