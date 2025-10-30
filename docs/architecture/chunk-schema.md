# Chunk Schema Design

## Overview

This document defines the Firestore collections schema for Story 1.6 (Intelligent Document Chunking). The schema supports storing document chunks as individual items with embeddings, while maintaining parent-child relationships for rollup queries and filtering.

---

## Firestore Collections

### 1. `kb_items` Collection

**Purpose:** Store chunk-level knowledge base items with embeddings for vector search.

**Document ID Format:** `{parent_doc_id}-chunk-{chunk_index}`

**Example:** `41094950-chunk-003`

#### Schema (Complete)

```firestore
kb_items/
├── 41094950-chunk-000/
│   ├── # Chunk Identity
│   ├── chunk_id: "41094950-chunk-000"
│   ├── parent_doc_id: "41094950"
│   ├── chunk_index: 0
│   ├── total_chunks: 25
│   │
│   ├── # Parent Document Metadata
│   ├── title: "Thinking, Fast and Slow"
│   ├── author: "Daniel Kahneman"
│   ├── source: "kindle"
│   ├── category: "books"
│   ├── tags: ["psychology", "behavioral-economics", "decision-making"]
│   │
│   ├── # Chunk Content (NEW - eliminates GCS fetch)
│   ├── content: "Full markdown text of this chunk including overlap..."
│   │
│   ├── # Vector Embedding
│   ├── embedding: Vector([0.1234, 0.5678, ..., 0.9012])  # 768 dimensions
│   ├── embedding_model: "gemini-embedding-001"
│   │
│   ├── # Chunk Boundaries & Overlap Tracking
│   ├── chunk_boundaries: {
│   │   ├── start: 0        # Character offset in original document
│   │   ├── end: 2048
│   ├── }
│   ├── overlap_start: 0    # First N chars are overlap from previous
│   ├── overlap_end: 75     # Last N chars overlap into next chunk
│   ├── token_count: 512    # Actual token count (for verification)
│   │
│   ├── # Processing Status
│   ├── embedding_status: "complete"  # complete|pending|failed
│   ├── content_hash: "sha256:abc123..."
│   ├── last_embedded_at: Timestamp(2025-10-27T12:00:00Z)
│   ├── last_error: null
│   ├── retry_count: 0
│   │
│   ├── # Audit Trail
│   ├── created_at: Timestamp(2025-10-27T12:00:00Z)
│   ├── updated_at: Timestamp(2025-10-27T12:00:00Z)
│
├── 41094950-chunk-001/
│   └── [similar structure]
│
└── [more chunks...]
```

#### Field Specifications

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `chunk_id` | string | ✅ | Unique identifier: `{parent_doc_id}-chunk-{index}` |
| `parent_doc_id` | string | ✅ | Reference to original document (user_book_id) |
| `chunk_index` | integer | ✅ | Zero-based position in chunk sequence |
| `total_chunks` | integer | ✅ | Total chunks from parent document |
| `title` | string | ✅ | Parent document title |
| `author` | string | ✅ | Parent document author |
| `source` | string | ✅ | Content source: kindle, evernote, twitter, etc. |
| `category` | string | ✅ | Content category: books, articles, highlights, etc. |
| `tags` | array(string) | ✅ | Array of tags from parent document |
| `content` | string | ✅ | Full chunk text (markdown with overlap) |
| `embedding` | Vector | ✅ | 768-dimensional vector (Firestore native Vector type) |
| `embedding_model` | string | ✅ | Model used: "gemini-embedding-001" |
| `chunk_boundaries` | map | ✅ | {start: int, end: int} - char offsets in original |
| `overlap_start` | integer | ✅ | Char count: overlap shared with previous chunk |
| `overlap_end` | integer | ✅ | Char count: overlap shared with next chunk |
| `token_count` | integer | ✅ | Actual tokens in this chunk (for monitoring) |
| `embedding_status` | string | ✅ | complete\|pending\|failed |
| `content_hash` | string | ✅ | SHA256 hash of content for deduplication |
| `last_embedded_at` | timestamp | ✅ | Last successful embedding timestamp |
| `last_error` | string | ❌ | Error message if embedding_status = failed |
| `retry_count` | integer | ✅ | Number of failed embedding attempts |
| `created_at` | timestamp | ✅ | Document creation timestamp |
| `updated_at` | timestamp | ✅ | Last update timestamp |

#### Index Requirements

