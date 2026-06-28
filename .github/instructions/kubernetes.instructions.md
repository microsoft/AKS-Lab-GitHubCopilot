---
applyTo: "infra/**,**/Dockerfile,**/Chart.yaml,**/values.yaml"
---

# AKS + ACA infrastructure conventions

## Container images

- Base: `python:3.11-slim`.
- Multi-stage: `builder` stage installs deps with `uv pip install --system`, runtime stage copies `/usr/local/lib/python3.11/site-packages` + app code.
- Non-root user: `RUN useradd -m -u 10001 zava` then `USER zava`.
- Agents expose port `8000` and run uvicorn on `0.0.0.0:8000`; MCP servers expose port `8080` and run FastMCP streamable HTTP on `/mcp`.
- Image label `org.opencontainers.image.source` set to repo URL.

## Helm (AKS)

- One chart at `infra/aks/helm/zavashop`. Each agent is a subchart or a `values-<agent>.yaml`.
- Required values: `image.repository`, `image.tag`, `workloadIdentity.clientId`, `keyVault.name`, `tenantId`, and `a2a.<name>` specialist URLs.
- Every Deployment includes:
  - `serviceAccountName: <agent>-sa` with `azure.workload.identity/use: "true"`.
  - `readinessProbe` and `livenessProbe` on `/readyz` and `/healthz`.
  - `resources.requests`: `200m` CPU / `256Mi`. `limits`: `1` CPU / `1Gi`.
  - `topologySpreadConstraints` across zones for the orchestrator.

## Bicep (ACA)

- `infra/aca/main.bicep` parameters: `acrName`, `envName`, `uamiId`, `copilotModel`.
- Each ACA module accepts `minReplicas`; Lab 05 deploys specialists and MCPs with `minReplicas: 1` for reliable smoke/eval runs, `maxReplicas: 10`, and an HTTP concurrent-requests rule of 30.
- All env vars referencing secrets use `secretRef`. Secret values are pulled from Key Vault via the `keyVaultUrl` property on the container app.

## Networking

- AKS uses Azure CNI Overlay, private cluster, API server VNet integration off (lab simplicity — flag for production).
- Lab 05 exposes ACA specialists and MCP servers with HTTPS ingress so the AKS orchestrator can call their FQDNs from the lab network. Production landing zones should prefer private ingress, private DNS, and controlled egress once VNet integration is in place.

## Tags

Every Azure resource: `project=zavashop`, `lab=<n>`, `owner=<your-alias>`.
