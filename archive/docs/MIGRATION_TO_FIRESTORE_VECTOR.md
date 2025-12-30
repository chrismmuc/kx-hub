# Migration Plan: Vertex AI Vector Search → Firestore Vector Search

**Goal:** Replace expensive Vertex AI Vector Search ($100-547/mo) with Firestore native vector search ($0.10-2/mo)

**Status:** Ready to execute
**Estimated Time:** 4-6 hours
**Cost Savings:** ~99% reduction ($100/mo → $0.10/mo)

---

## Current State

### What We Have:
- ✅ Firestore database (`kb_database`)
- ✅ Firestore collections: `pipeline_items`, `kb_items`
- ✅ Cloud Functions: `ingest`, `normalize`, `embed`
- ✅ Vertex AI embeddings (keep - only $0.10/mo)
- ❌ Vertex AI Vector Search (DELETE - $100/mo)
- ❌ Index endpoint (undeployed)
- ❌ Vector index (exists but expensive)
- ❌ Staging bucket (not needed)

### What Needs to Change:
1. **Terraform:** Remove Vertex AI resources, add Firestore vector index
2. **Embed function:** Store embeddings in Firestore instead of Vertex AI
3. **Query function:** Create new function to search Firestore vectors
4. **Tests:** Update for Firestore implementation
5. **Data:** Re-run pipeline to populate Firestore with vectors

---

## Phase 1: Infrastructure Cleanup (Terraform)

### Step 1.1: Destroy Vertex AI Resources

**Execute these commands:**

```bash
cd terraform

# Destroy Vertex AI Vector Search (stops $100/mo cost immediately)
terraform destroy \
  -target=google_vertex_ai_index_endpoint_deployed_index.kb_deployed_index \
  -target=google_vertex_ai_index_endpoint.kb_index_endpoint \
  -target=google_vertex_ai_index.kb_vector_index \
  -target=google_storage_bucket.vector_search_staging \
  -target=google_storage_bucket_object.initial_embeddings
```

**Confirm when prompted:**
- Type `yes` to confirm destruction
- Wait for completion (~2-3 minutes)

**Expected output:**
```
Destroy complete! Resources: 5 destroyed.
```

**Cost impact:** Costs stop immediately after endpoint is destroyed.

---

### Step 1.2: Update Terraform Configuration

**File:** `terraform/main.tf`

**Changes already made:**
- ✅ Removed Vertex AI index, endpoint, deployed index
- ✅ Removed staging bucket
- ✅ Added Firestore vector index
- ✅ Removed VECTOR_SEARCH_* environment variables from embed function

**Verify changes:**

```bash
git diff terraform/main.tf
```

**You should see:**
- Lines removed: ~70 lines (Vertex AI resources)
- Lines added: ~20 lines (Firestore vector index)

---

### Step 1.3: Apply New Terraform Configuration

```bash
cd terraform

# Review changes
terraform plan

# Apply if everything looks good
terraform apply
```

**Expected resources to be created:**
- `google_firestore_index.kb_items_vector_index` (vector search index)

**Expected changes:**
- `google_cloudfunctions2_function.embed_function` (updated env vars)

---

## Phase 2: Update Embed Function

### Step 2.1: Code Changes to `src/embed/main.py`

**Changes needed:**

#### A. Remove old imports (lines 47-54):
```python
# REMOVE:
from google.cloud.aiplatform_v1.types import IndexDatapoint, UpsertDatapointsRequest
from google.cloud.aiplatform_v1.services.index_service import IndexServiceClient
```

#### B. Add new imports:
```python
# ADD:
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
```

#### C. Remove configuration variables (lines ~99-101):
```python
# REMOVE:
VECTOR_SEARCH_INDEX_ENDPOINT = os.environ.get('VECTOR_SEARCH_INDEX_ENDPOINT')
VECTOR_SEARCH_DEPLOYED_INDEX_ID = os.environ.get('VECTOR_SEARCH_DEPLOYED_INDEX_ID')
VECTOR_SEARCH_INDEX = os.environ.get('VECTOR_SEARCH_INDEX')
```

#### D. Remove functions:
```python
# REMOVE these entire functions:
# - get_index_service_client()
# - _index_resource()
# - upsert_to_vector_search()
# - upsert_batch_to_vector_search()
```

#### E. Replace `write_to_firestore()` function:

**Old function (lines ~392-462):**
```python
def write_to_firestore(metadata: Dict[str, Any], content_hash: str, run_id: str, embedding_status: str) -> bool:
    # ... stores metadata only, no embedding vector
```

