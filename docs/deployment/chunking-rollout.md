# Chunking Feature Deployment Checklist

## Pre-Deployment Validation

### 1. Test Suite Validation ✓
- [x] All 63 tests passing locally
- [ ] Run tests in CI/CD pipeline
- [ ] Integration tests pass with real GCP credentials (staging)

**Command**:
```bash
python3 -m unittest discover tests -v
```

**Expected**: All 63 tests pass (24 chunker + 13 normalize + 16 embed + 2 ingest + 8 integration)

### 2. Code Review ✓
- [x] Chunker module implemented (`src/common/chunker.py`)
- [x] Normalize stage updated for chunking
- [x] Embed stage updated for chunk schema
- [x] Tests cover edge cases
- [x] Documentation updated

### 3. Configuration Validation
- [ ] Environment variables set in Cloud Functions
- [ ] Default chunking parameters reviewed
- [ ] Firestore indexes created (if needed)

**Required Environment Variables** (normalize function):
```bash
CHUNK_TARGET_TOKENS=512
CHUNK_MAX_TOKENS=1024
CHUNK_MIN_TOKENS=100
CHUNK_OVERLAP_TOKENS=75
```

**Required Environment Variables** (embed function):
```bash
# Same as above, plus existing vars
GCP_PROJECT=<your-project>
GCP_REGION=europe-west4
MARKDOWN_BUCKET=<bucket-name>
PIPELINE_BUCKET=<bucket-name>
```

## Deployment Steps

### Phase 1: Backup & Preparation (Day 0)

#### 1.1 Export Current Data (Optional)
If you need a backup of existing data before wiping:

```bash
# Export kb_items collection
gcloud firestore export gs://your-backup-bucket/firestore-backup-$(date +%Y%m%d) \
    --collection-ids=kb_items

# Export pipeline_items collection
gcloud firestore export gs://your-backup-bucket/firestore-backup-$(date +%Y%m%d) \
    --collection-ids=pipeline_items
```

**Note**: Current implementation has no data recovery strategy. Backup is for reference only.

#### 1.2 Review Current State
```bash
# Check current kb_items count (should be ~271 documents)
gcloud firestore databases documents list \
    --collection=kb_items \
    --limit=1 \
    | grep "name:" | wc -l

# Check current pipeline_items count
gcloud firestore databases documents list \
    --collection=pipeline_items \
    --limit=1 \
    | grep "name:" | wc -l
```

#### 1.3 Notify Users (If Applicable)
If this is a shared system, notify users of downtime window:
- Expected downtime: ~1 hour (data wipe + pipeline re-run)
- Impact: Search unavailable during rebuild
- Timeline: [Specify date/time]

### Phase 2: Data Wipe (Day 0)

#### 2.1 Run Wipe Script
```bash
cd /Users/christian/dev/kx-hub
./scripts/wipe_and_reset.sh
```

**What it does**:
1. Deletes all kb_items documents
2. Deletes all pipeline_items documents
3. Removes markdown files from Cloud Storage
4. Clears pipeline manifests
5. **Preserves**: Raw JSON data in Cloud Storage

**Verification**:
```bash
# Confirm kb_items is empty
gcloud firestore databases documents list --collection=kb_items --limit=1
# Should return: (empty)

# Confirm pipeline_items is empty
gcloud firestore databases documents list --collection=pipeline_items --limit=1
# Should return: (empty)
```

### Phase 3: Deploy Updated Functions (Day 0)

#### 3.1 Deploy Normalize Function
```bash
cd src/normalize
gcloud functions deploy normalize \
    --runtime python311 \
    --trigger-http \
    --entry-point normalize_handler \
    --region europe-west4 \
    --memory 512MB \
    --timeout 540s \
    --set-env-vars CHUNK_TARGET_TOKENS=512,CHUNK_MAX_TOKENS=1024,CHUNK_MIN_TOKENS=100,CHUNK_OVERLAP_TOKENS=75,MARKDOWN_BUCKET=<bucket>,PIPELINE_BUCKET=<bucket>,PROJECT_ID=<project>
```

