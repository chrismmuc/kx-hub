# Remote MCP Server Deployment Guide

**Date:** 2025-12-20
**Target:** Google Cloud Run
**Branch:** silly-haibt

## Prerequisites

- [x] GCP project with billing enabled
- [x] Terraform installed (>= 1.0)
- [x] Docker installed
- [x] gcloud CLI configured
- [ ] Tavily API key (get from https://tavily.com)

## Deployment Steps

### Step 1: Build and Push Docker Image

```bash
# Set project ID
export PROJECT_ID=$(gcloud config get-value project)
export IMAGE_TAG="gcr.io/${PROJECT_ID}/kx-hub-mcp-remote:latest"

# Build for linux/amd64 platform
docker build -f Dockerfile.mcp-server -t "${IMAGE_TAG}" --platform linux/amd64 .

# Configure Docker for GCR
gcloud auth configure-docker

# Push image to Google Container Registry
docker push "${IMAGE_TAG}"
```

### Step 2: Configure Terraform Variables

```bash
cd terraform/mcp-remote

# Copy example configuration
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values:
# - project_id: Your GCP project ID
# - region: us-central1 (or your preferred region)
# - tavily_api_key: Your Tavily API key
# - alert_email: Your email for alerts (optional)
```

**Example terraform.tfvars:**
```hcl
project_id           = "kx-hub-prod"
region              = "us-central1"
firestore_collection = "kb_items"
service_name        = "kx-hub-mcp-remote"
tavily_api_key      = "tvly-YOUR-ACTUAL-API-KEY"
alert_email         = "your-email@example.com"
```

### Step 3: Deploy Infrastructure with Terraform

```bash
# Initialize Terraform
terraform init

# Review deployment plan
terraform plan

# Apply configuration (creates all infrastructure)
terraform apply
```

**What Terraform Creates:**
- ✅ Cloud Run service with MCP server
- ✅ Service account with least-privilege IAM
- ✅ Secret Manager secrets (auth token, Tavily key)
- ✅ Monitoring alerts and dashboards
- ✅ Log-based metrics

### Step 4: Get Service URL and Auth Token

```bash
# Get the deployed service URL
terraform output service_url

# Get the authentication token (store securely!)
terraform output -raw auth_token
```

**Output Example:**
```
service_url = "https://kx-hub-mcp-remote-abc123-uc.a.run.app"
auth_token = "your-secure-48-char-token-here"
```

### Step 5: Configure Claude Desktop

Add to your Claude Desktop MCP configuration:

**macOS/Linux:** `~/.config/claude/config.json`
**Windows:** `%APPDATA%\Claude\config.json`

```json
{
  "mcpServers": {
    "kx-hub": {
      "transport": {
        "type": "sse",
        "url": "https://kx-hub-mcp-remote-abc123-uc.a.run.app",
        "headers": {
          "Authorization": "Bearer your-secure-48-char-token-here"
        }
      }
    }
  }
}
```

### Step 6: Test the Deployment

```bash
# Test the endpoint with curl
curl -H "Authorization: Bearer YOUR_AUTH_TOKEN" \
  "https://kx-hub-mcp-remote-abc123-uc.a.run.app/health"

# Expected response: {"status": "healthy"}
```

## Post-Deployment

### View Logs

```bash
# View Cloud Run logs
gcloud run services logs read kx-hub-mcp-remote \
  --region=us-central1 \
  --limit=50
```

### Monitor Metrics

```bash
# View monitoring dashboard
terraform output monitoring_dashboard_url
```

### Update Deployment

When you make code changes:

```bash
# 1. Build and push new image
docker build -f Dockerfile.mcp-server -t "${IMAGE_TAG}" --platform linux/amd64 .
docker push "${IMAGE_TAG}"

# 2. Update Cloud Run (Terraform will detect image change)
cd terraform/mcp-remote
terraform apply
```

## Troubleshooting

### Issue: Docker build fails
**Solution:** Ensure you're building for linux/amd64 platform:
```bash
docker build -f Dockerfile.mcp-server -t "${IMAGE_TAG}" --platform linux/amd64 .
```

### Issue: Permission denied pushing to GCR
**Solution:** Configure Docker authentication:
```bash
gcloud auth configure-docker
```

### Issue: Terraform plan shows no changes after image update
**Solution:** Force Cloud Run to update:
```bash
terraform taint google_cloud_run_service.mcp_server
terraform apply
```

### Issue: 401 Unauthorized when testing
**Solution:** Verify auth token matches:
```bash
terraform output -raw auth_token
```

## Cost Estimate

- **Cloud Run:** ~$0.50-1.00/month (within free tier)
- **Secret Manager:** ~$0.06/month (2 secrets)
- **Monitoring:** Free tier
- **Container Registry:** ~$0.02/month
- **Total:** ~$1.00/month

## Security Notes

- ✅ Authentication required on all requests (Bearer token)
- ✅ Secrets stored in Secret Manager (not in code)
- ✅ Service account with minimal IAM permissions
- ✅ Read-only Firestore access (except recommendation tracking)
- ✅ No public write access

## Rollback

If you need to destroy the deployment:

```bash
cd terraform/mcp-remote
terraform destroy
```

**Warning:** This will delete the Cloud Run service and secrets!

## Next Steps

1. **Test the MCP server** in Claude Desktop
2. **Set up monitoring alerts** (already configured in Terraform)
3. **Review logs** for any errors
4. **Update documentation** with your service URL

---

**Deployment complete!** 🎉

Your remote MCP server is now accessible from any device with Claude Desktop.
