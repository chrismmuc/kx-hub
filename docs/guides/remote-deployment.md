# Remote MCP Server - Setup Guide

Der kx-hub MCP Server kann sowohl **lokal** (stdio) als auch **remote** (Cloud Run) betrieben werden.

## Übersicht

### Lokal (Standard)
- **Transport**: stdio
- **Zugriff**: Nur auf deinem Mac
- **Client**: Claude Desktop
- **Auth**: Keine (localhost)
- **Kosten**: $0

### Remote (Optional)
- **Transport**: SSE (Server-Sent Events)
- **Zugriff**: Von überall via HTTPS
- **Clients**: ChatGPT Desktop, andere HTTP-Clients
- **Auth**: Bearer Token (Secret Manager)
- **Kosten**: ~$0.21/Monat

## Kosten Remote-Deployment

**Monatliche Kosten:** ~$0.21

| Service | Kosten |
|---------|--------|
| Cloud Run | $0.08 |
| Secret Manager | $0.12 |
| Container Registry | $0.01 |
| **Gesamt** | **$0.21** |

Bei hoher Nutzung (1000 Requests/Monat): ~$1.73/Monat

## Lokale Nutzung (Kein Deployment nötig)

Läuft wie bisher:

```bash
# Im Claude Desktop MCP Config
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
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Docker**
   ```bash
   docker --version
   ```

3. **Terraform**
   ```bash
   terraform --version
   ```

4. **Tavily API Key**
   - Registriere dich auf https://tavily.com
   - Kopiere deinen API Key

### Deployment-Schritte

#### 1. Terraform konfigurieren

```bash
cd terraform/mcp-remote
cp terraform.tfvars.example terraform.tfvars

# Editiere terraform.tfvars:
# - project_id: Deine GCP Project ID
# - tavily_api_key: Dein Tavily API Key
# - alert_email: Deine E-Mail für Alerts
```

#### 2. Docker Image bauen und pushen

```bash
# Von project root
export PROJECT_ID=$(gcloud config get-value project)
export IMAGE_TAG="gcr.io/${PROJECT_ID}/kx-hub-mcp-remote:latest"

# Image bauen
docker build \
  -f Dockerfile.mcp-server \
  -t "${IMAGE_TAG}" \
  --platform linux/amd64 \
  .

# Docker für GCR konfigurieren
gcloud auth configure-docker

# Image pushen
docker push "${IMAGE_TAG}"
```

#### 3. Infrastructure deployen

```bash
cd terraform/mcp-remote

# Terraform initialisieren
terraform init

# Plan reviewen
terraform plan

# Deployen
terraform apply
```

#### 4. Credentials holen

```bash
# Service URL
terraform output service_url

# Auth Token (GEHEIM HALTEN!)
terraform output -raw auth_token
```

### Nutzung mit ChatGPT

1. Öffne ChatGPT Desktop
2. Gehe zu Settings → Custom GPTs
3. Erstelle neue Action:

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "kx-hub Knowledge Base",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "https://your-service-url"
    }
  ],
  "paths": {
    "/sse": {
      "post": {
        "operationId": "query_knowledge_base",
        "summary": "Query knowledge base",
        "security": [
          {
            "BearerAuth": []
          }
        ]
      }
    }
  },
  "components": {
    "securitySchemes": {
      "BearerAuth": {
        "type": "http",
        "scheme": "bearer"
      }
    }
  }
}
```

4. Füge Bearer Token hinzu (aus `terraform output`)

## Sicherheit

### Authentication
- **Methode**: Bearer Token
- **Token**: 48-char random string (Secret Manager)
- **Endpoint**: Alle Requests außer `/health`

### Service Account
- **Name**: `mcp-server-remote@PROJECT.iam.gserviceaccount.com`
- **Permissions**:
  - ✅ Firestore read (kb_items, clusters, config)
  - ✅ Secret Manager accessor (MCP_AUTH_TOKEN, TAVILY_API_KEY)
  - ✅ Vertex AI user (embeddings, Gemini)
  - ✅ Write zu config/recommendation_shown (URL tracking)
  - ❌ Keine anderen Schreibrechte

