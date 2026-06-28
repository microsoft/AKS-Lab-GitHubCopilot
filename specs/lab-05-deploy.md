# Lab 05 Deploy Spec

## Goal

Package and deploy the generated ZavaShop stock-out fleet through a repeatable `/ship-it` flow. The orchestrator runs on AKS with landing-zone controls, while four specialist agents and four MCP servers run on Azure Container Apps with scale-to-zero.

## Deployment Shape

- Build one reusable Python base image plus one image per service.
- Tag every image with the current git SHA; never use `latest`.
- Push images to `$ACR.azurecr.io/zavashop/<name>:<git-sha>`.
- Deploy the orchestrator to AKS with Helm.
- Deploy specialists and MCP servers to ACA through a reusable Bicep module.

## Services

| Service | Runtime | Target |
|---|---|---|
| base | Python 3.11 | ACR base image |
| orchestrator | FastAPI + GitHub Copilot SDK | AKS |
| inventory | FastAPI + GitHub Copilot SDK | ACA |
| supplier | FastAPI + GitHub Copilot SDK | ACA |
| logistics | FastAPI + GitHub Copilot SDK | ACA |
| pricing | FastAPI + GitHub Copilot SDK | ACA |
| inventory-mcp | FastMCP streamable HTTP | ACA |
| supplier-mcp | FastMCP streamable HTTP | ACA |
| shipping-mcp | FastMCP streamable HTTP | ACA |
| pricing-mcp | FastMCP streamable HTTP | ACA |

## AKS Requirements

- Assume Lab 01 already enabled Microsoft Entra ID, Azure RBAC, Azure Policy, Container Insights, and Defender for Cloud.
- Helm chart lives at `infra/aks/helm/zavashop/`.
- Orchestrator has two replicas by default.
- Use `orchestrator-sa` with Workload Identity annotation and pod label `azure.workload.identity/use: "true"`.
- Read `GITHUB-TOKEN` from Key Vault through Secrets Store CSI; no plaintext token in Helm values.
- Set non-root pod and container security contexts.
- Set resource requests and limits.
- Set topology spread constraints across zones.
- Expose `/healthz` and `/readyz` probes.
- Do not use `az aks get-credentials --admin` in CI.

## ACA Requirements

- Bicep module lives at `infra/aca/agent.bicep`.
- Deploy helper lives at `infra/aca/deploy.sh`.
- All eight ACA apps use the same UAMI.
- All eight ACA apps use Key Vault `secretRef` for `GITHUB_TOKEN`.
- Specialist agents receive their MCP endpoint through `ZAVA_*_MCP_URL` environment variables.
- Scale min replicas to 0, max replicas to 10, with HTTP concurrency set to 30.
- Keep ingress internal unless a service is explicitly designated public.

## Landing Zone Gates

Before changing live workloads, `/ship-it` must verify:

- AKS `aadProfile` is present and Azure RBAC is enabled.
- AKS Azure Policy add-on is enabled.
- AKS Defender security monitoring is enabled.
- Defender for Cloud `Containers` pricing tier is `Standard`.
- Defender for Cloud `KeyVaults` pricing tier is `Standard`.
- Image tags are git SHAs.
- No checked-in infra uses `:latest`.

## GitHub Actions Requirements

- Workflow path: `.github/workflows/deploy.yml`.
- Trigger on push to `main` after CI succeeds.
- Use `permissions: id-token: write, contents: read`.
- Use `azure/login@v2` with OIDC; never use a client secret.
- Use `actions/setup-python@v5` with `python-version: "3.13"` before `astral-sh/setup-uv@v3`.
- Build and push only changed service images after the first deployment.
- Wait for the AKS LoadBalancer IP and `/healthz` before invoking `/plan`.

## Refusal Conditions

- Refuse deployment if `git status --short` is non-empty.
- Refuse deployment if `uv run poe check` fails.
- Refuse deployment if required Lab 01 environment variables are absent.
- Refuse deployment if landing zone gates fail.
- Refuse deployment if any image tag is `latest`.

## Acceptance

- `az acr repository list -n $ACR -o tsv | sort` shows all 10 repositories.
- `az containerapp list -g $RG -o table` shows eight healthy ACA apps.
- `kubectl -n zavashop get pods` shows orchestrator replicas running.
- `/plan` returns a structured plan for `ZS-1042` at `store-101`.
- `ZAVA_EVAL_LATENCY_BUDGET=400 ZAVA_ENDPOINT=http://$ORCH uv run python -m tests.evals.run_evals` returns 0 failures.
