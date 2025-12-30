# MCP Server Setup - Quick Reference

Follow these steps to create the service account and configure Claude Desktop.

## Step 1: Apply Terraform Changes

```bash
cd /Users/christian/dev/kx-hub/terraform

# Preview changes
terraform plan

# Create the service account
terraform apply
```

**What this creates:**
- Service account: `mcp-server-sa@kx-hub.iam.gserviceaccount.com`
- IAM role: `roles/datastore.user` (Firestore read access)
- IAM role: `roles/aiplatform.user` (Vertex AI embeddings)

---

## Step 2: Generate Service Account Key

Run the helper script:

```bash
cd /Users/christian/dev/kx-hub
./setup-mcp-credentials.sh
```

**What this does:**
- Creates `~/.config/gcp/` directory
- Generates JSON key file: `~/.config/gcp/kx-hub-mcp-key.json`
- Shows you the exact Claude Desktop config to use

**OR manually:**

```bash
# Create directory
mkdir -p ~/.config/gcp
chmod 700 ~/.config/gcp

# Generate key
gcloud iam service-accounts keys create ~/.config/gcp/kx-hub-mcp-key.json \
  --iam-account=mcp-server-sa@kx-hub.iam.gserviceaccount.com

# Secure the key
chmod 600 ~/.config/gcp/kx-hub-mcp-key.json
```

---

## Step 3: Configure Claude Desktop

**macOS:**
```bash
code ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Linux:**
```bash
code ~/.config/Claude/claude_desktop_config.json
```

**Add this configuration:**

```json
{
  "mcpServers": {
    "kx-hub": {
      "command": "python3",
      "args": ["/Users/christian/dev/kx-hub/src/mcp_server/main.py"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/Users/christian/.config/gcp/kx-hub-mcp-key.json",
        "GCP_PROJECT": "kx-hub",
        "GCP_REGION": "europe-west4",
        "FIRESTORE_COLLECTION": "kb_items"
      }
    }
  }
}
```

**Important:** Use the **full absolute path** to your key file!

---

## Step 4: Restart Claude Desktop

1. Quit Claude Desktop completely
2. Reopen Claude Desktop
3. Check for the kx-hub MCP server in the UI

---

## Step 5: Test the MCP Server

**In Claude Desktop, try these queries:**

```
"What's in my knowledge base?"
```
→ Uses `get_stats` tool to show totals

```
"What insights do I have about decision making?"
```
→ Uses `search_semantic` to find relevant chunks

```
"Show me all highlights from Daniel Kahneman"
```
→ Uses `search_by_metadata` to filter by author

---

## Verification Commands

**Test authentication:**
```bash
gcloud auth activate-service-account \
  --key-file=~/.config/gcp/kx-hub-mcp-key.json
```

**Test Firestore access:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcp/kx-hub-mcp-key.json
export GCP_PROJECT=kx-hub
export FIRESTORE_COLLECTION=kb_items

python3 -c "
import os
os.environ['GCP_PROJECT'] = 'kx-hub'
os.environ['FIRESTORE_COLLECTION'] = 'kb_items'
from src.mcp_server import firestore_client
stats = firestore_client.get_stats()
print(f'✓ Success! Found {stats[\"total_chunks\"]} chunks')
"
```

**Test Vertex AI access:**
```bash
python3 -c "
import os
os.environ['GCP_PROJECT'] = 'kx-hub'
os.environ['GCP_REGION'] = 'europe-west4'
from src.mcp_server import embeddings
embedding = embeddings.generate_query_embedding('test query')
print(f'✓ Success! Generated {len(embedding)}-dimensional embedding')
"
```

---

## Troubleshooting

**Server not appearing in Claude Desktop:**
- Check MCP logs: `tail -f ~/Library/Logs/Claude/mcp*.log` (macOS)
- Verify JSON syntax in config file
- Ensure key file path is absolute (not relative)
- Check Python version: `python3 --version` (must be 3.8+)

**Permission errors:**
- Verify service account has both IAM roles:
  ```bash
  gcloud projects get-iam-policy kx-hub \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:mcp-server-sa@kx-hub.iam.gserviceaccount.com"
  ```

**Import errors:**
- Install dependencies:
  ```bash
  cd /Users/christian/dev/kx-hub/src/mcp_server
  pip install -r requirements.txt
  ```

---

## Files Created

- `terraform/main.tf` - Service account resources (lines 583-605)
- `setup-mcp-credentials.sh` - Helper script for key generation
- `MCP-SETUP-STEPS.md` - This guide
- `~/.config/gcp/kx-hub-mcp-key.json` - Service account key (after running setup)

---

## Security Notes

**Key File Security:**
- Stored in: `~/.config/gcp/` (user-only directory)
- Permissions: `600` (read/write for user only)
- **Never commit to git** (already in .gitignore)
- Read-only access (Firestore + Vertex AI only, no write permissions)

**IAM Permissions:**
- `roles/datastore.user` - Read-only Firestore access
- `roles/aiplatform.user` - Vertex AI embeddings only (no training/tuning)
- **No** storage write access
- **No** logging write access (optional for MCP server)
- **No** secrets access
- **No** Pub/Sub access

---

## Next Steps

See full documentation:
- [MCP Server Setup Guide](docs/mcp-server-setup.md)
- [MCP Server Usage Guide](docs/mcp-server-usage.md)
- [MCP Integration Architecture](docs/architecture/mcp-integration.md)
