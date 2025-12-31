#!/bin/bash
# Build and publish kx-llm package to Artifact Registry
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
PROJECT_ID="kx-hub"
REGION="europe-west4"
REPO="kx-packages"

echo "=== Building kx-llm package ==="

# Clean previous builds
rm -rf dist/ build/ *.egg-info kx_llm/*.egg-info

# Build package
python3 -m pip install --upgrade build twine
python3 -m build

echo "=== Publishing to Artifact Registry ==="

# Configure twine for Artifact Registry
python3 -m twine upload \
    --repository-url "https://${REGION}-python.pkg.dev/${PROJECT_ID}/${REPO}/" \
    dist/*

echo "=== Done ==="
echo "Install with: pip install kx-llm --index-url https://${REGION}-python.pkg.dev/${PROJECT_ID}/${REPO}/simple/"
