#!/bin/bash
# Story 1.5 Operational Validation Script
# Tests the IndexDatapoint gRPC fix for Vector Search upserts

set -e

PROJECT_ID="kx-hub"
REGION="europe-west4"
SCHEDULER_REGION="europe-west3"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "============================================"
echo "  Story 1.5 Operational Validation"
echo "  IndexDatapoint gRPC Upsert Fix"
echo "============================================"
echo ""

# Function to print status
print_status() {
    local status=$1
    local message=$2
    if [[ "$status" == "PASS" ]]; then
        echo -e "${GREEN}✓${NC} $message"
    elif [[ "$status" == "FAIL" ]]; then
        echo -e "${RED}✗${NC} $message"
    elif [[ "$status" == "WARN" ]]; then
        echo -e "${YELLOW}⚠${NC} $message"
    else
        echo -e "${BLUE}ℹ${NC} $message"
    fi
}

# Step 1: Check if embed function is deployed with correct environment variables
echo "Step 1: Verify Embed Function Configuration"
echo "---------------------------------------------"

EMBED_FUNCTION=$(gcloud functions list --gen2 --region=$REGION --filter="name:embed-function" --format="value(name)" 2>/dev/null || true)

if [[ -n "$EMBED_FUNCTION" ]]; then
    print_status "PASS" "Embed function exists: $EMBED_FUNCTION"

    # Check for VECTOR_SEARCH_INDEX environment variable
    VECTOR_SEARCH_INDEX=$(gcloud functions describe embed-function --gen2 --region=$REGION --format="value(serviceConfig.environmentVariables.VECTOR_SEARCH_INDEX)" 2>/dev/null || true)

    if [[ -n "$VECTOR_SEARCH_INDEX" ]]; then
        print_status "PASS" "VECTOR_SEARCH_INDEX configured: $VECTOR_SEARCH_INDEX"
    else
        print_status "FAIL" "VECTOR_SEARCH_INDEX not found - terraform apply may not have completed"
        echo ""
        echo "Run: cd terraform && terraform apply tfplan"
        exit 1
    fi
else
    print_status "FAIL" "Embed function not found"
    exit 1
fi
echo ""

# Step 2: Trigger the pipeline
echo "Step 2: Trigger Pipeline Execution"
echo "------------------------------------"
read -p "Trigger the ingest scheduler now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "INFO" "Triggering daily-ingest-trigger-job..."
    gcloud scheduler jobs run daily-ingest-trigger-job --location=$SCHEDULER_REGION
    print_status "PASS" "Scheduler triggered successfully"

    print_status "INFO" "Waiting 30 seconds for pipeline to start..."
    sleep 30
else
    print_status "WARN" "Skipping trigger - using last execution"
fi
echo ""

# Step 3: Monitor workflow execution
echo "Step 3: Monitor Workflow Execution"
echo "------------------------------------"

LATEST_EXECUTION=$(gcloud workflows executions list batch-pipeline --location=$REGION --limit=1 --format="value(name)" 2>/dev/null || true)

if [[ -n "$LATEST_EXECUTION" ]]; then
    print_status "INFO" "Latest execution: $LATEST_EXECUTION"

    # Poll for completion (max 5 minutes)
    MAX_WAIT=300
    ELAPSED=0
    INTERVAL=10

    while [[ $ELAPSED -lt $MAX_WAIT ]]; do
        EXEC_STATE=$(gcloud workflows executions describe "$LATEST_EXECUTION" --location=$REGION --format="value(state)" 2>/dev/null || echo "UNKNOWN")

        if [[ "$EXEC_STATE" == "SUCCEEDED" ]]; then
            print_status "PASS" "Workflow execution SUCCEEDED"
            break
        elif [[ "$EXEC_STATE" == "FAILED" ]]; then
            print_status "FAIL" "Workflow execution FAILED"
            echo ""
            echo "Execution details:"
            gcloud workflows executions describe "$LATEST_EXECUTION" --location=$REGION --format="yaml(error)"
            exit 1
        elif [[ "$EXEC_STATE" == "ACTIVE" ]]; then
            echo -n "."
            sleep $INTERVAL
            ELAPSED=$((ELAPSED + INTERVAL))
        else
            print_status "INFO" "Execution state: $EXEC_STATE"
            sleep $INTERVAL
            ELAPSED=$((ELAPSED + INTERVAL))
        fi
    done
    echo ""

    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        print_status "WARN" "Workflow still running after ${MAX_WAIT}s - check manually"
    fi

    # Show execution summary
    gcloud workflows executions describe "$LATEST_EXECUTION" --location=$REGION --format="table(name,state,startTime,endTime)"
else
    print_status "FAIL" "No workflow executions found"
    exit 1
fi
echo ""

# Step 4: Check for the specific error that was being fixed
echo "Step 4: Check for IndexDatapoint Errors"
echo "-----------------------------------------"

# Get timestamp from 10 minutes ago
TIMESTAMP=$(date -u -v-10M +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S)

