---
applyTo: "infra/**,**/Dockerfile,**/Chart.yaml,**/values.yaml"
---

# AKS + ACA infrastructure conventions

## Container images

- Base: `python:3.11-slim`.
- Multi-stage: `builder` stage installs deps with `uv pip install --system`, runtime stage copies `/usr/local/lib/python3.11/site-packages` + app code.
- Non-root user: `RUN useradd -m -u 10001 zava` then `USER zava`.
- `EXPOSE 8000`. Entrypoint: `uvicorn app.server:app --host 0.0.0.0 --port 8000`.
- Image label `org.opencontainers.image.source` set to repo URL.

## Helm (AKS)

- One chart at `infra/aks/helm/zavashop`. Each agent is a subchart or a `values-<agent>.yaml`.
- Required values: `image.repository`, `image.tag`, `workloadIdentity.clientId`, `mcp.endpoints.<name>`.
- Every Deployment includes:
  - `serviceAccountName: <agent>-sa` with `azure.workload.identity/use: "true"`.
  - `readinessProbe` and `livenessProbe` on `/readyz` and `/healthz`.
  - `resources.requests`: `200m` CPU / `256Mi`. `limits`: `1` CPU / `1Gi`.
  - `topologySpreadConstraints` across zones for the orchestrator.

## Bicep (ACA)

- `infra/aca/main.bicep` parameters: `acrName`, `envName`, `uamiId`, `copilotModel`.
- Each agent module declares `scale.minReplicas: 0`, `maxReplicas: 10`, `rules` with `http` concurrent-requests = 30.
- All env vars referencing secrets use `secretRef`. Secret values are pulled from Key Vault via the `keyVaultUrl` property on the container app.

## Networking

- AKS uses Azure CNI Overlay, private cluster, API server VNet integration off (lab simplicity — flag for production).
- ACA env is **internal-only**; the only public ingress is the orchestrator on AKS, fronted by an Azure Application Gateway / nginx.
- Service-to-service traffic between AKS and ACA goes over the shared VNet via the ACA env's static internal IP.

## Tags

Every Azure resource: `project=zavashop`, `lab=<n>`, `owner=<your-alias>`.
