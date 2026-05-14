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
    keyVaultUrl: 'https://${keyVaultName}.vault.azure.net/secrets/GITHUB-TOKEN'
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
  minReplicas: 0
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

Fleet runtime port is **8080** (MCP servers pin it in source; specialists/orchestrator match for consistency).

```bicep
probes: [
  { type: 'Liveness',  httpGet: { path: '/healthz', port: 8080 }, periodSeconds: 10 }
  { type: 'Readiness', httpGet: { path: '/readyz',  port: 8080 }, periodSeconds: 5  }
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
- `exposeIngress: true` only for the orchestrator; specialists are internal-only.
