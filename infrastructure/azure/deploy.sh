#!/bin/bash
# ATLAS V1 - Azure Deployment Script

set -e

# Configuration
RESOURCE_GROUP="${ATLAS_RESOURCE_GROUP:-atlas-rg}"
LOCATION="${ATLAS_LOCATION:-eastus}"
ENVIRONMENT="${ATLAS_ENV:-dev}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}ATLAS V1 - Azure Deployment${NC}"
echo "=============================="
echo ""

# Check for required tools
if ! command -v az &> /dev/null; then
    echo -e "${RED}Error: Azure CLI not found. Please install it first.${NC}"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Not logged in to Azure. Running 'az login'...${NC}"
    az login
fi

# Show current subscription
SUBSCRIPTION=$(az account show --query name -o tsv)
echo "Using subscription: $SUBSCRIPTION"
echo ""

# Prompt for SQL credentials if not set
if [ -z "$SQL_ADMIN_LOGIN" ]; then
    read -p "SQL Admin Login: " SQL_ADMIN_LOGIN
fi

if [ -z "$SQL_ADMIN_PASSWORD" ]; then
    read -s -p "SQL Admin Password: " SQL_ADMIN_PASSWORD
    echo ""
fi

# Create resource group if it doesn't exist
echo -e "${YELLOW}Creating resource group: $RESOURCE_GROUP${NC}"
az group create --name $RESOURCE_GROUP --location $LOCATION --output none

# Deploy infrastructure
echo -e "${YELLOW}Deploying infrastructure...${NC}"
az deployment group create \
    --resource-group $RESOURCE_GROUP \
    --template-file main.bicep \
    --parameters \
        environment=$ENVIRONMENT \
        location=$LOCATION \
        sqlAdminLogin=$SQL_ADMIN_LOGIN \
        sqlAdminPassword=$SQL_ADMIN_PASSWORD \
    --output table

# Get outputs
echo ""
echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "Key outputs:"
az deployment group show \
    --resource-group $RESOURCE_GROUP \
    --name main \
    --query properties.outputs \
    --output table

echo ""
echo "Next steps:"
echo "1. Add secrets to Key Vault:"
echo "   - tiingo-api-key"
echo "   - fred-api-key"
echo "   - atlas-db-connection"
echo "   - atlas-dashboard-users"
echo ""
echo "2. Deploy the application code"
echo ""
echo "3. Run initial database migration:"
echo "   atlas init-db"
