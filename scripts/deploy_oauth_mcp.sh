#!/usr/bin/env bash
#
# Deploy kx-hub MCP Server with OAuth 2.1 support to Cloud Run
#
# This script:
# 1. Generates a password hash for OAuth login
# 2. Builds and pushes Docker image
# 3. Deploys infrastructure with Terraform
# 4. Outputs configuration for Claude.ai

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check required tools
check_requirements() {
    log_info "Checking requirements..."

    local missing=()

    if ! command -v gcloud &> /dev/null; then
        missing+=("gcloud (Google Cloud SDK)")
    fi

    if ! command -v docker &> /dev/null; then
        missing+=("docker")
    fi

    if ! command -v terraform &> /dev/null; then
        missing+=("terraform")
    fi

    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required tools:"
        for tool in "${missing[@]}"; do
            echo "  - $tool"
        done
        exit 1
    fi

    log_success "All requirements met"
}

# Generate password hash
generate_password_hash() {
    log_info "Generating OAuth password hash..."

    echo ""
    echo "Enter a secure password for OAuth login:"
    read -s password
    echo ""
    echo "Confirm password:"
    read -s password_confirm
    echo ""

    if [ "$password" != "$password_confirm" ]; then
        log_error "Passwords don't match!"
        exit 1
    fi

    # Generate bcrypt hash
    hash=$(python3 -c "import bcrypt; print(bcrypt.hashpw(b'$password', bcrypt.gensalt()).decode())")

    log_success "Password hash generated"
    echo "$hash"
}

# Main deployment function
main() {
    echo ""
    echo "======================================"
    echo "  kx-hub OAuth MCP Server Deployment"
    echo "======================================"
    echo ""

    check_requirements

    # Change to terraform directory
    cd "$(dirname "$0")/../terraform/mcp-remote"

    # Check if terraform.tfvars exists
    if [ ! -f terraform.tfvars ]; then
        log_warning "terraform.tfvars not found"
        log_info "Copying terraform.tfvars.example to terraform.tfvars"
        cp terraform.tfvars.example terraform.tfvars
        log_warning "Please edit terraform.tfvars with your configuration"
        log_warning "Then run this script again"
        exit 1
    fi

    # Ask if user wants to enable OAuth
    echo ""
    echo "Do you want to enable OAuth 2.1 for Claude Mobile/Web? (y/n)"
    read -r enable_oauth

    if [[ "$enable_oauth" == "y" || "$enable_oauth" == "Y" ]]; then
        log_info "OAuth 2.1 will be enabled"

        # Get user email
        echo ""
        echo "Enter your email for OAuth:"
        read -r user_email

        # Generate password hash
        password_hash=$(generate_password_hash)

        # Update terraform.tfvars
        log_info "Updating terraform.tfvars..."
        sed -i.bak "s/^oauth_enabled = .*/oauth_enabled = true/" terraform.tfvars
        sed -i.bak "s/^oauth_user_email = .*/oauth_user_email = \"$user_email\"/" terraform.tfvars
        sed -i.bak "s|^oauth_user_password_hash = .*|oauth_user_password_hash = \"$password_hash\"|" terraform.tfvars

        log_success "terraform.tfvars updated with OAuth configuration"
    else
        log_info "OAuth disabled - using simple Bearer token auth"
        sed -i.bak "s/^oauth_enabled = .*/oauth_enabled = false/" terraform.tfvars
    fi

    # Get GCP project ID from terraform.tfvars
    project_id=$(grep "^project_id" terraform.tfvars | cut -d'=' -f2 | tr -d ' "')

    log_info "Using GCP project: $project_id"

    # Build Docker image
    echo ""
    log_info "Building Docker image..."

    cd ../..
    export IMAGE_TAG="gcr.io/${project_id}/kx-hub-mcp-remote:latest"

    docker build -f Dockerfile.mcp-server -t "${IMAGE_TAG}" --platform linux/amd64 .

    log_success "Docker image built"

    # Push to GCR
    log_info "Pushing image to Google Container Registry..."

    gcloud auth configure-docker
    docker push "${IMAGE_TAG}"

    log_success "Image pushed to GCR"

    # Deploy with Terraform
    echo ""
    log_info "Deploying infrastructure with Terraform..."

    cd terraform/mcp-remote

    terraform init
    terraform plan
    terraform apply

    log_success "Deployment complete!"

    # Show outputs
    echo ""
    echo "======================================"
    echo "  Deployment Summary"
    echo "======================================"
    echo ""

    service_url=$(terraform output -raw service_url)

    echo "Service URL: $service_url"
    echo ""

    if [[ "$enable_oauth" == "y" || "$enable_oauth" == "Y" ]]; then
        echo "OAuth Configuration:"
        echo "  - Authorization URL: $service_url/authorize"
        echo "  - Token URL: $service_url/token"
        echo "  - Registration URL: $service_url/register"
        echo "  - Discovery URL: $service_url/.well-known/oauth-authorization-server"
        echo ""
        echo "To add to Claude.ai:"
        echo "  1. Go to https://claude.ai/settings"
        echo "  2. Navigate to Connectors"
        echo "  3. Click 'Add custom connector'"
        echo "  4. Enter:"
        echo "     - Name: kx-hub"
        echo "     - Remote MCP Server URL: $service_url"
        echo "  5. Leave OAuth Client ID/Secret empty (DCR auto-configures)"
        echo "  6. Click 'Add' and authorize"
    else
        auth_token=$(terraform output -raw auth_token)
        echo "Bearer Token Auth (Desktop only):"
        echo "  - Auth Token: $auth_token"
        echo ""
        echo "To add to Claude Desktop:"
        echo "  Add to claude_desktop_config.json:"
        echo "  {"
        echo "    \"mcpServers\": {"
        echo "      \"kx-hub\": {"
        echo "        \"transport\": {"
        echo "          \"type\": \"sse\","
        echo "          \"url\": \"$service_url\","
        echo "          \"headers\": {"
        echo "            \"Authorization\": \"Bearer $auth_token\""
        echo "          }"
        echo "        }"
        echo "      }"
        echo "    }"
        echo "  }"
    fi

    echo ""
    log_success "Deployment successful! 🎉"
}

# Run main function
main "$@"
