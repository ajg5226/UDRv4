// ATLAS V1 - Azure Infrastructure
// Main Bicep template for deploying all resources

@description('Environment name (dev, staging, prod)')
param environment string = 'dev'

@description('Azure region for resources')
param location string = resourceGroup().location

@description('Base name for resources')
param baseName string = 'atlas'

@description('SQL Server administrator login')
@secure()
param sqlAdminLogin string

@description('SQL Server administrator password')
@secure()
param sqlAdminPassword string

// Variables
var resourcePrefix = '${baseName}-${environment}'
var tags = {
  Environment: environment
  Application: 'ATLAS'
  ManagedBy: 'Bicep'
}

// Key Vault
module keyVault 'modules/keyvault.bicep' = {
  name: 'keyVault'
  params: {
    name: '${resourcePrefix}-kv'
    location: location
    tags: tags
  }
}

// Storage Account
module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: replace('${resourcePrefix}stor', '-', '')
    location: location
    tags: tags
  }
}

// SQL Server and Database
module sql 'modules/sql.bicep' = {
  name: 'sql'
  params: {
    serverName: '${resourcePrefix}-sql'
    databaseName: '${baseName}db'
    location: location
    tags: tags
    adminLogin: sqlAdminLogin
    adminPassword: sqlAdminPassword
  }
}

// Application Insights
module appInsights 'modules/appinsights.bicep' = {
  name: 'appInsights'
  params: {
    name: '${resourcePrefix}-ai'
    location: location
    tags: tags
  }
}

// Function App (Pipeline)
module functionApp 'modules/functionapp.bicep' = {
  name: 'functionApp'
  params: {
    name: '${resourcePrefix}-func'
    location: location
    tags: tags
    storageAccountName: storage.outputs.name
    appInsightsInstrumentationKey: appInsights.outputs.instrumentationKey
    keyVaultName: keyVault.outputs.name
  }
}

// Container App (Dashboard)
module containerApp 'modules/containerapp.bicep' = {
  name: 'containerApp'
  params: {
    name: '${resourcePrefix}-app'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
  }
}

// Outputs
output keyVaultName string = keyVault.outputs.name
output keyVaultUri string = keyVault.outputs.uri
output storageAccountName string = storage.outputs.name
output sqlServerFqdn string = sql.outputs.serverFqdn
output sqlDatabaseName string = sql.outputs.databaseName
output functionAppName string = functionApp.outputs.name
output functionAppUrl string = functionApp.outputs.url
output containerAppName string = containerApp.outputs.name
output containerAppUrl string = containerApp.outputs.url
output appInsightsInstrumentationKey string = appInsights.outputs.instrumentationKey
