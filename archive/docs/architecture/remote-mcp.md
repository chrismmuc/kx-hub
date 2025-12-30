# Remote MCP Server Architecture

## Overview

The kx-hub remote MCP server is a consolidated Python service that provides OAuth 2.1 authentication and MCP Streamable HTTP transport for Claude.ai and Claude Code access.

```
Claude.ai / Claude Code
  ↓ (Streamable HTTP + OAuth 2.1)
Python MCP Server (Cloud Run)
  ↓ (Firestore + Vertex AI)
GCP Services
```

## Architecture

### Single Consolidated Service

**URL**: `https://kx-hub-mcp-386230044357.europe-west1.run.app`
**Language**: Python + FastAPI
**Transport**: MCP Streamable HTTP (POST /)

The server combines:
- OAuth 2.1 with Dynamic Client Registration (RFC 7591)
- MCP Streamable HTTP transport (JSON-RPC over HTTP)
- All knowledge base tools

### Endpoints

**OAuth 2.1**:
- `GET /.well-known/oauth-authorization-server` - OAuth metadata (RFC 8414)
- `GET /.well-known/oauth-protected-resource` - Resource metadata (RFC 9728)
- `POST /register` - Dynamic Client Registration
- `GET/POST /authorize` - Authorization with login/consent UI
- `POST /token` - Token exchange (authorization_code, refresh_token)

**MCP**:
- `POST /` - MCP Streamable HTTP endpoint (requires JWT auth)
- `GET /` - Server info
- `GET /health` - Health check

### Authentication Flow

```
1. Client discovers OAuth metadata
   GET /.well-known/oauth-authorization-server

2. Client registers dynamically
   POST /register
   → Returns client_id + client_secret

3. User authorizes via browser
   GET /authorize?client_id=...&redirect_uri=...&code_challenge=...
   → Login page → Consent page → Redirect with code

4. Client exchanges code for tokens
   POST /token (grant_type=authorization_code)
   → Returns JWT access_token + refresh_token

5. Client calls MCP with JWT
   POST / (Authorization: Bearer <jwt>)
   → JSON-RPC requests/responses
```

### JWT Token

Access tokens are RS256-signed JWTs with:
- `iss`: Issuer URL (service URL)
- `sub`: User ID (email)
- `aud`: Client ID
- `scope`: Granted scope
- `exp`: Expiration (1 hour)

Keys stored in Secret Manager:
- `oauth-jwt-private-key` - For signing
- `oauth-jwt-public-key` - For verification

## Tools

The MCP server exposes these tools:

| Tool | Description |
|------|-------------|
| `search_kb` | Unified semantic search with filters |
| `get_chunk` | Chunk details with knowledge card |
| `get_recent` | Recent reading activity |
| `get_stats` | KB statistics |
| `list_clusters` | List semantic clusters |
| `get_cluster` | Cluster details with members |
| `configure_kb` | Configuration settings |
| `search_within_cluster` | Cluster-scoped search |
| `get_reading_recommendations` | AI-powered recommendations |

## Deployment

### Files

```
src/mcp_server/
├── server.py           # FastAPI server (OAuth + MCP + Tools)
├── oauth_server.py     # OAuth 2.1 implementation
├── oauth_storage.py    # Firestore token storage
├── oauth_templates.py  # Login/consent HTML pages
├── tools.py            # Tool implementations
├── firestore_client.py # Firestore queries
├── embeddings.py       # Vertex AI embeddings
└── requirements.txt    # Python dependencies

Dockerfile.mcp-consolidated
cloudbuild.mcp-consolidated.yaml
```

### Deploy

```bash
gcloud builds submit --config cloudbuild.mcp-consolidated.yaml --project=kx-hub
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT` | GCP project ID |
| `FIRESTORE_DATABASE` | Firestore database name |
| `OAUTH_ISSUER` | OAuth issuer URL (service URL) |
| `OAUTH_USER_EMAIL` | Authorized user email |
| `OAUTH_USER_PASSWORD_HASH` | bcrypt password hash |

### Secrets

| Secret | Description |
|--------|-------------|
| `TAVILY_API_KEY` | For reading recommendations |
| `oauth-jwt-private-key` | RSA private key for JWT signing |
| `oauth-jwt-public-key` | RSA public key for JWT verification |

## Testing

```bash
# Health check
curl https://kx-hub-mcp-386230044357.europe-west1.run.app/health

# Server info
curl https://kx-hub-mcp-386230044357.europe-west1.run.app/

# OAuth metadata
curl https://kx-hub-mcp-386230044357.europe-west1.run.app/.well-known/oauth-authorization-server

# MCP endpoint (requires auth)
curl -X POST https://kx-hub-mcp-386230044357.europe-west1.run.app/ \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

## Integration with Claude.ai

1. Add MCP Server in Claude.ai settings
2. Enter URL: `https://kx-hub-mcp-386230044357.europe-west1.run.app`
3. Complete OAuth flow (login + consent)
4. Use kx-hub tools in conversations

## Troubleshooting

### Check service status
```bash
gcloud run services describe kx-hub-mcp --region=europe-west1 --project=kx-hub
```

### View logs
```bash
gcloud run services logs read kx-hub-mcp --region=europe-west1 --project=kx-hub --limit=50
```

### Common issues

**JWT verification failed**
- Check that `oauth-jwt-public-key` matches `oauth-jwt-private-key`
- Verify the issuer URL matches the service URL

**401 Unauthorized**
- Token may be expired (1 hour lifetime)
- Client should use refresh_token to get new access_token

**OAuth flow fails**
- Check OAUTH_USER_EMAIL and OAUTH_USER_PASSWORD_HASH are set correctly
- Verify redirect_uri matches registered client
