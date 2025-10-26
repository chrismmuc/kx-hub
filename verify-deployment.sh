#!/bin/bash
# Deployment Verification Script

set -e

PROJECT_ID="kx-hub"
REGION="europe-west4"
SCHEDULER_REGION="europe-west3"
PIPELINE_BUCKET="${PROJECT_ID}-pipeline"

echo "============================================"
echo "  Verifying kx-hub Deployment"
echo "============================================"
echo ""

# 1. Check Cloud Function
echo "1. Cloud Function Status:"
echo "   ------------------------"
gcloud functions list --gen2 --region=$REGION --format="table(name,state,updateTime)"
echo ""

# 2. Check Cloud Scheduler
echo "2. Cloud Scheduler Job:"
echo "   ---------------------"
gcloud scheduler jobs list --location=$SCHEDULER_REGION --format="table(name,schedule,state)"
echo ""

# 3. Check Pub/Sub Topics
echo "3. Pub/Sub Topics:"
echo "   ----------------"
gcloud pubsub topics list --format="table(name)" | grep -E "(daily-trigger|daily-ingest)"
echo ""

# 4. Check Storage Buckets
echo "4. Storage Buckets:"
echo "   -----------------"
gcloud storage buckets list --format="table(name,location)" | grep kx-hub
echo ""

# 5. Check Pipeline Manifests
echo "5. Pipeline Manifests:"
echo "   ---------------------"
gcloud storage ls gs://$PIPELINE_BUCKET/manifests 2>/dev/null || echo "   ⚠️  No manifests found yet in gs://$PIPELINE_BUCKET/manifests"
echo ""

# 6. Check Pipeline Item State
echo "6. Pipeline Item State (Firestore):"
echo "   --------------------------------"
gcloud firestore documents list --collection-ids=pipeline_items --limit=5 --format="table(name,fields.embedding_status.stringValue,fields.normalize_status.stringValue,updateTime)" 2>/dev/null || echo "   ⚠️  Unable to list pipeline_items collection"
echo ""

# 7. Check Service Account
echo "7. Service Account:"
echo "   -----------------"
gcloud iam service-accounts list --format="table(email,displayName)" | grep ingest
echo ""

# 8. Check Secret
echo "8. Secret Manager:"
echo "   ----------------"
gcloud secrets describe readwise-api-key --format="table(name,createTime)" 2>/dev/null || echo "   ⚠️  Secret 'readwise-api-key' not found - run ./setup-secrets.sh"
echo ""

# 9. Latest Workflow Execution (batch-pipeline):
echo "9. Workflow Execution:"
echo "   --------------------"
LATEST_EXECUTION=$(gcloud workflows executions list batch-pipeline --location=$REGION --limit=1 --format="value(name)" 2>/dev/null || true)
if [[ -n "$LATEST_EXECUTION" ]]; then
  gcloud workflows executions describe "$LATEST_EXECUTION" --location=$REGION --format="table(name,state,startTime,endTime)" 2>/dev/null || echo "   ⚠️  Unable to describe latest execution"
else
  echo "   ⚠️  No executions found for workflow batch-pipeline"
fi
echo ""

# 10. Embed Function Logs (confirm gRPC upserts succeeding):
echo "10. Embed Function Logs (last 50 entries):"
echo "    ---------------------------------------"
gcloud logging read 'resource.type="cloud_run_revision" severity>=ERROR AND labels."k8s-pod/app"="embed"' --limit=50 --order=desc --format="table(timestamp,severity,textPayload)" 2>/dev/null || \
  gcloud logging read 'resource.type="cloud_function" severity>=ERROR AND resource.labels.function_name="embed"' --limit=50 --order=desc --format="table(timestamp,severity,textPayload)" 2>/dev/null || \
  echo "    ℹ️  No recent embed errors found (or insufficient permissions to query logs)"
echo ""

echo "Reminder: after dependency upgrades run Terraform redeploy + pipeline trigger:"
echo "  cd terraform && terraform plan -out=tfplan && terraform apply tfplan"
echo "  gcloud scheduler jobs run daily-ingest-trigger-job --location=$SCHEDULER_REGION"
echo ""

echo "============================================"
echo "  Deployment Verification Complete!"
echo "============================================"
