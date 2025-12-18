# MCP Remote Server Deployment Configuration

## Overview

This document defines the deployment configuration for the remote MCP server on Google Cloud Run.

## Environment Variables

### Required Environment Variables

| Variable | Description | Example | Source |
|----------|-------------|---------|--------|
| `TRANSPORT_MODE` | Server transport mode (stdio or sse) | `sse` | Environment |
| `GCP_PROJECT` | Google Cloud Project ID | `kx-hub-prod` | Environment |
| `GCP_REGION` | Google Cloud Region | `us-central1` | Environment |
| `FIRESTORE_COLLECTION` | Firestore collection name | `kb_items` | Environment |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account key (local only) | `/path/to/key.json` | Local only |

### Secret Manager Secrets

| Secret Name | Description | Access Required |
|-------------|-------------|-----------------|
| `MCP_AUTH_TOKEN` | Bearer token for authentication | Service account must have secretAccessor role |
| `TAVILY_API_KEY` | Tavily Search API key | Service account must have secretAccessor role |

## Cloud Run Configuration

### Service Specification

```yaml
Service Name: kx-hub-mcp-remote
Region: us-central1
Platform: managed

Resources:
  Memory: 1GB
  CPU: 1
  Timeout: 120 seconds

Scaling:
  Min Instances: 0  # Scale to zero when not in use
  Max Instances: 3  # Limit for cost control
  Concurrency: 10   # Max concurrent requests per instance

Networking:
  Ingress: all      # Public access (auth via Bearer token)

Authentication:
  Allow Unauthenticated: yes  # Auth handled by Bearer token in app
```

### Environment Variables (Deployment)

```bash
TRANSPORT_MODE=sse
GCP_PROJECT=kx-hub-prod
GCP_REGION=us-central1
FIRESTORE_COLLECTION=kb_items
```

### Secret Injection

```bash
# Secrets mounted as environment variables
MCP_AUTH_TOKEN (from secret: MCP_AUTH_TOKEN:latest)
TAVILY_API_KEY (from secret: TAVILY_API_KEY:latest)
```

## Authentication Scheme

### Bearer Token Authentication

- **Header**: `Authorization: Bearer <MCP_AUTH_TOKEN>`
- **Token**: 32-byte random token stored in Secret Manager
- **Enforcement**: Middleware validates on all requests
- **Response**: 401 Unauthorized for missing/invalid tokens

### Token Generation

```bash
# Generate secure random token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Service Account

### Service Account Email

```
mcp-server-remote@kx-hub-prod.iam.gserviceaccount.com
```

### Required IAM Roles

1. **Firestore Access**:
   - `roles/datastore.viewer` (read-only for kb_items, clusters, config)
   - Custom role for write to `config/recommendation_shown`

2. **Secret Manager**:
   - `roles/secretmanager.secretAccessor` for:
     - `MCP_AUTH_TOKEN`
     - `TAVILY_API_KEY`

3. **Vertex AI**:
   - `roles/aiplatform.user` (for embeddings and Gemini models)

## Deployment via Terraform

**IMPORTANT**: All deployment MUST be done via Terraform. **NEVER use gcloud commands** for deployment.

### Deployment Steps

1. **Configure Terraform variables**:
   ```bash
   cd terraform/mcp-remote
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your values
   ```

2. **Build and push Docker image**:
   ```bash
   export PROJECT_ID=$(gcloud config get-value project)
   export IMAGE_TAG="gcr.io/${PROJECT_ID}/kx-hub-mcp-remote:latest"

   docker build -f Dockerfile.mcp-server -t "${IMAGE_TAG}" --platform linux/amd64 .
   gcloud auth configure-docker
   docker push "${IMAGE_TAG}"
   ```

3. **Deploy infrastructure**:
   ```bash
   cd terraform/mcp-remote
   terraform init
   terraform plan
   terraform apply
   ```

4. **Get service URL and auth token**:
   ```bash
   terraform output service_url
   terraform output -raw auth_token
   ```

See [docs/mcp-remote.md](../mcp-remote.md) for complete deployment guide.

## Endpoint URL Format

```
https://kx-hub-mcp-remote-<hash>-uc.a.run.app
```

The actual URL will be provided after deployment.

## Cost Estimate

- **Cloud Run**: $0.50-1.00/month (within free tier)
- **Tavily API**: Free tier (1000 queries/month)
- **Vertex AI**: Existing usage (no incremental cost)
- **Total**: <$1.50/month
