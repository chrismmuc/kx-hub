# MCP Remote Server Deployment

Deploy the kx-hub MCP server to Google Cloud Run for remote access.

## Cost Estimate

**~$0.21/month** for typical usage (50 requests/month)

Breakdown:
- Cloud Run: $0.08/month
- Secret Manager: $0.12/month
- Container Registry: $0.01/month
- Other services: Free tier

Max cost if usage increases to 1000 requests/month: **~$1.73/month**

## Prerequisites

1. Google Cloud SDK (`gcloud`) authenticated
2. Docker installed
3. Terraform installed
4. Tavily API key (get from https://tavily.com)

## Deployment Steps

### 1. Configure Terraform Variables

```bash
cd terraform/mcp-remote
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 2. Build and Push Docker Image

```bash
# From project root
export PROJECT_ID=$(gcloud config get-value project)
export IMAGE_TAG="gcr.io/${PROJECT_ID}/kx-hub-mcp-remote:latest"

# Build image
docker build \
  -f Dockerfile.mcp-server \
  -t "${IMAGE_TAG}" \
  --platform linux/amd64 \
  .

# Configure Docker for GCR
gcloud auth configure-docker

# Push image
docker push "${IMAGE_TAG}"
```

### 3. Deploy Infrastructure

```bash
cd terraform/mcp-remote

# Initialize Terraform
terraform init

# Review plan
terraform plan

# Apply (creates all resources)
terraform apply
```

### 4. Get Credentials

```bash
# Get service URL
terraform output service_url

# Get auth token (keep secret!)
terraform output -raw auth_token
```

## Security

- **Authentication**: Bearer token required on all requests
- **Service Account**: Least-privilege (read-only except recommendation tracking)
- **Secrets**: Stored in Secret Manager, never in code
- **Network**: Public HTTPS endpoint, auth enforced by application
- **Monitoring**: Alerts on 5xx errors and auth failures

## Local Testing

You can still run the MCP server locally:

```bash
# Use default stdio mode (local)
python -m src.mcp_server.main

# Or explicitly set stdio mode
TRANSPORT_MODE=stdio python -m src.mcp_server.main
```

## Updating the Deployment

After code changes:

```bash
# 1. Rebuild and push image
docker build -f Dockerfile.mcp-server -t "${IMAGE_TAG}" .
docker push "${IMAGE_TAG}"

# 2. Trigger redeployment (Cloud Run will pull new image)
cd terraform/mcp-remote
terraform apply -var="force_redeploy=$(date +%s)"
```

## Cleanup

To destroy all resources:

```bash
cd terraform/mcp-remote
terraform destroy
```

**Warning**: This will delete:
- Cloud Run service
- Service account
- Secrets (including auth token)
- Monitoring alerts

## Troubleshooting

### Check Logs
```bash
gcloud run services logs read kx-hub-mcp-remote --region=us-central1
```

### Test Health Endpoint
```bash
SERVICE_URL=$(cd terraform/mcp-remote && terraform output -raw service_url)
curl ${SERVICE_URL}/health
# Should return: {"status":"healthy"}
```

### Test Authentication
```bash
AUTH_TOKEN=$(cd terraform/mcp-remote && terraform output -raw auth_token)
curl -H "Authorization: Bearer ${AUTH_TOKEN}" ${SERVICE_URL}/sse
```

## Monitoring

View dashboard:
```bash
# Get project ID
PROJECT_ID=$(gcloud config get-value project)

# Open dashboard
echo "https://console.cloud.google.com/monitoring/dashboards?project=${PROJECT_ID}"
```
