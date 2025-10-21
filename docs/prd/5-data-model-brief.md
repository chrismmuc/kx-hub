# 5. Data Model (Brief)
**Firestore `kb_items`**  
- Document ID = item_id  
- Fields: title, url, tags, authors, created_at, updated_at, cluster_id[], similar_ids[], scores[], `content_hash`, `embedding_status`, `last_embedded_at`, `last_error`

**Firestore `pipeline_items`**  
- Document ID = item_id  
- Fields: `raw_uri`, `raw_updated_at`, `markdown_uri`, `normalize_status` (`pending|processing|complete|failed`), `content_hash`, `embedding_status` (`pending|processing|complete|failed`), `retry_count`, `last_transition_at`, `manifest_run_id`  
- Used for delta detection, resume-on-error, and coordinating downstream stages

**Firestore `kb_clusters`**  
- Document ID = cluster_id  
- Fields: label, members[], parent_cluster?, related_clusters[], label_version

**Cloud Storage**  
- `/raw/*.json` (ingest output)  
- `/pipeline/manifests/{timestamp}.json` (IDs + metadata for each run)  
- `/markdown/notes/{id}.md` (normalized content)  
- `/cards/{id}.md`, `/graphs/graph.json`
