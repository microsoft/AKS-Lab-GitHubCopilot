# Skill: AKS Helm Chart for the Orchestrator

## Chart layout

```
infra/aks/helm/zavashop/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── _helpers.tpl
    ├── serviceaccount.yaml
    ├── secretproviderclass.yaml
    ├── deployment.yaml
    └── service.yaml
```

## values.yaml shape

```yaml
image:
  repository: ""        # acr.azurecr.io/zavashop/orchestrator
  tag: ""               # git short sha — REQUIRED, no default
  pullPolicy: IfNotPresent

workloadIdentity:
  clientId: ""          # UAMI client id, REQUIRED

keyVault:
  name: ""              # REQUIRED
tenantId: ""            # REQUIRED

a2a:
  inventory: ""
  supplier:  ""
  logistics: ""
  pricing:   ""

resources:
  requests: { cpu: "200m", memory: "256Mi" }
  limits:   { cpu: "1",    memory: "1Gi"  }
```

## serviceaccount.yaml

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orchestrator-sa
  namespace: {{ .Release.Namespace }}
  annotations:
    azure.workload.identity/client-id: {{ required "workloadIdentity.clientId" .Values.workloadIdentity.clientId }}
  labels:
    azure.workload.identity/use: "true"
```

## secretproviderclass.yaml

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: zavashop-github-token
spec:
  provider: azure
  parameters:
    usePodIdentity: "false"
    useVMManagedIdentity: "false"
    clientID: {{ .Values.workloadIdentity.clientId }}
    keyvaultName: {{ .Values.keyVault.name }}
    tenantId: {{ .Values.tenantId }}
    objects: |
      array:
        - |
          objectName: GITHUB-TOKEN
          objectType: secret
  secretObjects:
    - secretName: github-token
      type: Opaque
      data:
        - objectName: GITHUB-TOKEN
          key: token
```

## deployment.yaml essentials

- `metadata.labels.azure.workload.identity/use: "true"` on the **pod template**.
- `serviceAccountName: orchestrator-sa`.
- `topologySpreadConstraints` over `topology.kubernetes.io/zone`, `maxSkew: 1`.
- Mount the CSI volume; project `GITHUB_TOKEN` env via `secretKeyRef` to `github-token/token`.
- Env: `AZURE_CLIENT_ID`, `ZAVA_COPILOT_MODEL=gpt-5.5`, `ZAVA_COPILOT_TIMEOUT_SECONDS=120`, four `ZAVA_<NAME>_A2A_URL` from `.Values.a2a.*`.
- Probes: `/healthz`, `/readyz` on port 8080 (fleet runtime port — see deploy-engineer rule 7).

## Rules

- `helm lint` MUST pass.
- `image.tag` has no default — fail fast if not supplied.
- Never `value:` a secret. Always `secretKeyRef` or CSI projection.
- `replicaCount` defaults to 2.
