param name string
param envId string
param image string
param registryServer string
param uamiId string
param uamiClientId string
param copilotModel string = 'gpt-5.5'
param mcpEndpoints object = {}
param exposeIngress bool = false
param keyVaultName string
param targetPort int = 8000
param location string = resourceGroup().location

var secretName = 'github-token'
var baseEnv = [
  {
    name: 'AZURE_CLIENT_ID'
    value: uamiClientId
  }
  {
    name: 'ZAVA_COPILOT_MODEL'
    value: copilotModel
  }
  {
    name: 'ZAVA_COPILOT_TIMEOUT_SECONDS'
    value: '120'
  }
  {
    name: 'GITHUB_TOKEN'
    secretRef: secretName
  }
]
var mcpEnv = [for endpoint in items(mcpEndpoints): {
  name: endpoint.key
  value: string(endpoint.value)
}]

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: {
    project: 'zavashop'
    lab: '05'
    agent: name
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uamiId}': {}
    }
  }
  properties: {
    managedEnvironmentId: envId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: exposeIngress
        targetPort: targetPort
        allowInsecure: false
        transport: 'auto'
      }
      secrets: [
        {
          name: secretName
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/GITHUB-TOKEN'
          identity: uamiId
        }
      ]
      registries: [
        {
          server: registryServer
          identity: uamiId
        }
      ]
    }
    template: {
      containers: [
        {
          name: name
          image: image
          env: concat(baseEnv, mcpEnv)
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: targetPort
              }
              periodSeconds: 10
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/readyz'
                port: targetPort
              }
              periodSeconds: 5
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 10
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '30'
              }
            }
          }
        ]
      }
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
