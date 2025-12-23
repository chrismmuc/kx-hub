# Hybrid MCP Architecture

## Übersicht

Die neue Hybrid-Architektur teilt den MCP Server in zwei Services auf:

```
Claude.ai
  ↓ (SSE + OAuth)
TypeScript MCP Server (Cloud Run)
  ↓ (HTTP)
Python Tools API (Cloud Run)
```

## Services

### 1. Python Tools API
**Port**: 8080
**Sprache**: Python + FastAPI
**Zweck**: Business Logic für alle Knowledge Base Tools

**Endpoints**:
- `GET /health` - Health check
- `POST /tools/search_kb` - Semantic search
- `POST /tools/get_chunk` - Chunk details mit knowledge card
- `POST /tools/get_recent` - Recent reading activity
- `POST /tools/get_stats` - KB statistics
- `POST /tools/list_clusters` - List semantic clusters
- `POST /tools/get_cluster` - Cluster details
- `POST /tools/configure_kb` - Configuration
- `POST /tools/search_within_cluster` - Cluster-scoped search
- `POST /tools/get_reading_recommendations` - AI recommendations

**Deployed**: `kx-hub-tools-api` (Cloud Run, europe-west1)

### 2. TypeScript MCP Server
**Port**: 8080
**Sprache**: TypeScript + Express + MCP SDK
**Zweck**: SSE Transport, OAuth Validation, Tool Proxy

**Features**:
- SSE Transport für MCP Protocol
- JWT Token Validation (OAuth 2.1)
- Proxy zu OAuth Lambda (`.well-known`, `/register`, `/authorize`, `/token`)
- Tool Call Forwarding zu Python API

**Endpoints**:
- `GET /health` - Health check
- `GET /` - SSE endpoint (requires OAuth)
- `POST /messages` - MCP messages (requires OAuth)
- `GET /.well-known/oauth-authorization-server` - OAuth metadata (proxy)
- `POST /register` - Client registration (proxy)
- `POST /authorize` - Authorization (proxy)
- `POST /token` - Token exchange (proxy)

**Deployed**: `kx-hub-mcp-server` (Cloud Run, europe-west1)

### 3. OAuth Authorization Server
**Sprache**: Python (Lambda)
**Zweck**: OAuth 2.1 Dynamic Client Registration
**Status**: Unverändert ✅

## Vorteile

1. **Funktionierende SSE**: TypeScript SDK hat keine ASGI-Probleme
2. **Minimaler Rewrite**: Python Tools bleiben unverändert
3. **Saubere Architektur**: Jeder Service hat eine Aufgabe
4. **Einfaches Debugging**: Services können einzeln getestet werden
5. **Skalierbar**: Beide Services können unabhängig skalieren

## Deployment

```bash
# Beide Services deployen
./scripts/deploy_hybrid_mcp.sh

# Oder einzeln:
gcloud builds submit --config cloudbuild.mcp-tools-api.yaml
gcloud builds submit --config cloudbuild.mcp-server-ts.yaml
```

## Environment Variables

### Python Tools API
- `GOOGLE_CLOUD_PROJECT` - GCP Project ID (automatisch gesetzt)

### TypeScript MCP Server
- `PYTHON_TOOLS_API_URL` - URL der Python Tools API
- `OAUTH_LAMBDA_URL` - URL des OAuth Lambda
- `JWT_SECRET` - Secret für JWT Validation

## Testing

```bash
# Python Tools API testen
curl https://kx-hub-tools-api-XXXXX-ew.a.run.app/health

curl -X POST https://kx-hub-tools-api-XXXXX-ew.a.run.app/tools/get_stats \
  -H "Content-Type: application/json"

# TypeScript MCP Server testen
curl https://kx-hub-mcp-server-XXXXX-ew.a.run.app/health

# OAuth Metadata
curl https://kx-hub-mcp-server-XXXXX-ew.a.run.app/.well-known/oauth-authorization-server
```

## Integration mit Claude.ai

1. MCP Server URL in Claude.ai eintragen: `https://kx-hub-mcp-server-XXXXX-ew.a.run.app`
2. OAuth Flow durchlaufen (Dynamic Client Registration)
3. Token wird automatisch validiert
4. Tools werden über Python API ausgeführt

## Dateien

### Python Tools API
- `/src/mcp_tools_api/main.py` - FastAPI Server
- `/src/mcp_tools_api/requirements.txt` - Dependencies
- `/Dockerfile.mcp-tools-api` - Docker Image
- `/cloudbuild.mcp-tools-api.yaml` - Cloud Build Config

### TypeScript MCP Server
- `/src/mcp_server_ts/src/server.ts` - Express Server
- `/src/mcp_server_ts/src/controllers/SseController.ts` - SSE Handling
- `/src/mcp_server_ts/src/middlewares/AuthMiddleware.ts` - JWT Validation
- `/src/mcp_server_ts/src/mcp/McpToolProxy.ts` - Tool Forwarding
- `/src/mcp_server_ts/package.json` - Node Dependencies
- `/src/mcp_server_ts/tsconfig.json` - TypeScript Config
- `/Dockerfile.mcp-server-ts` - Docker Image
- `/cloudbuild.mcp-server-ts.yaml` - Cloud Build Config

## Troubleshooting

### Python Tools API läuft nicht
```bash
# Logs checken
gcloud run services logs read kx-hub-tools-api --region=europe-west1

# Service neu deployen
gcloud builds submit --config cloudbuild.mcp-tools-api.yaml
```

### TypeScript MCP Server verbindet nicht
```bash
# Logs checken
gcloud run services logs read kx-hub-mcp-server --region=europe-west1

# Environment Variables prüfen
gcloud run services describe kx-hub-mcp-server --region=europe-west1 --format=yaml | grep -A 20 env
```

### OAuth funktioniert nicht
- JWT_SECRET muss identisch mit OAuth Lambda sein
- OAUTH_LAMBDA_URL muss korrekt gesetzt sein
- `.well-known` Proxy sollte OAuth Metadata zurückgeben
