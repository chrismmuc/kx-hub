# 6. Configuration

## `/config/settings.yml` – Vertex AI & App Configuration

```yaml
vertex_ai:
  project_id: "your-gcp-project-id"
  location: "europe-west4"
  embeddings_model: "gemini-embedding-001"
  generative_model: "gemini-2.5-flash-001"

chunking:
  target_tokens: 512       # Target chunk size in tokens
  max_tokens: 1024         # Maximum chunk size (hard limit)
  min_tokens: 100          # Minimum chunk size
  overlap_tokens: 75       # Overlap between adjacent chunks

readwise:
  api_key_secret: "/kx-hub/readwise/api-key" # Path in Google Secret Manager
  sync_interval_hours: 24

github:
  repo: "user/obsidian-vault"
  branch: "main"
  commit_author: "kx-hub-bot"

email:
  provider: "sendgrid"
  api_key_secret: "/kx-hub/sendgrid/api-key"
  from: "noreply@kx-hub.example.com"
  digest_schedule: "0 9 * * MON"  # Mondays 9am
```

## Runtime Dependencies
- **Normalize function (`src/normalize`)**: Requires `tiktoken==0.5.2` for token counting
- **Embed function (`src/embed`)**: Requires `google-cloud-firestore>=2.16.0` for native vector storage, `google-cloud-aiplatform>=1.44.0` for Vertex AI embeddings, and `tiktoken==0.5.2` for token validation

## Environment Variables
Core configuration (no Vector Search index needed anymore):
- `GCP_PROJECT`: GCP project ID
- `GCP_REGION`: Region for Cloud Functions (e.g., `europe-west4`)
- `MARKDOWN_BUCKET`: Cloud Storage bucket for normalized markdown
- `PIPELINE_BUCKET`: Cloud Storage bucket for pipeline artifacts
- `PIPELINE_COLLECTION`: Firestore collection for pipeline state (default: `pipeline_items`)

**Chunking Configuration** (optional, defaults provided):
- `CHUNK_TARGET_TOKENS`: Target chunk size in tokens (default: 512)
- `CHUNK_MAX_TOKENS`: Maximum chunk size (default: 1024)
- `CHUNK_MIN_TOKENS`: Minimum chunk size (default: 100)
- `CHUNK_OVERLAP_TOKENS`: Overlap between chunks (default: 75)

## Estimated Monthly Costs (with Chunking)
- **Vertex AI Embeddings** (gemini-embedding-001): ~$0.50 (271 books → ~1,355 chunks @ 5 chunks/book avg)
- **Firestore Vector Search**: ~$0.20 (storage + vector queries for chunks)
- **Cloud Functions**: ~$0.50 (ingest, normalize with chunking, embed execution)
- **Cloud Storage**: ~$0.10 (chunk markdown, raw JSON storage)
- **Firestore Reads/Writes**: ~$0.10 (pipeline metadata + kb_items per chunk)
- **Total**: **~$1.40/month**

**Cost Impact of Chunking**:
- Embedding cost increase: +$0.40/month (5× more embeddings from chunking)
- Retrieval improvement: Eliminates GCS round trips (~100ms saved per query)
- Search quality: Passage-level granularity vs document-level

✅ **Overall 98.6% cost reduction**: Previously $100+/month with Vertex AI Vector Search → Now ~$1.40/month with Firestore native vectors + chunking. Complexity and maintenance effort drastically reduced.
