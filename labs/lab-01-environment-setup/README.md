# Lab 01 — Environment Setup

> ⏱ ~45 min · Provision the Azure foundation that the rest of the labs will deploy onto.

## What you build

By the end of this lab you'll have:

| Resource | Why |
|---|---|
| Resource group `rg-zavashop-lab` | Container for everything |
| Azure Container Registry (`acrzavashop<rand>`) | Stores agent images |
| AKS cluster (`aks-zavashop`) | Runs the orchestrator |
| Azure Container Apps env (`cae-zavashop`) | Runs specialist agents |
| Key Vault (`kv-zavashop-<rand>`) | Stores the GitHub Copilot token + MCP URLs |
| User-Assigned Managed Identity (UAMI) | Workload Identity for AKS/ACA |
| Local Python 3.11 env with `uv` | Dev loop |
| GitHub Copilot signed in in VS Code | Coding assistance |

## 0. Tooling check

```bash
az version            # ≥ 2.65
kubectl version --client
helm version          # ≥ 3.14
docker version
python --version      # 3.11+
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
export RG="rg-zavashop-lab"
export RAND="$RANDOM"
export ACR="acrzavashop${RAND}"
export AKS="aks-zavashop"
export CAE="cae-zavashop"
export KV="kv-zava-${RAND}"
export UAMI="uami-zavashop"
```

> 💡 **Copilot tip:** open VS Code in this repo, then open Copilot Chat and type `/explain` against `AGENTS.md` — Copilot will load the house rules into its context for the rest of the session.

## 2. Create the resource group + ACR

```bash
az group create -n $RG -l $LOCATION \
  --tags project=zavashop lab=01

az acr create -n $ACR -g $RG --sku Standard --admin-enabled false
```

## 3. Create the User-Assigned Managed Identity

```bash
az identity create -n $UAMI -g $RG -l $LOCATION
export UAMI_CLIENT_ID=$(az identity show -n $UAMI -g $RG --query clientId -o tsv)
export UAMI_PRINCIPAL_ID=$(az identity show -n $UAMI -g $RG --query principalId -o tsv)
export UAMI_RESOURCE_ID=$(az identity show -n $UAMI -g $RG --query id -o tsv)
```

Grant it `AcrPull` on ACR:

```bash
ACR_ID=$(az acr show -n $ACR -g $RG --query id -o tsv)
az role assignment create \
  --assignee-object-id $UAMI_PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope $ACR_ID
```

## 4. Create the AKS cluster (with OIDC + Workload Identity)

```bash
az aks create \
  -g $RG -n $AKS \
  --location $LOCATION \
  --node-count 2 \
  --node-vm-size Standard_D4s_v6 \
  --enable-oidc-issuer \
  --enable-workload-identity \
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

## 10. Save environment to `.env.lab`

```bash
cat > .env.lab <<EOF
LOCATION=$LOCATION
RG=$RG
ACR=$ACR
AKS=$AKS
CAE=$CAE
COPILOT_MODEL=gpt-5.5
KV=$KV
UAMI=$UAMI
UAMI_CLIENT_ID=$UAMI_CLIENT_ID
UAMI_RESOURCE_ID=$UAMI_RESOURCE_ID
AKS_OIDC=$AKS_OIDC
EOF
echo ".env.lab" >> .gitignore
```

## ✅ Verification

```bash
kubectl get nodes -o wide
az containerapp env show -n $CAE -g $RG --query properties.provisioningState   # Succeeded
uv run python -c "import agent_framework; print(agent_framework.__version__)"
uv run python -c "from agent_framework.github import GitHubCopilotAgent; print('copilot sdk ok')"
```

If all four checks pass, you're ready for [Lab 02 — Agent Creation](../lab-02-agent-creation/README.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Copilot SDK returns 401 | Your `GITHUB_TOKEN` is missing the Copilot scope, or your account doesn't have Copilot enabled. Re-issue a fine-grained PAT. |
| Copilot SDK returns 403 on `gpt-5.5` | Your Copilot plan may not include `gpt-5.5`. Confirm in github.com/settings/copilot. |
| `az aks create` hangs > 15 min | Check `az aks show ... --query provisioningState` in another shell; if `Failed`, delete and retry in a different region. |
| `kubectl` `Unauthorized` | Re-run `az aks get-credentials --overwrite-existing`. |
| Copilot Chat unable to reach GitHub | Corp proxy — set `HTTPS_PROXY` env var in VS Code's terminal profile. |
