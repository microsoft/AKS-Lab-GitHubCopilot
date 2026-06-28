# Skill: ACA Bicep Module

## `infra/aca/agent.bicep` parameters

```bicep
param name string
param envId string                        // ACA environment resource id
param image string                        // full ACR path incl. :<git-sha>
param uamiId string                       // user-assigned managed identity id
param uamiClientId string
param copilotModel string = 'gpt-5.5'
param mcpEndpoints object = {}            // map: ZAVA_<KEY>_MCP_URL -> value
param exposeIngress bool = false
param keyVaultName string
param targetPort int = 8000
param minReplicas int = 1
```

## Container env (mandatory)

```bicep
env: [
  { name: 'AZURE_CLIENT_ID',     value: uamiClientId }
  { name: 'ZAVA_COPILOT_MODEL',  value: copilotModel }
  { name: 'ZAVA_COPILOT_TIMEOUT_SECONDS', value: '120' }
  { name: 'GITHUB_TOKEN',        secretRef: 'github-token' }
  // Spread the mcpEndpoints map into ZAVA_*_MCP_URL entries
]
secrets: [
  {
    name: 'github-token'
    keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/GITHUB-TOKEN'
    identity: uamiId
  }
]
```

## Identity

```bicep
identity: {
  type: 'UserAssigned'
  userAssignedIdentities: { '${uamiId}': {} }
}
```

## Scale rule (always)

```bicep
scale: {
  minReplicas: minReplicas
  maxReplicas: 10
  rules: [
    {
      name: 'http-concurrency'
      http: { metadata: { concurrentRequests: '30' } }
    }
  ]
}
```

## Probes

Agents use runtime port **8000**; MCP servers use **8080**. Probe `targetPort` so one module works for both.

```bicep
probes: [
  { type: 'Liveness',  httpGet: { path: '/healthz', port: targetPort }, periodSeconds: 10 }
  { type: 'Readiness', httpGet: { path: '/readyz',  port: targetPort }, periodSeconds: 5  }
]
```

## Tags (mandatory)

```bicep
tags: {
  project: 'zavashop'
  lab: '05'
  agent: name
}
```

## Rules

- Image tag is the git SHA. `:latest` is a build error.
- No `value:` for secrets — only `secretRef`.
- Lab 05 sets `exposeIngress: true` and `minReplicas: 1` for specialists and MCPs so AKS smoke/eval calls can reach ACA FQDNs reliably. Production should revisit private ingress and scale-to-zero once DNS/networking and cold-start budgets are designed.
