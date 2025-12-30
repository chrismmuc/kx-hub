#!/bin/bash
# Remote MCP Server Deployment Script
# This script automates the deployment of the MCP remote server to Google Cloud Run

set -e  # Exit on error

echo "========================================="
echo "Remote MCP Server Deployment"
echo "========================================="
echo ""

# Step 1: Verify prerequisites
echo "Step 1: Verifying prerequisites..."
command -v gcloud >/dev/null 2>&1 || { echo "ERROR: gcloud CLI is required but not installed."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker is required but not installed."; exit 1; }
command -v terraform >/dev/null 2>&1 || { echo "ERROR: Terraform is required but not installed."; exit 1; }
echo "✅ All prerequisites installed"
echo ""

# Step 2: Get GCP project ID
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo "ERROR: No GCP project configured. Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi
echo "Using GCP Project: $PROJECT_ID"
echo ""

# Step 3: Build Docker image
echo "Step 2: Building Docker image..."
export IMAGE_TAG="gcr.io/${PROJECT_ID}/kx-hub-mcp-remote:latest"
echo "Image tag: $IMAGE_TAG"

docker build -f Dockerfile.mcp-server -t "${IMAGE_TAG}" --platform linux/amd64 .
echo "✅ Docker image built successfully"
echo ""

# Step 4: Configure Docker for GCR
echo "Step 3: Configuring Docker authentication..."
gcloud auth configure-docker --quiet
echo "✅ Docker configured for GCR"
echo ""

# Step 5: Push Docker image
echo "Step 4: Pushing Docker image to GCR..."
docker push "${IMAGE_TAG}"
echo "✅ Docker image pushed successfully"
echo ""

# Step 6: Check Terraform configuration
echo "Step 5: Checking Terraform configuration..."
cd terraform/mcp-remote

if [ ! -f "terraform.tfvars" ]; then
    echo "⚠️  WARNING: terraform.tfvars not found!"
    echo "Please create terraform.tfvars from terraform.tfvars.example"
    echo ""
    echo "Required variables:"
    echo "  - project_id: $PROJECT_ID"
    echo "  - tavily_api_key: YOUR_TAVILY_API_KEY"
    echo "  - alert_email: YOUR_EMAIL (optional)"
    echo ""
    read -p "Press Enter to continue once terraform.tfvars is created, or Ctrl+C to exit..."
fi
echo "✅ Terraform configuration ready"
echo ""

# Step 7: Initialize Terraform
echo "Step 6: Initializing Terraform..."
terraform init
echo "✅ Terraform initialized"
echo ""

# Step 8: Terraform plan
echo "Step 7: Running Terraform plan..."
terraform plan -out=tfplan
echo ""
echo "========================================="
echo "Review the plan above carefully!"
echo "========================================="
echo ""
read -p "Do you want to apply this plan? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Deployment cancelled."
    rm -f tfplan
    exit 0
fi

# Step 9: Apply Terraform
echo ""
echo "Step 8: Applying Terraform configuration..."
terraform apply tfplan
rm -f tfplan
echo "✅ Infrastructure deployed successfully"
echo ""

# Step 10: Get outputs
echo "========================================="
echo "Deployment Complete!"
echo "========================================="
echo ""
echo "Service URL:"
terraform output service_url
echo ""
echo "Auth Token (save this securely!):"
terraform output -raw auth_token
echo ""
echo ""
echo "Next steps:"
echo "1. Add the service URL and auth token to your Claude Desktop config"
echo "2. Restart Claude Desktop"
echo "3. Test the connection"
echo ""
echo "For detailed instructions, see: docs/mcp-remote.md"
echo ""