**New function:**
```python
def store_embedding_in_firestore(
    item_id: str,
    embedding_vector: List[float],
    metadata: Dict[str, Any],
    content_hash: str,
    run_id: str
) -> bool:
    """
    Store embedding vector directly in Firestore kb_items document.

    Args:
        item_id: Document ID
        embedding_vector: 768-dimensional embedding vector
        metadata: Document metadata from frontmatter
        content_hash: Hash of the markdown content
        run_id: Current pipeline run identifier

    Returns:
        True if successful, False if error occurred
    """
    try:
        db = get_firestore_client()

        created_at_value = _parse_iso_datetime(metadata.get('created_at'))
        updated_at_value = _parse_iso_datetime(metadata.get('updated_at'))

        # Prepare document data with vector
        doc_data = {
            'title': metadata['title'],
            'url': metadata.get('url'),
            'tags': metadata.get('tags', []),
            'authors': [metadata['author']],
            'created_at': created_at_value if created_at_value else firestore.SERVER_TIMESTAMP,
            'updated_at': updated_at_value if updated_at_value else firestore.SERVER_TIMESTAMP,
            'content_hash': content_hash,
            'embedding_status': 'complete',
            'last_embedded_at': firestore.SERVER_TIMESTAMP,
            'last_error': None,
            'last_run_id': run_id,
            'embedding': Vector(embedding_vector),  # NEW: Store vector directly
        }

        # Write to kb_items collection
        doc_ref = db.collection('kb_items').document(item_id)
        doc_ref.set(doc_data, merge=True)

        logger.info(f"Stored embedding for document {item_id} in Firestore")
        return True

    except Exception as e:
        logger.error(f"Failed to store embedding for {item_id}: {e}")
        return False
```

#### F. Update main handler (in `embed()` function, lines ~580-640):

**Find this code:**
```python
# OLD:
upsert_success = upsert_to_vector_search(item_id, embedding, run_id)
if not upsert_success:
    # ... error handling

firestore_success = write_to_firestore(metadata, content_hash, run_id, 'complete')
```

**Replace with:**
```python
# NEW:
firestore_success = store_embedding_in_firestore(
    item_id, embedding, metadata, content_hash, run_id
)
if not firestore_success:
    failed += 1
    update_pipeline_item_status(
        item_id, 'failed',
        error_msg="Firestore write failed",
        retry_count=item_data.get('retry_count', 0) + 1
    )
    continue

vector_upserts += 1
firestore_updates += 1
```

---

### Step 2.2: Simplified Version (Alternative)

**If the above is too complex, I can provide a complete rewritten `src/embed/main.py` file.**

Would you prefer:
- [ ] Step-by-step edits (as above)
- [ ] Complete replacement file (I write the whole file)

---

## Phase 3: Create Query Function

### Step 3.1: Create Query Function

**Create file:** `src/query/main.py`

```python
"""
Cloud Function to query knowledge base using Firestore vector search.
"""

import logging
from typing import Dict, Any, List
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from vertexai.preview.language_models import TextEmbeddingModel
import vertexai
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_firestore_client = None
_embedding_model = None

GCP_PROJECT = os.environ.get('GCP_PROJECT', 'kx-hub')
GCP_REGION = os.environ.get('GCP_REGION', 'europe-west4')


def get_firestore_client():
    """Lazy initialization of Firestore client."""
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT)
        logger.info("Initialized Firestore client")
    return _firestore_client


def get_embedding_model():
    """Lazy initialization of Vertex AI embedding model."""
    global _embedding_model
    if _embedding_model is None:
        vertexai.init(project=GCP_PROJECT, location=GCP_REGION)
        _embedding_model = TextEmbeddingModel.from_pretrained("gemini-embedding-001")
        logger.info("Initialized Vertex AI embedding model")
    return _embedding_model


def generate_query_embedding(query_text: str) -> List[float]:
    """Generate embedding for query text."""
    model = get_embedding_model()
    embeddings = model.get_embeddings([query_text])
    return embeddings[0].values


def search_similar_documents(query_embedding: List[float], limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for similar documents using Firestore vector search.

    Args:
        query_embedding: Query vector embedding
        limit: Maximum number of results to return

    Returns:
        List of matching documents with similarity scores
    """
    db = get_firestore_client()

    # Create vector query
    query_vector = Vector(query_embedding)

    # Find nearest neighbors
    vector_query = db.collection('kb_items').find_nearest(
        vector_field='embedding',
        query_vector=query_vector,
        distance_measure=DistanceMeasure.COSINE,
        limit=limit
    )

    results = []
    for doc in vector_query.stream():
        data = doc.to_dict()
        results.append({
            'id': doc.id,
            'title': data.get('title'),
            'url': data.get('url'),
            'authors': data.get('authors', []),
            'tags': data.get('tags', []),
            'created_at': str(data.get('created_at')) if data.get('created_at') else None,
        })

    return results


def query(request):
    """
    Cloud Function handler for vector search queries.

    Request body:
    {
        "query": "What did I read about vector databases?",
        "limit": 10  // optional
    }

    Response:
    {
        "status": "success",
        "query": "...",
        "results": [...]
    }
    """
    logger.info("Query function triggered")

    request_json = request.get_json(silent=True) or {}
    query_text = request_json.get('query')
    limit = request_json.get('limit', 10)

    if not query_text:
        return {'status': 'error', 'message': 'query parameter is required'}, 400

    try:
        # Generate query embedding
        logger.info(f"Generating embedding for query: {query_text}")
        query_embedding = generate_query_embedding(query_text)

        # Search similar documents
        logger.info(f"Searching for {limit} similar documents")
        results = search_similar_documents(query_embedding, limit=limit)

        logger.info(f"Found {len(results)} results")

        return {
            'status': 'success',
            'query': query_text,
            'count': len(results),
            'results': results
        }, 200

    except Exception as e:
        logger.error(f"Query failed: {e}")
        return {'status': 'error', 'message': str(e)}, 500
```

