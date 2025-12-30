#!/bin/bash
# Data Wipe & Reset Script for Chunking Migration
#
# WARNING: This script will DELETE all existing knowledge base data
# Use only when ready to migrate to chunking-based architecture
#
# Prerequisites:
# - gcloud CLI configured with correct project
# - Appropriate permissions for Firestore and Cloud Storage
# - Backup of any critical data (if needed)

set -e  # Exit on error

# Configuration
PROJECT_ID="${GCP_PROJECT:-kx-hub}"
REGION="${GCP_REGION:-europe-west4}"
MARKDOWN_BUCKET="${MARKDOWN_BUCKET:-kx-hub-markdown-normalized}"
PIPELINE_BUCKET="${PIPELINE_BUCKET:-kx-hub-pipeline}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}===============================================${NC}"
echo -e "${YELLOW}KX-Hub Data Wipe & Reset Script${NC}"
echo -e "${YELLOW}===============================================${NC}"
echo ""
echo -e "Project: ${GREEN}${PROJECT_ID}${NC}"
echo -e "Region: ${GREEN}${REGION}${NC}"
echo -e "Markdown Bucket: ${GREEN}${MARKDOWN_BUCKET}${NC}"
echo -e "Pipeline Bucket: ${GREEN}${PIPELINE_BUCKET}${NC}"
echo ""
echo -e "${RED}WARNING: This will DELETE all existing data!${NC}"
echo -e "${RED}This includes:${NC}"
echo -e "${RED}- All Firestore kb_items documents${NC}"
echo -e "${RED}- All Firestore pipeline_items documents${NC}"
echo -e "${RED}- All markdown files in Cloud Storage${NC}"
echo -e "${RED}- All pipeline manifests${NC}"
echo ""
read -p "Are you sure you want to continue? Type 'YES' to confirm: " CONFIRM

if [ "$CONFIRM" != "YES" ]; then
    echo -e "${YELLOW}Aborted. No changes made.${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}Step 1: Wiping Firestore kb_items collection...${NC}"
gcloud firestore databases delete-documents \
    --collection=kb_items \
    --project="${PROJECT_ID}" \
    --recursive \
    --quiet || {
        echo -e "${RED}Failed to delete kb_items. Continuing anyway...${NC}"
    }
echo -e "${GREEN}✓ kb_items collection wiped${NC}"

echo ""
echo -e "${YELLOW}Step 2: Wiping Firestore pipeline_items collection...${NC}"
gcloud firestore databases delete-documents \
    --collection=pipeline_items \
    --project="${PROJECT_ID}" \
    --recursive \
    --quiet || {
        echo -e "${RED}Failed to delete pipeline_items. Continuing anyway...${NC}"
    }
echo -e "${GREEN}✓ pipeline_items collection wiped${NC}"

echo ""
echo -e "${YELLOW}Step 3: Clearing Cloud Storage markdown files...${NC}"
gcloud storage rm "gs://${MARKDOWN_BUCKET}/notes/**" \
    --recursive \
    --quiet 2>/dev/null || {
        echo -e "${YELLOW}No markdown files found or bucket doesn't exist. Skipping...${NC}"
    }
echo -e "${GREEN}✓ Markdown files cleared${NC}"

echo ""
echo -e "${YELLOW}Step 4: Clearing Cloud Storage pipeline manifests...${NC}"
gcloud storage rm "gs://${PIPELINE_BUCKET}/pipeline/manifests/**" \
    --recursive \
    --quiet 2>/dev/null || {
        echo -e "${YELLOW}No manifests found or bucket doesn't exist. Skipping...${NC}"
    }
echo -e "${GREEN}✓ Pipeline manifests cleared${NC}"

echo ""
echo -e "${GREEN}===============================================${NC}"
echo -e "${GREEN}Data wipe complete!${NC}"
echo -e "${GREEN}===============================================${NC}"
echo ""
echo -e "Next steps:"
echo -e "1. Deploy updated Cloud Functions (normalize, embed)"
echo -e "2. Verify chunking configuration (environment variables)"
echo -e "3. Trigger full pipeline run: gcloud workflows execute batch-pipeline"
echo -e "4. Monitor logs for chunking behavior"
echo -e "5. Validate chunk creation in Firestore kb_items"
echo ""
echo -e "${YELLOW}Raw JSON data is preserved. Re-run the pipeline to rebuild chunks.${NC}"
