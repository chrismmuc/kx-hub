# OAuth 2.1 Setup Guide for Claude Mobile/Web Access

This guide explains how to enable OAuth 2.1 authentication for kx-hub MCP server, allowing access from Claude Mobile and Claude.ai Web.

## Overview

The kx-hub remote MCP server implements OAuth 2.1 with Dynamic Client Registration (RFC 7591) to enable access from:
- Claude.ai Web (any browser)
- Claude Mobile (iPhone/Android)
- Claude Code (via remote MCP)

## Architecture

```
Claude Mobile/Web → OAuth Flow → Cloud Run (kx-hub-mcp)
                                      ├─ /.well-known/* (discovery)
                                      ├─ /register (DCR)
                                      ├─ /authorize (login/consent)
                                      ├─ /token (token exchange)
                                      └─ POST / (MCP Streamable HTTP)
```

### Components

All components are in a single consolidated Python service:

- **server.py** - FastAPI server with OAuth + MCP endpoints
- **oauth_server.py** - RFC 7591 compliant OAuth implementation
- **oauth_storage.py** - Firestore client/token management
- **oauth_templates.py** - HTML login/consent UI
- **tools.py** - MCP tool implementations

## Prerequisites

- Google Cloud Project with billing enabled
- gcloud CLI configured
- Claude Pro/Team/Enterprise plan (for Custom Connectors)

## Deployment

### Deploy with Cloud Build

```bash
gcloud builds submit --config cloudbuild.mcp-consolidated.yaml --project=kx-hub
```

Or deploy directly:

```bash
gcloud run deploy kx-hub-mcp \
  --image=europe-west1-docker.pkg.dev/kx-hub/kx-hub/mcp-consolidated:latest \
  --region=europe-west1 \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT=kx-hub,FIRESTORE_DATABASE=kx-hub,OAUTH_ISSUER=https://kx-hub-mcp-386230044357.europe-west1.run.app,OAUTH_USER_EMAIL=your-email@example.com,OAUTH_USER_PASSWORD_HASH=\$2b\$12\$..." \
  --set-secrets="TAVILY_API_KEY=TAVILY_API_KEY:latest" \
  --project=kx-hub
```

### Generate Password Hash

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'YourSecurePassword', bcrypt.gensalt()).decode())"
```

## Configure Claude.ai Web/Mobile

### Step 1: Open Settings

1. Go to [https://claude.ai/settings](https://claude.ai/settings)
2. Navigate to **Connectors** (or **Integrations**)
3. Click **"Add custom connector"** or **"Add MCP Server"**

### Step 2: Enter Configuration

**IMPORTANT:** Leave OAuth fields EMPTY - Claude will auto-configure via Dynamic Client Registration!

- **Name**: `kx-hub`
- **Remote MCP Server URL**: `https://kx-hub-mcp-386230044357.europe-west1.run.app`
- **OAuth Client ID**: *(leave empty)*
- **OAuth Client Secret**: *(leave empty)*

### Step 3: Authorize

1. Click **"Add"** or **"Connect"**
2. Claude.ai will redirect to your authorization page
3. Enter your password (the one you used to generate the hash)
4. Review permissions and click **"Authorize"**
5. You should see a **success page** with a countdown timer
6. **Auto-redirect** back to Claude.ai after 3 seconds
7. Status should change to **"Connected"**

### Verification

Test the connection:
- In a new Claude conversation, type: **"Get my knowledge base statistics"**
- Claude should use the `get_stats` tool from kx-hub
- You should see a response with chunk count, cluster count, etc.

## Testing

### Test OAuth Endpoints

```bash
SERVICE_URL=https://kx-hub-mcp-386230044357.europe-west1.run.app

# Health check
curl $SERVICE_URL/health

# Server info
curl $SERVICE_URL/

# OAuth discovery
curl $SERVICE_URL/.well-known/oauth-authorization-server | jq

# Expected output:
{
  "issuer": "https://kx-hub-mcp-386230044357.europe-west1.run.app",
  "authorization_endpoint": "https://kx-hub-mcp-386230044357.europe-west1.run.app/authorize",
  "token_endpoint": "https://kx-hub-mcp-386230044357.europe-west1.run.app/token",
  "registration_endpoint": "https://kx-hub-mcp-386230044357.europe-west1.run.app/register",
  ...
}
```

## Troubleshooting

### Issue: "Connector not connected" in Claude.ai

**Possible Causes:**

1. **`.well-known` endpoints not reachable**
   - **Test:** `curl https://kx-hub-mcp-386230044357.europe-west1.run.app/.well-known/oauth-protected-resource`
   - **Expected:** 200 OK with OAuth metadata

2. **HTTP instead of HTTPS Issuer**
   - **Test:** `curl .../.well-known/oauth-authorization-server | jq .issuer`
   - **Expected:** `https://` URL (not `http://`)
   - **Fix:** Ensure OAUTH_ISSUER env var is set correctly

3. **Token validation fails**
   - **Check Cloud Run logs:**
     ```bash
     gcloud run services logs read kx-hub-mcp --region=europe-west1 --limit=50
     ```
   - **Look for:** "JWT verification failed" errors

### Issue: "Invalid password" on login

**Cause**: Password hash doesn't match
**Solution**: Regenerate hash and update environment:

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'YourPassword', bcrypt.gensalt()).decode())"
# Update OAUTH_USER_PASSWORD_HASH env var and redeploy
```

### Issue: "Token expired" errors

**Cause**: Access token expired (1 hour expiry)
**Solution**: Claude automatically refreshes tokens. If it fails, re-authorize in Settings.

### Debugging Tips

**View logs:**
```bash
gcloud run services logs read kx-hub-mcp --region=europe-west1 --project=kx-hub --limit=50
```

**Check Firestore data:**
```bash
# List registered clients
gcloud firestore documents list oauth_clients --project=kx-hub
```

## Security Considerations

- JWT tokens signed with RS256 (asymmetric)
- Client secrets hashed with bcrypt
- Refresh tokens rotate on each use (one-time)
- Authorization codes expire after 10 minutes
- Access tokens expire after 1 hour
- HTTPS enforced by Cloud Run
- Secret Manager for sensitive keys
- Single-user system (only you can authorize)

## Cost Estimate

- Cloud Run: ~$0.50-1.00/month (free tier)
- Secret Manager: ~$0.12/month
- Firestore: ~$0.05/month
- **Total**: ~$0.70/month

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

4. **MCP Requests**:
   - Claude POSTs to `/` with `Authorization: Bearer <jwt>`
   - Server validates JWT signature
   - Processes MCP JSON-RPC request
   - Returns tool results

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
- `TAVILY_API_KEY`: For reading recommendations

## References

- [RFC 7591: OAuth 2.0 Dynamic Client Registration](https://datatracker.ietf.org/doc/html/rfc7591)
- [RFC 6749: OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749)
- [MCP Protocol Specification](https://modelcontextprotocol.io)
