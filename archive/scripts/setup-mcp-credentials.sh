#!/bin/bash
# Setup script for MCP Server service account and credentials
# Run this after terraform apply creates the service account

set -e

PROJECT_ID="kx-hub"
SA_EMAIL="mcp-server-sa@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_DIR="${HOME}/.config/gcp"
KEY_FILE="${KEY_DIR}/kx-hub-mcp-key.json"

echo "================================================"
echo "MCP Server Credentials Setup"
echo "================================================"
echo ""

# Create key directory if it doesn't exist
echo "1. Creating credentials directory..."
mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"
echo "   ✓ Directory: $KEY_DIR"
echo ""

# Generate service account key
echo "2. Generating service account key..."
if [ -f "$KEY_FILE" ]; then
    echo "   ⚠️  Key file already exists: $KEY_FILE"
    read -p "   Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "   Skipping key generation."
        KEY_FILE_EXISTED=true
    else
        rm "$KEY_FILE"
    fi
fi

if [ "$KEY_FILE_EXISTED" != true ]; then
    gcloud iam service-accounts keys create "$KEY_FILE" \
        --iam-account="$SA_EMAIL"
    chmod 600 "$KEY_FILE"
    echo "   ✓ Key created: $KEY_FILE"
fi
echo ""

# Display Claude Desktop configuration
echo "3. Claude Desktop Configuration"
echo "================================================"
echo ""
echo "Add this to your Claude Desktop config:"
echo ""

if [[ "$OSTYPE" == "darwin"* ]]; then
    CONFIG_PATH="~/Library/Application Support/Claude/claude_desktop_config.json"
else
    CONFIG_PATH="~/.config/Claude/claude_desktop_config.json"
fi

echo "File: $CONFIG_PATH"
echo ""
cat <<'EOF'
{
  "mcpServers": {
    "kx-hub": {
      "command": "python3",
      "args": ["/Users/christian/dev/kx-hub/src/mcp_server/main.py"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "REPLACE_WITH_KEY_PATH",
        "GCP_PROJECT": "kx-hub",
        "GCP_REGION": "europe-west4",
        "FIRESTORE_COLLECTION": "kb_items"
      }
    }
  }
}
EOF
echo ""
echo "Replace REPLACE_WITH_KEY_PATH with:"
echo "  $KEY_FILE"
echo ""

# Display verification steps
echo "4. Verification Steps"
echo "================================================"
echo ""
echo "a) Test service account authentication:"
echo "   gcloud auth activate-service-account --key-file=$KEY_FILE"
echo ""
echo "b) Test Firestore access:"
echo "   export GOOGLE_APPLICATION_CREDENTIALS=$KEY_FILE"
echo "   python3 -c 'from src.mcp_server import firestore_client; print(firestore_client.get_stats())'"
echo ""
echo "c) Restart Claude Desktop to load MCP server"
echo ""
echo "================================================"
echo "Setup complete!"
echo "================================================"
