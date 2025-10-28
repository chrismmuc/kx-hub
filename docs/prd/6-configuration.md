# 6. Configuration

## `/config/settings.yml` – Vertex AI & App Configuration

```yaml
vertex_ai:
  project_id: "your-gcp-project-id"
  location: "europe-west4"
  embeddings_model: "gemini-embedding-001"
  generative_model: "gemini-2.5-flash-001"

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
- **Embed function (`src/embed`)**: Requires `google-cloud-firestore>=2.16.0` for native vector storage and `google-cloud-aiplatform>=1.44.0` for Vertex AI embeddings.

## Environment Variables
Core configuration (no Vector Search index needed anymore):
- `GCP_PROJECT`: GCP project ID
- `GCP_REGION`: Region for Cloud Functions (e.g., `europe-west4`)
- `MARKDOWN_BUCKET`: Cloud Storage bucket for normalized markdown
- `PIPELINE_BUCKET`: Cloud Storage bucket for pipeline artifacts
- `PIPELINE_COLLECTION`: Firestore collection for pipeline state (default: `pipeline_items`)

## Estimated Monthly Costs
- **Vertex AI Embeddings** (gemini-embedding-001): ~$0.10 (271 books × 1-2 calls per book)
- **Firestore Vector Search**: ~$0.10 (storage + vector queries)
- **Cloud Functions**: ~$0.50 (ingest, normalize, embed execution)
- **Cloud Storage**: ~$0.10 (markdown, raw JSON storage)
- **Firestore Reads/Writes**: ~$0.10 (pipeline metadata + kb_items)
- **Total**: **~$0.90/month**

✅ **99% cost reduction achieved**: Previously $100+/month with Vertex AI Vector Search → Now ~$0.90/month with Firestore native vectors. Complexity and maintenance effort drastically reduced.
