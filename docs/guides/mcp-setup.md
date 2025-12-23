# MCP Server Setup Guide

This guide walks you through setting up the kx-hub MCP server for Claude Desktop integration.

## Prerequisites

- Python 3.8 or higher
- Claude Desktop installed
- GCP service account with Firestore read access
- kx-hub knowledge base deployed with 813 chunks

## Installation

### 1. Install Dependencies

```bash
cd /Users/christian/dev/kx-hub/src/mcp_server
pip install -r requirements.txt
```

### 2. Set Up GCP Authentication

Download your service account JSON key file from Google Cloud Console:

1. Go to [GCP Console](https://console.cloud.google.com/)
2. Navigate to IAM & Admin → Service Accounts
3. Find your kx-hub service account
4. Create a new JSON key
5. Save the file to a secure location (e.g., `~/.config/gcp/kx-hub-key.json`)

**Required IAM Permissions:**
- `roles/datastore.user` (Firestore read access)
- `roles/aiplatform.user` (Vertex AI embeddings)

### 3. Configure Claude Desktop

Edit your Claude Desktop configuration file:

**macOS:**
```bash
code ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Linux:**
```bash
code ~/.config/Claude/claude_desktop_config.json
```

Add the kx-hub MCP server configuration:

```json
{
  "mcpServers": {
    "kx-hub": {
      "command": "python3",
      "args": ["/Users/christian/dev/kx-hub/src/mcp_server/main.py"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/your/kx-hub-key.json",
        "GCP_PROJECT": "kx-hub",
        "GCP_REGION": "europe-west4",
        "FIRESTORE_COLLECTION": "kb_items"
      }
    }
  }
}
```

**Important:** Replace `/path/to/your/kx-hub-key.json` with the actual path to your service account key file.

### 4. Restart Claude Desktop

Quit and restart Claude Desktop to load the MCP server configuration.

## Verification

Open a new conversation in Claude Desktop and check for the kx-hub server:

1. Look for the server indicator in the UI (usually bottom-left)
2. Try a simple query: "What's in my knowledge base?"
3. Claude should use the `get_stats` tool to retrieve information

## Troubleshooting

### Server Not Appearing in Claude Desktop

**Check MCP Logs:**

On macOS:
```bash
tail -f ~/Library/Logs/Claude/mcp*.log
```

On Linux:
```bash
tail -f ~/.local/share/Claude/logs/mcp*.log
```

**Common Issues:**

1. **Invalid JSON Configuration**
   - Validate your `claude_desktop_config.json` with a JSON linter
   - Ensure all paths use proper escaping

2. **Missing Environment Variables**
   - Check that `GOOGLE_APPLICATION_CREDENTIALS` path is correct
   - Verify the service account key file exists and is readable

3. **Permission Errors**
   - Ensure the service account has Firestore and Vertex AI permissions
   - Test authentication: `gcloud auth activate-service-account --key-file=<path>`

4. **Python Import Errors**
   - Verify all dependencies are installed
   - Check Python version: `python3 --version` (must be 3.8+)

### Server Connects but Tools Don't Work

**Check Firestore Access:**
```bash
python3 -c "
import os
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/path/to/key.json'
os.environ['GCP_PROJECT'] = 'kx-hub'
os.environ['FIRESTORE_COLLECTION'] = 'kb_items'
from src.mcp_server import firestore_client
chunks = firestore_client.list_all_chunks(limit=1)
print(f'Success! Found {len(chunks)} chunk(s)')
"
```

**Check Vertex AI Access:**
```bash
python3 -c "
import os
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/path/to/key.json'
os.environ['GCP_PROJECT'] = 'kx-hub'
os.environ['GCP_REGION'] = 'europe-west4'
from src.mcp_server import embeddings
embedding = embeddings.generate_query_embedding('test')
print(f'Success! Generated {len(embedding)}-dimensional embedding')
"
```

### Slow Query Performance

- **First Query Delay:** Initial query takes 2-3 seconds due to cold start (client initialization)
- **Subsequent Queries:** Should complete in <1 second
- **Embedding Generation:** Adds ~200-500ms per query
- **Firestore Vector Search:** Typically <300ms for 10 results

If queries consistently take >2 seconds, check:
- Network latency to GCP
- Firestore index health (ensure vector index exists on `embedding` field)
- GCP quota limits (Vertex AI QPM, Firestore read limits)

## Uninstallation

To remove the MCP server:

1. Open `claude_desktop_config.json`
2. Remove the `"kx-hub"` entry from `mcpServers`
3. Save and restart Claude Desktop

## Next Steps

- [Usage Guide](./mcp-server-usage.md) - Learn how to query your knowledge base
- [Architecture Overview](./architecture/mcp-integration.md) - Understand how it works
- [Troubleshooting](./mcp-server-setup.md#troubleshooting) - Common issues and solutions
