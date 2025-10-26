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
- **Embed function (`src/embed`)**: Pin `google-cloud-aiplatform>=1.44` to access the Vertex AI gRPC Matching Engine client for Vector Search upserts.

## Estimated Monthly Costs
- **Embeddings & Vector Search**: ~$3.10 (Vertex AI)
- **Generative Models**: ~$1.50 (Vertex AI Gemini 2.5 Flash)
- **Cloud Functions, Storage, Firestore**: ~$0.50
- **Total**: **~$5.10/month**
✅ **Goal: ~$5/month achieved. Complexity and maintenance effort are drastically reduced compared to the V2 architecture.**
