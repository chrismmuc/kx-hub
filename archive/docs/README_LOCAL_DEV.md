# Local Development Setup

Schnelles lokales Testen ohne Cloud Run Deployments.

## Quick Start

```bash
# 1. Secrets generieren
./scripts/generate_local_secrets.sh

# 2. Alle Services starten
docker-compose up --build

# 3. OAuth Flow testen
./scripts/test_oauth_flow.sh http://localhost:8082
```

## Services

- **Firestore Emulator**: `localhost:8080`
- **Python Tools API**: `localhost:8081`
- **OAuth Server**: `localhost:8082`
- **MCP Server**: `localhost:8083`

## OAuth Flow manuell testen

### 1. Client Registration
```bash
curl -X POST http://localhost:8082/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Test Client",
    "redirect_uris": ["http://localhost:3000/callback"],
    "grant_types": ["authorization_code"],
    "response_types": ["code"]
  }'
```

### 2. Authorization (Browser)
```
http://localhost:8082/authorize?
  response_type=code&
  client_id=<CLIENT_ID>&
  redirect_uri=http://localhost:3000/callback&
  state=test123&
  scope=kx-hub:read
```

Login mit:
- Email: `chrismu82@googlemail.com`
- Password: (dein gesetztes Passwort)

### 3. Token Exchange
```bash
curl -X POST http://localhost:8082/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=<CODE>&redirect_uri=http://localhost:3000/callback&client_id=<CLIENT_ID>&client_secret=<SECRET>"
```

### 4. MCP Tool Call (mit Token)
```bash
curl http://localhost:8083/tools/search_kb \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'
```

## Logs

```bash
# Alle Services
docker-compose logs -f

# Nur OAuth Server
docker-compose logs -f oauth-server

# Nur MCP Server
docker-compose logs -f mcp-server
```

## Clean Up

```bash
docker-compose down -v
```

## Unit Tests (TODO)

```bash
# Python OAuth Tests
cd src/mcp_server
pytest test_oauth_server.py

# TypeScript SSE Tests
cd src/mcp_server_ts
npm test
```