### Secrets
- **MCP_AUTH_TOKEN**: Auto-generiert (48 Zeichen)
- **TAVILY_API_KEY**: Von dir bereitgestellt
- **Storage**: Google Secret Manager
- **Zugriff**: Nur Service Account

### Network
- **Endpoint**: Public HTTPS
- **Auth**: Application-level (Bearer Token)
- **TLS**: Cloud Run managed certificate
- **CORS**: Disabled

## Monitoring

### Logs anzeigen

```bash
gcloud run services logs read kx-hub-mcp-remote \
  --region=us-central1 \
  --limit=50
```

### Dashboard öffnen

```bash
# URL ausgeben
PROJECT_ID=$(gcloud config get-value project)
echo "https://console.cloud.google.com/monitoring/dashboards?project=${PROJECT_ID}"
```

### Alerts

Automatische Alerts bei:
- **5xx Errors**: >5/min für 5 Minuten
- **Auth Failures**: >10/min für 5 Minuten

Email-Benachrichtigung an `alert_email` (terraform.tfvars)

## Troubleshooting

### Health Check

```bash
SERVICE_URL=$(cd terraform/mcp-remote && terraform output -raw service_url)
curl ${SERVICE_URL}/health

# Erwartete Antwort:
# {"status":"healthy"}
```

### Auth Test

```bash
AUTH_TOKEN=$(cd terraform/mcp-remote && terraform output -raw auth_token)
curl -H "Authorization: Bearer ${AUTH_TOKEN}" ${SERVICE_URL}/sse
```

### Häufige Fehler

**401 Unauthorized**
- Bearer Token falsch oder fehlt
- Token aus `terraform output -raw auth_token` holen

**500 Internal Server Error**
- Logs checken: `gcloud run services logs read kx-hub-mcp-remote`
- Secrets validieren: MCP_AUTH_TOKEN und TAVILY_API_KEY vorhanden?

**Timeout (504)**
- Recommendation-Query dauert >120s
- Timeout in Terraform erhöhen (main.tf, template.timeout)

## Updates

Nach Code-Änderungen:

```bash
# 1. Image neu bauen und pushen
docker build -f Dockerfile.mcp-server -t "${IMAGE_TAG}" .
docker push "${IMAGE_TAG}"

# 2. Cloud Run neu deployen (pullt neues Image)
cd terraform/mcp-remote
terraform apply
```

## Cleanup

Alle Ressourcen löschen:

```bash
cd terraform/mcp-remote
terraform destroy
```

**Warnung**: Löscht:
- Cloud Run Service
- Service Account
- Secrets (inkl. Auth Token)
- Monitoring Alerts

## FAQ

**Q: Funktioniert das auf iOS?**
A: Nein, Claude iOS unterstützt kein MCP (weder lokal noch remote).

**Q: Kann ich beides nutzen (lokal + remote)?**
A: Ja! Lokal für Claude Desktop, remote für ChatGPT/andere Clients.

**Q: Was passiert mit meinen Daten?**
A: Nichts wird gespeichert. Server ist stateless, liest nur aus Firestore.

**Q: Wie sichere ich den Endpoint ab?**
A: Bearer Token Auth ist bereits implementiert. Optional: IP Whitelisting über Cloud Armor.

**Q: Kostet mehr bei hoher Nutzung?**
A: Ja, aber begrenzt: Max $1.73/Monat (1000 Requests). Danach skaliert linear.

**Q: Kann ich den Token rotieren?**
A: Ja, neuen Secret-Wert in Secret Manager setzen, dann `terraform apply`.

## Support

Bei Problemen:
1. Logs checken
2. Health endpoint testen
3. Terraform outputs validieren
4. GitHub Issue erstellen