```
Composite Indexes:

1. Vector Search Index (REQUIRED)
   Fields: embedding (vector)
   Purpose: Find semantically similar chunks

2. Parent Document Lookup
   Fields: (parent_doc_id, chunk_index)
   Purpose: Retrieve all chunks from single document in order

3. Metadata Filtering
   Fields: (source, category) + (tags)
   Purpose: Filter chunks by content type/category

4. Status Tracking
   Fields: (embedding_status, last_embedded_at DESC)
   Purpose: Find pending/failed embeddings for retries
```

---

### 2. `pipeline_items` Collection

**Purpose:** Track processing status of chunks through the normalize → embed pipeline.

**Document ID Format:** `{parent_doc_id}-chunk-{chunk_index}`

**Example:** `41094950-chunk-003`

#### Schema (Complete)

```firestore
pipeline_items/
├── 41094950-chunk-000/
│   ├── # Item Identity
│   ├── item_id: "41094950-chunk-000"           # For compatibility
│   ├── user_book_id: "41094950"                # Parent document
│   ├── chunk_index: 0
│   ├── total_chunks: 25
│   │
│   ├── # Pipeline URIs
│   ├── raw_uri: "gs://kx-hub-raw-json/41094950.json"
│   ├── raw_updated_at: Timestamp(2025-10-27T10:00:00Z)
│   ├── markdown_uri: "gs://kx-hub-markdown-normalized/41094950-chunk-000.md"
│   ├── markdown_size_bytes: 2048
│   │
│   ├── # Stage Status
│   ├── normalize_status: "complete"            # pending|processing|complete|failed
│   ├── embedding_status: "complete"            # pending|processing|complete|failed
│   │
│   ├── # Content Integrity
│   ├── content_hash: "sha256:xyz789..."
│   ├── manifest_run_id: "20251027-daily-001"
│   │
│   ├── # Retry & Error Handling
│   ├── retry_count: 0
│   ├── max_retries: 3
│   ├── last_error: null
│   ├── last_error_at: null
│   │
│   ├── # State Transitions
│   ├── last_transition_at: Timestamp(2025-10-27T12:00:00Z)
│   │
│   ├── # Chunk-Specific Metadata
│   ├── chunk_tokens: 512
│   ├── chunk_boundaries: {start: 0, end: 2048}
│   ├── parent_metadata: {
│   │   ├── title: "Thinking, Fast and Slow",
│   │   ├── author: "Daniel Kahneman",
│   │   ├── source: "kindle"
│   ├── }
│   │
│   ├── # Audit Trail
│   ├── created_at: Timestamp(2025-10-27T10:00:00Z)
│   ├── updated_at: Timestamp(2025-10-27T12:00:00Z)
│
├── 41094950-chunk-001/
│   └── [similar structure]
│
└── [more chunk processing items...]
```

#### Field Specifications

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `item_id` | string | ✅ | Chunk identifier (compatibility field) |
| `user_book_id` | string | ✅ | Parent document ID |
| `chunk_index` | integer | ✅ | Position in sequence |
| `total_chunks` | integer | ✅ | Total chunks from document |
| `raw_uri` | string | ✅ | GCS path to raw JSON |
| `raw_updated_at` | timestamp | ✅ | Raw data update time |
| `markdown_uri` | string | ✅ | GCS path to chunk markdown file |
| `markdown_size_bytes` | integer | ✅ | Size of markdown file |
| `normalize_status` | string | ✅ | pending\|processing\|complete\|failed |
| `embedding_status` | string | ✅ | pending\|processing\|complete\|failed |
| `content_hash` | string | ✅ | SHA256 of content (for dedup) |
| `manifest_run_id` | string | ✅ | Ingest pipeline run identifier |
| `retry_count` | integer | ✅ | Number of failed attempts |
| `max_retries` | integer | ✅ | Max retry limit (default: 3) |
| `last_error` | string | ❌ | Error message on failure |
| `last_error_at` | timestamp | ❌ | When last error occurred |
| `last_transition_at` | timestamp | ✅ | Status change timestamp |
| `chunk_tokens` | integer | ✅ | Token count (for cost tracking) |
| `chunk_boundaries` | map | ✅ | {start: int, end: int} |
| `parent_metadata` | map | ✅ | {title, author, source, ...} |
| `created_at` | timestamp | ✅ | Item creation timestamp |
| `updated_at` | timestamp | ✅ | Last update timestamp |

#### Index Requirements