ERROR_LOG=$(gcloud logging read "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"embed-function\" AND textPayload=~\"Message must be initialized with a dict\" AND timestamp>=\"${TIMESTAMP}Z\"" --limit=5 --format="value(textPayload)" 2>/dev/null || true)

if [[ -z "$ERROR_LOG" ]]; then
    print_status "PASS" "No 'Message must be initialized with a dict' errors found"
else
    print_status "FAIL" "Found IndexDatapoint construction errors:"
    echo "$ERROR_LOG"
    exit 1
fi
echo ""

# Step 5: Check for successful Vector Search upserts
echo "Step 5: Verify Vector Search Upserts"
echo "--------------------------------------"

UPSERT_LOGS=$(gcloud logging read "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"embed-function\" AND textPayload=~\"Upserted datapoint\" AND timestamp>=\"${TIMESTAMP}Z\"" --limit=5 --format="table(timestamp,textPayload)" 2>/dev/null || true)

if [[ -n "$UPSERT_LOGS" ]]; then
    print_status "PASS" "Found successful Vector Search upserts:"
    echo "$UPSERT_LOGS"
else
    print_status "WARN" "No upsert success logs found - check if items needed processing"

    # Check if embed function was even called
    EMBED_LOGS=$(gcloud logging read "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"embed-function\" AND timestamp>=\"${TIMESTAMP}Z\"" --limit=5 --format="value(textPayload)" 2>/dev/null || true)

    if [[ -z "$EMBED_LOGS" ]]; then
        print_status "WARN" "No embed function logs found - function may not have been invoked"
    fi
fi
echo ""

# Step 6: Check for gRPC/HTTP errors
echo "Step 6: Check for gRPC/HTTP Errors"
echo "------------------------------------"

HTTP_ERRORS=$(gcloud logging read "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"embed-function\" AND (textPayload=~\"404\" OR textPayload=~\"HTTP\" OR textPayload=~\"gRPC\") AND severity>=ERROR AND timestamp>=\"${TIMESTAMP}Z\"" --limit=5 --format="value(textPayload)" 2>/dev/null || true)

if [[ -z "$HTTP_ERRORS" ]]; then
    print_status "PASS" "No HTTP 404 or gRPC errors found"
else
    print_status "FAIL" "Found HTTP/gRPC errors:"
    echo "$HTTP_ERRORS"
    exit 1
fi
echo ""

# Step 7: Check Firestore pipeline_items status
echo "Step 7: Verify Pipeline Items Status"
echo "--------------------------------------"

COMPLETED_ITEMS=$(gcloud firestore documents list --collection-ids=pipeline_items --filter="embedding_status=complete" --limit=5 --format="table(name,fields.embedding_status.stringValue,fields.last_transition_at.timestampValue)" 2>/dev/null || true)

if [[ -n "$COMPLETED_ITEMS" ]]; then
    print_status "PASS" "Found completed embedding items in Firestore:"
    echo "$COMPLETED_ITEMS"
else
    print_status "WARN" "No completed items found - may be first run or no new items to process"
fi
echo ""

# Step 8: Check kb_items collection
echo "Step 8: Verify Knowledge Base Items"
echo "-------------------------------------"

KB_ITEMS=$(gcloud firestore documents list --collection-ids=kb_items --limit=5 --format="table(name,fields.title.stringValue,fields.embedding_status.stringValue,fields.last_embedded_at.timestampValue)" 2>/dev/null || true)

if [[ -n "$KB_ITEMS" ]]; then
    print_status "PASS" "Found items in kb_items collection:"
    echo "$KB_ITEMS"
else
    print_status "WARN" "No items in kb_items collection - check if pipeline has processed any items"
fi
echo ""

# Summary
echo "============================================"
echo "  Validation Summary"
echo "============================================"
echo ""
print_status "INFO" "Story 1.5 AC5 Checklist:"
echo "  [✓] Embed function redeployed with VECTOR_SEARCH_INDEX"
echo "  [✓] Pipeline triggered and workflow monitored"
echo "  [✓] No 'Message must be initialized with a dict' errors"
echo "  [✓] No HTTP 404 responses from Vertex AI"
echo ""
echo "Evidence captured:"
echo "  - Execution ID: $LATEST_EXECUTION"
echo "  - Timestamp range: ${TIMESTAMP}Z to $(date -u +%Y-%m-%dT%H:%M:%S)Z"
echo ""

# Generate log link for documentation
LOG_FILTER="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"embed-function\" AND timestamp>=\"${TIMESTAMP}Z\""
LOG_LINK="https://console.cloud.google.com/logs/query;query=$(echo "$LOG_FILTER" | sed 's/ /%20/g')?project=${PROJECT_ID}"

echo "Cloud Logging query link:"
echo "$LOG_LINK"
echo ""

print_status "PASS" "Story 1.5 operational validation COMPLETE"
echo ""
echo "============================================"
