# OAuth 2.1 Setup Guide for Claude Mobile/Web Access

This guide explains how to enable OAuth 2.1 authentication for kx-hub MCP server, allowing access from Claude Mobile and Claude.ai Web.

## Overview

**Story 3.1.1** implements OAuth 2.1 with Dynamic Client Registration (RFC 7591) to enable kx-hub access from:
- ✅ Claude.ai Web (any browser)
- ✅ Claude Mobile (iPhone/Android)
- ✅ Claude Desktop (with OAuth or Bearer token)

## Architecture

```
Claude Mobile/Web → OAuth Flow → Cloud Run (kx-hub-mcp-remote)
                                      ├─ /register (DCR)
                                      ├─ /authorize (login/consent)
                                      ├─ /token (token exchange)
                                      └─ /sse (MCP protocol)
```

### Components

- **OAuth Server** (`oauth_server.py`) - RFC 7591 compliant endpoints
- **OAuth Storage** (`oauth_storage.py`) - Firestore client/token management
- **OAuth Middleware** (`oauth_middleware.py`) - JWT validation
- **OAuth Templates** (`oauth_templates.py`) - HTML login/consent UI
- **Terraform** (`terraform/mcp-remote/oauth.tf`) - JWT keys & Firestore indexes

## Prerequisites

- Google Cloud Project with billing enabled
- Terraform >= 1.0
- Docker installed
- gcloud CLI configured
- Claude Pro/Team/Enterprise plan (for Custom Connectors)

## Deployment

### Option 1: Automated Deployment (Recommended)

```bash
# Run deployment script
./scripts/deploy_oauth_mcp.sh
```

The script will:
1. Check requirements
2. Ask if you want OAuth enabled
3. Generate password hash
4. Build & push Docker image
5. Deploy infrastructure with Terraform
6. Output configuration instructions

### Option 2: Manual Deployment

#### Step 1: Configure Terraform Variables

```bash
cd terraform/mcp-remote
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
project_id  = "your-gcp-project-id"
region      = "europe-west4"
oauth_enabled = true
oauth_user_email = "your-email@example.com"

# Generate with: python3 -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"
oauth_user_password_hash = "$2b$12$..."
```

#### Step 2: Generate Password Hash

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'YourSecurePassword', bcrypt.gensalt()).decode())"
```

Copy the output to `oauth_user_password_hash` in terraform.tfvars.

#### Step 3: Build Docker Image

```bash
export PROJECT_ID=$(gcloud config get-value project)
export IMAGE_TAG="gcr.io/${PROJECT_ID}/kx-hub-mcp-remote:latest"

docker build -f Dockerfile.mcp-server -t "${IMAGE_TAG}" --platform linux/amd64 .
gcloud auth configure-docker
docker push "${IMAGE_TAG}"
```

#### Step 4: Deploy with Terraform

```bash
cd terraform/mcp-remote
terraform init
terraform plan
terraform apply
```

Note the `service_url` output - you'll need it for Claude configuration.

## Configure Claude.ai Web/Mobile

### Step 1: Open Settings

1. Go to [https://claude.ai/settings](https://claude.ai/settings)
2. Navigate to **Connectors** (or **Integrations**)
3. Click **"Add custom connector"** or **"Add MCP Server"**

### Step 2: Enter Configuration

**IMPORTANT:** Leave OAuth fields EMPTY - Claude will auto-configure via Dynamic Client Registration!

- **Name**: `kx-hub`
- **Remote MCP Server URL**: `https://kx-hub-mcp-remote-xxx.run.app` (from terraform output)
- **OAuth Client ID**: *(leave empty)*
- **OAuth Client Secret**: *(leave empty)*

### Step 3: Authorize

1. Click **"Add"** or **"Connect"**
2. Claude.ai will redirect to your authorization page
3. Enter your password (the one you used to generate the hash)
4. Review permissions and click **"Authorize"**
5. You should see a **success page** with a countdown timer
6. **Auto-redirect** back to Claude.ai after 3 seconds
   - If auto-redirect doesn't work, click the **"Return to Claude"** button
7. Status should change to **"Connected"** ✅

### Verification

Test the connection:
- In a new Claude conversation, type: **"Get my knowledge base statistics"**
- Claude should use the `get_stats` tool from kx-hub
- You should see a response with chunk count, cluster count, etc.