**Verification**:
```bash
# Test deployment
curl -X POST https://<region>-<project>.cloudfunctions.net/normalize \
    -H "Content-Type: application/json" \
    -d '{"run_id": "test"}'

# Should return 404 (manifest not found) - this is expected for test run
```

#### 3.2 Deploy Embed Function
```bash
cd src/embed
gcloud functions deploy embed \
    --runtime python311 \
    --trigger-http \
    --entry-point embed \
    --region europe-west4 \
    --memory 512MB \
    --timeout 540s \
    --set-env-vars CHUNK_TARGET_TOKENS=512,CHUNK_MAX_TOKENS=1024,GCP_PROJECT=<project>,GCP_REGION=europe-west4,MARKDOWN_BUCKET=<bucket>,PIPELINE_BUCKET=<bucket>
```

**Verification**:
```bash
# Test deployment
curl -X POST https://<region>-<project>.cloudfunctions.net/embed \
    -H "Content-Type: application/json" \
    -d '{"run_id": "test"}'

# Should return 404 (manifest not found) - this is expected for test run
```

#### 3.3 Verify Dependencies
Both functions should have `tiktoken==0.5.2` in requirements.txt:

```bash
# Check normalize requirements
cat src/normalize/requirements.txt | grep tiktoken
# Should output: tiktoken==0.5.2

# Check embed requirements
cat src/embed/requirements.txt | grep tiktoken
# Should output: tiktoken==0.5.2
```

### Phase 4: Pipeline Re-Run (Day 0)

#### 4.1 Trigger Full Pipeline
Since raw JSON is preserved, re-run the pipeline to rebuild chunks:

```bash
# Option 1: Using Cloud Workflows
gcloud workflows execute batch-pipeline \
    --location=europe-west4 \
    --data='{"message": "chunking-migration"}'

# Option 2: Manual trigger (if no workflow)
# 1. Trigger ingest function to create new manifest
# 2. Normalize will process and create chunks
# 3. Embed will process chunks
```

#### 4.2 Monitor Progress
**Normalize Stage**:
```bash
gcloud functions logs read normalize \
    --region=europe-west4 \
    --limit=50 \
    | grep "Split"
```

Expected output:
```
Split 41094950 into 3 chunks
Split 41094951 into 7 chunks
...
```

**Embed Stage**:
```bash
gcloud functions logs read embed \
    --region=europe-west4 \
    --limit=50 \
    | grep "Storing embedding"
```

Expected output:
```
Storing embedding vector with 768 dimensions for 41094950-chunk-000
Storing embedding vector with 768 dimensions for 41094950-chunk-001
...
```

#### 4.3 Verify Chunk Creation
```bash
# Check kb_items count (should be ~1,355 chunks, ~5× original doc count)
gcloud firestore databases documents list \
    --collection=kb_items \
    | grep "name:" | wc -l

# Sample a chunk document
gcloud firestore databases documents get \
    kb_items/<first-chunk-id>
```

Expected fields:
- `chunk_id`: e.g., "41094950-chunk-000"
- `parent_doc_id`: e.g., "41094950"
- `chunk_index`: 0
- `total_chunks`: e.g., 3
- `content`: Full chunk text
- `embedding`: Vector with 768 dimensions
- `token_count`: e.g., 512

### Phase 5: Validation (Day 1)

#### 5.1 Data Quality Checks
```bash
# 1. Verify chunk distribution
gcloud logging read \
    'resource.type="cloud_function" AND resource.labels.function_name="normalize" AND "Split"' \
    --limit=100 \
    --format=json \
    | jq '.[] | .textPayload' \
    | grep "Split"

# 2. Verify no errors
gcloud logging read \
    'resource.type="cloud_function" AND severity="ERROR"' \
    --limit=50

# 3. Check embedding success rate
gcloud logging read \
    'resource.type="cloud_function" AND resource.labels.function_name="embed" AND "Storing embedding"' \
    --limit=100 \
    | wc -l
# Should match expected chunk count
```