---

### Step 3.2: Create Query Requirements

**Create file:** `src/query/requirements.txt`

```txt
functions-framework==3.*
google-cloud-firestore>=2.14.0
google-cloud-aiplatform>=1.44.0
```

---

### Step 3.3: Add Query Function to Terraform

**Add to `terraform/main.tf`:**

```hcl
# Query Cloud Function
resource "google_cloudfunctions2_function" "query_function" {
  name        = "query-function"
  location    = var.region
  description = "Query knowledge base using Firestore vector search"

  build_config {
    runtime     = "python311"
    entry_point = "query"
    source {
      storage_source {
        bucket = google_storage_bucket.functions_source.name
        object = google_storage_bucket_object.query_function_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 10
    available_memory      = "512M"
    timeout_seconds       = 60
    service_account_email = google_service_account.query_function_sa.email

    environment_variables = {
      GCP_PROJECT = var.project_id
      GCP_REGION  = var.region
    }
  }
}

# Service account for query function
resource "google_service_account" "query_function_sa" {
  account_id   = "query-function-sa"
  display_name = "Service Account for Query Cloud Function"
}

# Grant query function access to Firestore
resource "google_project_iam_member" "query_sa_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.query_function_sa.email}"
}

# Grant query function access to Vertex AI (for embeddings)
resource "google_project_iam_member" "query_sa_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.query_function_sa.email}"
}

# Allow unauthenticated access (or configure auth as needed)
resource "google_cloud_run_service_iam_member" "query_function_invoker" {
  project  = google_cloudfunctions2_function.query_function.project
  location = google_cloudfunctions2_function.query_function.location
  service  = google_cloudfunctions2_function.query_function.name
  role     = "roles/run.invoker"
  member   = "allUsers"  # Change to specific users for auth
}

# Source code for query function
resource "google_storage_bucket_object" "query_function_source" {
  name   = "query-function-${filemd5("${path.module}/../src/query/main.py")}.zip"
  bucket = google_storage_bucket.functions_source.name
  source = data.archive_file.query_function_source.output_path
}

data "archive_file" "query_function_source" {
  type        = "zip"
  output_path = "/tmp/query-function.zip"
  source_dir  = "${path.module}/../src/query"
}
```

---

## Phase 4: Testing

### Step 4.1: Update Tests

**File:** `tests/test_embed.py`

**Changes needed:**
- Remove tests for `upsert_to_vector_search()`
- Remove tests for `upsert_batch_to_vector_search()`
- Update tests to mock Firestore `Vector` class
- Add tests for `store_embedding_in_firestore()`

**Simplified approach:**
- Run tests to see what breaks
- Fix broken tests one by one

---

### Step 4.2: Run Unit Tests

```bash
# Test embed function
python3 -m unittest tests/test_embed.py -v

# Expected: Some tests will fail (vector search tests)
# Fix them by updating mocks
```

---

## Phase 5: Deployment & Data Migration

### Step 5.1: Deploy Updated Infrastructure

```bash
cd terraform

# Review all changes
terraform plan

# Deploy
terraform apply
```

**Expected changes:**
- Update: `embed-function` (new code)
- Create: `query-function` (new)
- Create: `google_firestore_index.kb_items_vector_index`

---

### Step 5.2: Clear Old Firestore Data (Optional)

**Option A: Keep existing metadata, just add vectors**
```bash
# No action needed - re-running pipeline will update documents
```

**Option B: Fresh start**
```bash
# Delete all kb_items documents
gcloud firestore export gs://kx-hub-backup/backup-$(date +%Y%m%d) \
  --collection-ids=kb_items

# Then delete collection (via console or script)
```

**Recommendation:** Option A (keep existing data)

---

### Step 5.3: Re-run Pipeline to Load Vectors

