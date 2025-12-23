# Remote MCP Server - Deployment Guide

Der kx-hub MCP Server kann sowohl **lokal** (stdio) als auch **remote** (Cloud Run) betrieben werden.

## Übersicht

### Lokal (Standard)
- **Transport**: stdio
- **Zugriff**: Nur auf deinem Mac
- **Client**: Claude Desktop
- **Auth**: Keine (localhost)
- **Kosten**: $0

### Remote (Cloud Run)
- **Transport**: MCP Streamable HTTP
- **Zugriff**: Von überall via HTTPS
- **Clients**: Claude.ai, Claude Mobile, Claude Code
- **Auth**: OAuth 2.1 mit JWT
- **Kosten**: ~$0.70/Monat

## Architektur

```
Claude.ai / Claude Code
  ↓ (Streamable HTTP + OAuth 2.1)
Python MCP Server (Cloud Run)
  ↓ (Firestore + Vertex AI)
GCP Services
```

**Service URL**: `https://kx-hub-mcp-386230044357.europe-west1.run.app`

### Konsolidierter Service

Ein einziger Python-Service kombiniert:
- OAuth 2.1 mit Dynamic Client Registration
- MCP Streamable HTTP Transport
- Alle Knowledge Base Tools

## Lokale Nutzung (Kein Deployment nötig)

Läuft wie bisher mit Claude Desktop:

```json
{
  "mcpServers": {
    "kx-hub": {
      "command": "python",
      "args": ["-m", "src.mcp_server.main"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/key.json",
        "GCP_PROJECT": "your-project",
        "GCP_REGION": "us-central1",
        "FIRESTORE_COLLECTION": "kb_items"
      }
    }
  }
}
```

## Remote Deployment

### Voraussetzungen

1. **Google Cloud SDK**
   ```bash
   gcloud auth login
   gcloud config set project kx-hub
   ```

2. **Docker** (für lokales Testen)
   ```bash
   docker --version
   ```

### Deployment mit Cloud Build

```bash
gcloud builds submit --config cloudbuild.mcp-consolidated.yaml --project=kx-hub
```

### Manuelles Deployment

```bash
# 1. Docker Image bauen
docker build -f Dockerfile.mcp-consolidated -t europe-west1-docker.pkg.dev/kx-hub/kx-hub/mcp-consolidated:latest .

# 2. Image pushen
docker push europe-west1-docker.pkg.dev/kx-hub/kx-hub/mcp-consolidated:latest

# 3. Cloud Run deployen
gcloud run deploy kx-hub-mcp \
  --image=europe-west1-docker.pkg.dev/kx-hub/kx-hub/mcp-consolidated:latest \
  --region=europe-west1 \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT=kx-hub,FIRESTORE_DATABASE=kx-hub,OAUTH_ISSUER=https://kx-hub-mcp-386230044357.europe-west1.run.app,OAUTH_USER_EMAIL=your-email@example.com,OAUTH_USER_PASSWORD_HASH=\$2b\$12\$..." \
  --set-secrets="TAVILY_API_KEY=TAVILY_API_KEY:latest" \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --timeout=300 \
  --project=kx-hub
```

## Environment Variables

| Variable | Beschreibung |
|----------|--------------|
| `GCP_PROJECT` | GCP Project ID |
| `FIRESTORE_DATABASE` | Firestore Datenbank |
| `OAUTH_ISSUER` | OAuth Issuer URL (Service URL) |
| `OAUTH_USER_EMAIL` | Autorisierter Benutzer |
| `OAUTH_USER_PASSWORD_HASH` | bcrypt Passwort-Hash |

## Secrets

| Secret | Beschreibung |
|--------|--------------|
| `TAVILY_API_KEY` | Für Reading Recommendations |
| `oauth-jwt-private-key` | RSA Private Key für JWT Signatur |
| `oauth-jwt-public-key` | RSA Public Key für JWT Verifizierung |

## Dateien

```
src/mcp_server/
├── server.py           # FastAPI Server (OAuth + MCP + Tools)
├── oauth_server.py     # OAuth 2.1 Implementation
├── oauth_storage.py    # Firestore Token Storage
├── oauth_templates.py  # Login/Consent HTML Pages
├── tools.py            # Tool Implementations
├── firestore_client.py # Firestore Queries
├── embeddings.py       # Vertex AI Embeddings
└── requirements.txt    # Python Dependencies

Dockerfile.mcp-consolidated
cloudbuild.mcp-consolidated.yaml
```

## Testen

### Health Check

```bash
curl https://kx-hub-mcp-386230044357.europe-west1.run.app/health
# {"status":"healthy","service":"kx-hub-mcp-server","transport":"streamable-http"}
```

### Server Info

```bash
curl https://kx-hub-mcp-386230044357.europe-west1.run.app/
```

### OAuth Discovery

```bash
curl https://kx-hub-mcp-386230044357.europe-west1.run.app/.well-known/oauth-authorization-server | jq
```

### MCP Endpoint (erfordert Auth)

```bash
curl -X POST https://kx-hub-mcp-386230044357.europe-west1.run.app/ \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

## Nutzung mit Claude.ai

1. Öffne [claude.ai/settings](https://claude.ai/settings)
2. Gehe zu **Connectors** / **Integrations**
3. Klicke **"Add MCP Server"**
4. Gib ein:
   - **Name**: `kx-hub`
   - **URL**: `https://kx-hub-mcp-386230044357.europe-west1.run.app`
   - **OAuth**: *(leer lassen - wird automatisch konfiguriert)*
5. Durchlaufe OAuth Flow (Login + Consent)
6. Fertig!

## Monitoring

### Logs anzeigen

```bash
gcloud run services logs read kx-hub-mcp --region=europe-west1 --project=kx-hub --limit=50
```

### Service Status

```bash
gcloud run services describe kx-hub-mcp --region=europe-west1 --project=kx-hub
```

## Troubleshooting

### 401 Unauthorized
- Token abgelaufen (1 Stunde Lifetime)
- Client sollte refresh_token verwenden

### JWT verification failed
- Überprüfe ob `oauth-jwt-public-key` mit `oauth-jwt-private-key` übereinstimmt
- Issuer URL muss mit Service URL übereinstimmen

### Service nicht erreichbar
- Cloud Run Logs prüfen
- Health Endpoint testen

## Kosten

**Monatliche Kosten:** ~$0.70

| Service | Kosten |
|---------|--------|
| Cloud Run | $0.50 |
| Secret Manager | $0.12 |
| Firestore | $0.08 |
| **Gesamt** | **$0.70** |

## Updates

Nach Code-Änderungen:

```bash
gcloud builds submit --config cloudbuild.mcp-consolidated.yaml --project=kx-hub
```

## Cleanup

Service löschen:

```bash
gcloud run services delete kx-hub-mcp --region=europe-west1 --project=kx-hub
```

## FAQ

**Q: Funktioniert das auf iOS?**
A: Ja! Claude Mobile unterstützt Remote MCP Server mit OAuth.

**Q: Kann ich beides nutzen (lokal + remote)?**
A: Ja! Lokal für Claude Desktop (stdio), remote für Claude.ai/Mobile.

**Q: Was passiert mit meinen Daten?**
A: Nichts wird gespeichert. Server ist stateless, liest nur aus Firestore.
