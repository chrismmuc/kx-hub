#!/bin/bash

# Deployment script for Hybrid MCP Architecture
# Deploys Python Tools API and TypeScript MCP Server to Cloud Run

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Hybrid MCP Deployment ===${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI not found. Please install it first.${NC}"
    exit 1
fi

# Get current project
PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No GCP project set. Run 'gcloud config set project PROJECT_ID'${NC}"
    exit 1
fi

echo -e "${GREEN}Project: $PROJECT_ID${NC}"
echo ""

# Step 1: Deploy Python Tools API
echo -e "${BLUE}Step 1: Deploying Python Tools API...${NC}"
gcloud builds submit --config cloudbuild.mcp-tools-api.yaml

# Get the Python Tools API URL
PYTHON_API_URL=$(gcloud run services describe kx-hub-tools-api \
    --region=europe-west1 \
    --format='value(status.url)')

if [ -z "$PYTHON_API_URL" ]; then
    echo -e "${RED}Error: Failed to get Python Tools API URL${NC}"
    exit 1
fi

echo -e "${GREEN}Python Tools API deployed: $PYTHON_API_URL${NC}"
echo ""

# Step 2: Get OAuth Lambda URL from user
echo -e "${BLUE}Step 2: OAuth Configuration${NC}"
read -p "Enter your OAuth Lambda URL (from terraform/mcp-remote/terraform.tfstate): " OAUTH_LAMBDA_URL

if [ -z "$OAUTH_LAMBDA_URL" ]; then
    echo -e "${RED}Error: OAuth Lambda URL is required${NC}"
    exit 1
fi

# Step 3: Get JWT Secret
echo -e "${BLUE}Step 3: JWT Configuration${NC}"
read -sp "Enter your JWT Secret (same as used in OAuth Lambda): " JWT_SECRET
echo ""

if [ -z "$JWT_SECRET" ]; then
    echo -e "${RED}Error: JWT Secret is required${NC}"
    exit 1
fi

# Step 4: Deploy TypeScript MCP Server
echo -e "${BLUE}Step 4: Deploying TypeScript MCP Server...${NC}"

# Update cloudbuild.mcp-server-ts.yaml with actual values
sed -i.bak "s|_PYTHON_TOOLS_API_URL:.*|_PYTHON_TOOLS_API_URL: $PYTHON_API_URL|" cloudbuild.mcp-server-ts.yaml
sed -i.bak "s|_OAUTH_LAMBDA_URL:.*|_OAUTH_LAMBDA_URL: $OAUTH_LAMBDA_URL|" cloudbuild.mcp-server-ts.yaml
sed -i.bak "s|_JWT_SECRET:.*|_JWT_SECRET: $JWT_SECRET|" cloudbuild.mcp-server-ts.yaml

gcloud builds submit --config cloudbuild.mcp-server-ts.yaml

# Restore original cloudbuild file
mv cloudbuild.mcp-server-ts.yaml.bak cloudbuild.mcp-server-ts.yaml

# Get the MCP Server URL
MCP_SERVER_URL=$(gcloud run services describe kx-hub-mcp-server \
    --region=europe-west1 \
    --format='value(status.url)')

if [ -z "$MCP_SERVER_URL" ]; then
    echo -e "${RED}Error: Failed to get MCP Server URL${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}=== Deployment Complete! ===${NC}"
echo ""
echo -e "Python Tools API: ${BLUE}$PYTHON_API_URL${NC}"
echo -e "MCP Server:       ${BLUE}$MCP_SERVER_URL${NC}"
echo -e "OAuth Lambda:     ${BLUE}$OAUTH_LAMBDA_URL${NC}"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo "1. Test Python Tools API: curl $PYTHON_API_URL/health"
echo "2. Test MCP Server: curl $MCP_SERVER_URL/health"
echo "3. Configure Claude.ai with MCP Server URL: $MCP_SERVER_URL"
echo ""