```bash
# Trigger ingest manually
gcloud scheduler jobs run daily-ingest-trigger-job --location=europe-west3

# Monitor workflow execution
gcloud workflows executions list batch-pipeline \
  --location=europe-west4 \
  --limit=1

# Get execution details
EXEC_ID=$(gcloud workflows executions list batch-pipeline --location=europe-west4 --limit=1 --format="value(name)")
gcloud workflows executions describe $EXEC_ID --location=europe-west4
```

**Expected:**
- Ingest: Fetches 271 books from Readwise
- Normalize: Processes 271 markdown files
- Embed: Generates 271 embeddings and stores in Firestore

**Timeline:** ~5-10 minutes for full pipeline

---

### Step 5.4: Verify Data in Firestore

```bash
# Check that vectors are stored
gcloud firestore documents list --collection-ids=kb_items --limit=3

# Check a specific document
gcloud firestore documents describe \
  kb_items/41094950 \
  --database=kb-database
```

**Expected fields in each document:**
- `title`, `url`, `authors`, `tags`
- `embedding_status`: "complete"
- `embedding`: Vector array (768 dimensions)
- `last_embedded_at`: timestamp

---

### Step 5.5: Test Query Function

```bash
# Get query function URL
QUERY_URL=$(gcloud functions describe query-function \
  --gen2 \
  --region=europe-west4 \
  --format="value(serviceConfig.uri)")

# Test query
curl -X POST "$QUERY_URL" \
  -H "Content-Type: application/json" \
  -d '{"query": "What did I read about vector databases?", "limit": 5}'
```

**Expected response:**
```json
{
  "status": "success",
  "query": "What did I read about vector databases?",
  "count": 5,
  "results": [
    {
      "id": "41094950",
      "title": "Book Title",
      "url": "https://...",
      "authors": ["Author Name"],
      "tags": ["tag1", "tag2"]
    },
    ...
  ]
}
```

---

## Phase 6: Cleanup & Documentation

### Step 6.1: Remove Vertex AI References

**Files to update:**
- `docs/architecture/ai-provider-integration-vertex-ai.md`
- `docs/prd/6-configuration.md`
- `docs/architecture/cost-optimization-scaling.md`

**Update cost estimates:**
```markdown
| Component | Monthly Cost |
|-----------|--------------|
| Embeddings | $0.10 |
| Firestore Vector Search | $0.10 |
| Generative | $1.50 |
| Functions/Storage | $0.50 |
| **Total** | **$2.20** |
```

---

### Step 6.2: Commit Changes

```bash
git add .
git commit -m "$(cat <<'EOF'
feat: migrate from Vertex AI Vector Search to Firestore vector search

Replace expensive Vertex AI Vector Search ($100/mo) with Firestore native
vector search ($0.10/mo) for 99% cost reduction.

Changes:
- Remove Vertex AI index, endpoint, staging bucket from Terraform
- Add Firestore vector index to kb_items collection
- Update embed function to store vectors directly in Firestore
- Create new query function for vector similarity search
- Update documentation with new cost estimates

Cost savings: $100/mo → $0.10/mo (~99% reduction)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Rollback Plan (If Needed)

If something goes wrong:

```bash
# Restore from git
git checkout HEAD~1 terraform/main.tf
git checkout HEAD~1 src/embed/main.py

# Re-apply old Terraform
cd terraform
terraform apply

# Re-run pipeline
gcloud scheduler jobs run daily-ingest-trigger-job --location=europe-west3
```

---

## Success Criteria

- [ ] No Vertex AI Vector Search resources exist
- [ ] Firestore vector index created
- [ ] Embed function stores vectors in Firestore
- [ ] Query function returns relevant results
- [ ] All 271 books have embeddings in Firestore
- [ ] Monthly costs reduced to ~$2/month
- [ ] All tests passing

---

## Estimated Costs

### Before:
- Vertex AI Vector Search: $100-547/mo
- Vertex AI Embeddings: $0.10/mo
- **Total: ~$100/mo**

### After:
- Firestore Vector Search: $0.10/mo (storage + queries)
- Vertex AI Embeddings: $0.10/mo
- **Total: ~$0.20/mo**

**Savings: 99.8%**

---

## Timeline

- Phase 1 (Infrastructure): 30 min
- Phase 2 (Embed function): 1-2 hours
- Phase 3 (Query function): 30 min
- Phase 4 (Testing): 1 hour
- Phase 5 (Deployment): 1 hour
- Phase 6 (Cleanup): 30 min

**Total: 4-6 hours**

---

## Next Steps

Which phase would you like to start with?

1. [ ] Phase 1: Infrastructure cleanup (Terraform)
2. [ ] Phase 2: Update embed function
3. [ ] Phase 3: Create query function
4. [ ] All at once (I'll do everything)

---

**Last Updated:** 2025-10-27
**Status:** Ready to execute
