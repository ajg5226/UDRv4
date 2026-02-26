// Storage Account module

@description('Name of the Storage Account (must be globally unique, no hyphens)')
param name string

@description('Location for the Storage Account')
param location string

@description('Tags for the resource')
param tags object = {}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

// Blob container for raw data archive
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource rawContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'atlas-raw'
  properties: {
    publicAccess: 'None'
  }
}

output name string = storageAccount.name
output id string = storageAccount.id
output primaryEndpoint string = storageAccount.properties.primaryEndpoints.blob
