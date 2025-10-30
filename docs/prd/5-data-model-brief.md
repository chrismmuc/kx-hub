# 5. Data Model (Brief)
**Firestore `kb_items`** (Chunk-Level Storage)
- Document ID = `chunk_id` (e.g., `41094950-chunk-003`)
- **Chunk Fields**: `chunk_id`, `parent_doc_id`, `chunk_index`, `total_chunks`, `token_count`, `overlap_start`, `overlap_end`
- **Parent Metadata**: `title`, `author`, `url`, `tags[]`, `created_at`, `updated_at`
- **Content & Embedding**: `content` (full chunk text), `embedding` (768-dim Vector), `content_hash`
- **Status**: `embedding_status`, `last_embedded_at`, `last_run_id`, `last_error`
- **Clustering**: `cluster_id[]`, `similar_ids[]`, `scores[]`

**Firestore `pipeline_items`** (Per-Chunk Pipeline Tracking)
- Document ID = `chunk_id` or `user_book_id` (parent doc tracking)
- **Chunk Tracking**: `item_id` (chunk_id), `user_book_id`, `chunk_index`, `total_chunks`, `chunk_tokens`
- **URIs**: `raw_uri`, `markdown_uri` (per chunk)
- **Status**: `normalize_status` (`pending|processing|complete|failed`), `embedding_status`, `content_hash`
- **Coordination**: `manifest_run_id`, `retry_count`, `last_transition_at`
- Used for delta detection, resume-on-error, and coordinating downstream stages

**Firestore `kb_clusters`**  
- Document ID = cluster_id  
- Fields: label, members[], parent_cluster?, related_clusters[], label_version

**Cloud Storage**
- `/raw/*.json` (ingest output)
- `/pipeline/manifests/{timestamp}.json` (IDs + metadata for each run)
- `/markdown/notes/{chunk_id}.md` (normalized chunk content with frontmatter)
- `/cards/{id}.md`, `/graphs/graph.json`

**Chunking Strategy**
- Documents split into 512-1024 token chunks (tiktoken `cl100k_base` encoding)
- 75-token sliding window overlap between adjacent chunks
- Semantic boundary detection: highlight > paragraph > sentence > token limit
- Each chunk includes parent metadata in frontmatter for context preservation