```
Composite Indexes:

1. Pipeline Status Tracking
   Fields: (normalize_status, last_transition_at DESC)
   Purpose: Find pending items for normalize stage

2. Embed Queue
   Fields: (embedding_status, last_transition_at DESC)
   Purpose: Find pending items for embed stage

3. Parent Document Chunks
   Fields: (user_book_id, chunk_index)
   Purpose: Retrieve all chunks of a document in order

4. Retry Management
   Fields: (embedding_status, retry_count DESC)
   Purpose: Find items needing retry (failed + retries < max)
```

---

## Pipeline Flow with Chunks

```
Readwise API
    ↓
[1. Ingest] → raw JSON: gs://kx-hub-raw-json/41094950.json
    ↓
Create pipeline_items entries (one per chunk)
    ├── 41094950-chunk-000: {normalize_status: pending, embedding_status: pending}
    ├── 41094950-chunk-001: {normalize_status: pending, embedding_status: pending}
    └── ... (25 chunks)
    ↓
[2. Normalize] → for each pipeline_item:
    ├── Read raw JSON
    ├── Split into chunks (with overlap)
    ├── Write each chunk: gs://kx-hub-markdown-normalized/41094950-chunk-000.md
    ├── Update pipeline_item: {normalize_status: complete}
    └── Create manifest entry for each chunk
    ↓
[3. Embed] → for each pipeline_item where embedding_status = pending:
    ├── Read markdown from GCS
    ├── Parse frontmatter + content
    ├── Generate embedding via Vertex AI
    ├── Create kb_items document with embedding + content
    ├── Update pipeline_item: {embedding_status: complete}
    └── NO GCS fetch on retrieval (content in kb_items)
    ↓
[4. Query] → User semantic search:
    ├── Generate query embedding
    ├── Vector search on kb_items
    ├── Returns: {chunk_id, parent_doc_id, title, author, content, ...}
    └── Single Firestore query (no secondary GCS fetch)
```

---

## Querying Examples

### Query: Find all chunks from a document

```python
from google.cloud import firestore

db = firestore.Client()

# Retrieve all chunks of document in order
chunks = db.collection('kb_items')\
    .where('parent_doc_id', '==', '41094950')\
    .order_by('chunk_index')\
    .stream()

for chunk in chunks:
    print(f"Chunk {chunk.get('chunk_index')}: {chunk.get('content')}")
```

### Query: Semantic search with vector

```python
from google.cloud.firestore_v1.vector import Vector

# Vector search for semantically similar chunks
results = db.collection('kb_items')\
    .find_nearest(
        vector_field='embedding',
        query_vector=Vector([...]),  # User's query embedding
        limit=10,
        distance_measure=DistanceMeasure.COSINE
    ).stream()

for result in results:
    print(f"{result.get('title')}: {result.get('content')[:100]}...")
```

### Query: Filter by metadata

```python
# Find psychology-related chunks
chunks = db.collection('kb_items')\
    .where('category', '==', 'books')\
    .where('tags', 'array-contains', 'psychology')\
    .order_by('updated_at', direction=firestore.Query.DESCENDING)\
    .stream()
```

---

## Configuration Updates

Add to `docs/prd/6-configuration.md`:

```yaml
Chunking Configuration:
  CHUNK_TARGET_TOKENS: 512          # Ideal chunk size
  CHUNK_MAX_TOKENS: 1024            # Hard split limit
  CHUNK_MIN_SIZE_TOKENS: 100        # Minimum viable chunk
  CHUNK_OVERLAP_TOKENS: 75          # Context overlap tokens

Firestore Collections:
  kb_items:
    description: "Chunk-level knowledge base items with embeddings"
    document_id_format: "{parent_doc_id}-chunk-{chunk_index}"
    vector_index: "on embedding field"

  pipeline_items:
    description: "Processing pipeline state tracking"
    document_id_format: "{parent_doc_id}-chunk-{chunk_index}"
    purpose: "Idempotency, error recovery, monitoring"

Cloud Storage:
  gs://kx-hub-raw-json/
    → {user_book_id}.json

  gs://kx-hub-markdown-normalized/
    → {user_book_id}-chunk-{index}.md

  gs://kx-hub-pipeline/
    → manifests/{timestamp}.json
```

---

## Future Enhancements

1. **Chunk Relationships Table** - Cross-chunk similarity tracking
2. **Read History** - Track which chunks users have viewed
3. **Annotations** - User highlights/notes on specific chunks
4. **Dynamic Chunk Size** - Adaptive sizing based on content type
5. **Multi-Level Hierarchy** - Document → Section → Chunk nesting

---