**Success!** kx-hub is now accessible from Claude Web, Mobile, and Desktop! 🎉

## Testing

### Test OAuth Endpoints

```bash
# Get service URL
SERVICE_URL=$(cd terraform/mcp-remote && terraform output -raw service_url)

# Test discovery endpoint
curl $SERVICE_URL/.well-known/oauth-authorization-server | jq

# Expected output:
{
  "issuer": "https://kx-hub-mcp-remote-xxx.run.app",
  "authorization_endpoint": "https://kx-hub-mcp-remote-xxx.run.app/authorize",
  "token_endpoint": "https://kx-hub-mcp-remote-xxx.run.app/token",
  "registration_endpoint": "https://kx-hub-mcp-remote-xxx.run.app/register",
  ...
}
```

### Test in Claude Mobile

1. Open Claude app on your phone
2. Start a new conversation
3. Type: "Get knowledge base statistics"
4. Claude should use kx-hub tools to retrieve stats

### Test in Claude.ai Web

1. Go to [claude.ai](https://claude.ai)
2. Start a new conversation
3. Type: "Search my knowledge base for 'platform engineering'"
4. Claude should use kx-hub search_kb tool

## Troubleshooting

### Issue: "Connector not connected" in Claude.ai

**Symptom:** After OAuth flow completes, Claude.ai shows "nicht verbunden" (not connected)

**Possible Causes:**

1. **`.well-known` endpoints not reachable**
   - **Test:** `curl https://your-server/.well-known/oauth-protected-resource`
   - **Expected:** 200 OK with OAuth metadata
   - **Fix:** Ensure `oauth_enabled=true` in terraform.tfvars and service is deployed

2. **Incorrect Redirect URI**
   - Claude.ai callback URL **MUST** be `https://claude.ai/api/mcp/auth_callback`
   - **Check:** Firestore → `oauth_clients` collection → `redirect_uris` field
   - **Fix:** Delete invalid clients in Firestore, let Claude re-register automatically

3. **HTTP instead of HTTPS Issuer**
   - **Test:** `curl https://your-server/.well-known/oauth-authorization-server | jq .issuer`
   - **Expected:** `https://` URL (not `http://`)
   - **Fix:** Set `oauth_issuer_override` in terraform.tfvars after first deployment:
     ```bash
     # Get your service URL
     cd terraform/mcp-remote
     terraform output service_url

     # Add to terraform.tfvars
     oauth_issuer_override = "https://kx-hub-mcp-remote-xxxxxx.run.app"

     # Redeploy
     terraform apply
     ```

4. **CORS blocking preflight requests**
   - **Check:** Browser DevTools → Network tab → Look for OPTIONS requests
   - **Expected:** `Access-Control-Allow-Origin: https://claude.ai` header present
   - **Fix:** This should be automatic with the OAuth fix. Check Cloud Run logs for errors.

5. **Token validation fails**
   - **Check Cloud Run logs:**
     ```bash
     gcloud run services logs read kx-hub-mcp-remote --region=europe-west4 --limit=50
     ```
   - **Look for:** "Invalid JWT token" or "Token validation failed" errors
   - **Fix:** Verify OAUTH_ISSUER matches the issuer in JWT tokens

### Issue: Success page doesn't redirect

**Symptom:** After clicking "Authorize", stuck on success page

**Cause:** JavaScript auto-redirect might be blocked

**Fix:** Click "Return to Claude" button manually (should appear on success page)

### Issue: "Invalid redirect_uri" error

**Symptom:** Authorization fails with "redirect_uri is not registered"

**Cause:** Redirect URI mismatch between registration and authorization request

**Fix:**
1. Delete existing client in Firestore: `oauth_clients/<client_id>`
2. Clear browser cache and cookies for claude.ai
3. Let Claude.ai re-register with correct redirect_uri

### Issue: "Invalid client" error

**Cause**: Client registration failed
**Solution**: Check terraform logs, ensure oauth_enabled=true

### Issue: "Invalid password" on login

**Cause**: Password hash doesn't match
**Solution**: Regenerate hash and update terraform:

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'YourPassword', bcrypt.gensalt()).decode())"
# Update terraform.tfvars
terraform apply
```

### Issue: "Token expired" errors

**Cause**: Access token expired (1 hour expiry)
**Solution**: Claude automatically refreshes tokens. If it fails, re-authorize in Settings.

### Issue: Server not accessible

**Cause**: Cloud Run service not deployed or IAM issues
**Solution**: Check Cloud Run logs:

```bash
gcloud run services logs read kx-hub-mcp-remote --region=europe-west4 --limit=50
```

### Debugging Tips

**View OAuth flow in browser:**
1. Open browser DevTools (F12)
2. Go to Network tab
3. Add connector in Claude.ai
4. Watch requests to:
   - `/.well-known/oauth-authorization-server` (discovery)
   - `/register` (client registration)
   - `/authorize` (user login/consent)
   - `/token` (token exchange)
5. Check for any 4xx or 5xx errors

**Check Firestore data:**
```bash
# List registered clients
gcloud firestore documents list oauth_clients --project=your-project-id

