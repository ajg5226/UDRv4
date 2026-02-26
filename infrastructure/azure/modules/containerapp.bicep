// Container App module for Streamlit dashboard

@description('Name of the Container App')
param name string

@description('Location for the resource')
param location string

@description('Tags for the resource')
param tags object = {}

@description('Key Vault name for secrets')
param keyVaultName string

// Container Apps Environment
resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${name}-env'
  location: location
  tags: tags
  properties: {
    zoneRedundant: false
  }
}

// Container App
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8501  // Streamlit default port
        transport: 'auto'
        allowInsecure: false
      }
      secrets: []
    }
    template: {
      containers: [
        {
          name: 'atlas-dashboard'
          image: 'mcr.microsoft.com/azure-cli:latest'  // Placeholder - replace with actual image
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
          env: [
            {
              name: 'ATLAS_KEYVAULT_URL'
              value: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}'
            }
            {
              name: 'ATLAS_ENV'
              value: 'production'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

// Grant Container App access to Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource keyVaultAccessPolicy 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, containerApp.id, 'KeyVaultSecretsUser')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output name string = containerApp.name
output id string = containerApp.id
output url string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output principalId string = containerApp.identity.principalId