#### 5.2 Search Quality Test
Create a test query function or use Firestore console to test vector search:

```python
# Test query (run in Cloud Shell or local with credentials)
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector

db = firestore.Client()
collection = db.collection('kb_items')

# Example: Find nearest neighbors
query_vector = Vector([0.1] * 768)  # Replace with actual query embedding
results = collection.where(
    filter=FieldFilter("embedding", "ARRAY_CONTAINS_ANY", query_vector)
).limit(5).stream()

for doc in results:
    data = doc.to_dict()
    print(f"Chunk: {data['chunk_id']}")
    print(f"Title: {data['title']}")
    print(f"Content preview: {data['content'][:100]}...")
    print("---")
```

#### 5.3 Cost Validation
Monitor for first few days:

```bash
# Check Cloud Function invocations
gcloud logging read \
    'resource.type="cloud_function"' \
    --freshness=1d \
    | grep "Function execution" | wc -l

# Expected: ~1,626 invocations (271 normalize + 1,355 embed)
```

Check Vertex AI API usage in GCP Console → Vertex AI → Quotas & System Limits

### Phase 6: Monitoring Setup (Day 2-7)

#### 6.1 Set Up Alerts
Create Cloud Monitoring alerts for:

1. **High Error Rate**:
   - Condition: Error rate > 5% for any function
   - Action: Email/Slack notification

2. **Chunk Count Anomaly**:
   - Condition: Avg chunks/doc > 10
   - Action: Investigation required

3. **Cost Overrun**:
   - Condition: Daily embedding cost > $0.05
   - Action: Review document count

#### 6.2 Weekly Review
For first month, review weekly:
- [ ] Total chunks created vs expected
- [ ] Average chunk size (should be ~512 tokens)
- [ ] Search query performance
- [ ] Monthly cost tracking
- [ ] Error logs

**Reference**: See `docs/architecture/chunking-monitoring.md` for detailed metrics

## Rollback Procedure

If critical issues are discovered:

### Option 1: Restore from Backup (If Taken)
```bash
# Import from backup
gcloud firestore import gs://your-backup-bucket/firestore-backup-<date>
```

**Warning**: This restores OLD schema (document-level). Will need to re-deploy old functions.

### Option 2: Emergency Fix & Re-run
1. Fix the bug in code
2. Re-deploy affected function(s)
3. Run wipe script again
4. Re-trigger pipeline

**Downtime**: ~1 hour

### Option 3: Partial Rollback (Freeze State)
1. Stop pipeline triggers (disable Cloud Scheduler)
2. Fix issues
3. Test with subset of documents
4. Resume pipeline

## Success Criteria

Deployment is considered successful when:

- [x] All 63 tests pass
- [ ] Pipeline completes without errors
- [ ] ~1,355 chunks created in kb_items (5× doc count)
- [ ] Average chunk size: 400-600 tokens
- [ ] No error rate > 1%
- [ ] Search returns chunk-level results with content
- [ ] Monthly cost < $2.00
- [ ] Query latency < 100ms (test with sample queries)

## Post-Deployment

### Week 1
- Monitor error logs daily
- Validate chunk distribution matches expectations
- Test search quality with real queries
- Review cost metrics

### Week 2-4
- Collect user feedback (if applicable)
- Fine-tune chunk parameters if needed
- Document any issues/learnings
- Update monitoring dashboards

### Month 2+
- Review monthly cost trends
- Optimize chunk sizes if needed
- Consider future enhancements (semantic clustering, etc.)

## Contacts & Support

- **Technical Issues**: Review `docs/architecture/chunking-monitoring.md`
- **Cost Questions**: See `docs/prd/6-configuration.md`
- **Code Changes**: Story 1.6 in `docs/stories/1.6.story.md`

---

**Document Version**: 1.0
**Last Updated**: 2024-10-29
**Status**: Ready for Deployment