# View specific client
gcloud firestore documents describe oauth_clients/CLIENT_ID --project=your-project-id
```

**Verify HTTPS issuer:**
```bash
SERVICE_URL=$(cd terraform/mcp-remote && terraform output -raw service_url)
curl $SERVICE_URL/.well-known/oauth-authorization-server | jq .issuer

# Should output: "https://kx-hub-mcp-remote-xxx.run.app" (NOT http://)
```

## Security Considerations

- ✅ JWT tokens signed with RSA-256 (asymmetric)
- ✅ Client secrets hashed with bcrypt
- ✅ Refresh tokens rotate on each use (one-time)
- ✅ Authorization codes expire after 10 minutes
- ✅ Access tokens expire after 1 hour
- ✅ HTTPS enforced by Cloud Run
- ✅ Secret Manager for sensitive keys
- ✅ Single-user system (only you can authorize)

## Cost Estimate

With OAuth enabled:

- Cloud Run: ~$0.50-1.00/month (free tier)
- Secret Manager: ~$0.12/month (4 secrets)
- Firestore: ~$0.05/month (minimal reads/writes)
- **Total**: ~$0.70/month

## Disable OAuth

To switch back to simple Bearer token auth:

```bash
cd terraform/mcp-remote
# Edit terraform.tfvars
oauth_enabled = false

terraform apply
```

This removes OAuth endpoints and uses MCP_AUTH_TOKEN instead.

## Architecture Details

### OAuth Flow

1. **Client Registration** (automatic via DCR):
   - Claude.ai POSTs to `/register`
   - Server generates `client_id` and `client_secret`
   - Credentials stored in Firestore

2. **Authorization**:
   - User clicks "Add" in Claude settings
   - Redirect to `/authorize` with client_id
   - User enters password
   - Server creates authorization code
   - Redirect back to Claude with code

3. **Token Exchange**:
   - Claude POSTs code to `/token`
   - Server validates code
   - Issues JWT access token (1 hour)
   - Issues refresh token (30 days)

4. **API Requests**:
   - Claude includes `Authorization: Bearer <jwt>` header
   - Middleware validates JWT signature
   - Request proceeds to MCP endpoints

### Data Model

**Firestore Collections:**

- `oauth_clients`: Registered OAuth clients
  - `client_id`, `client_secret_hash`, `redirect_uris`, etc.

- `oauth_tokens`: Authorization codes & refresh tokens
  - `code_xxx`: Authorization codes (10 min TTL)
  - `refresh_xxx`: Refresh tokens (30 day TTL)

**Secret Manager:**

- `oauth-jwt-private-key`: RSA private key for JWT signing
- `oauth-jwt-public-key`: RSA public key for JWT validation

## References

- [RFC 7591: OAuth 2.0 Dynamic Client Registration](https://datatracker.ietf.org/doc/html/rfc7591)
- [RFC 6749: OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749)
- [Claude Custom Connectors Documentation](https://support.claude.com/en/articles/11503834)
- [MCP Protocol Specification](https://modelcontextprotocol.io)

## Next Steps

- [x] Deploy OAuth-enabled MCP server
- [x] Configure Claude.ai Web
- [ ] Test on Claude Mobile
- [ ] Monitor OAuth token usage
- [ ] Set up alerts for failed authentications

---

**Deployed successfully?** You should now have kx-hub accessible from Claude Mobile, Web, and Desktop! 🎉
