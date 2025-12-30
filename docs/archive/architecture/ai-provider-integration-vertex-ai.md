# AI Provider Integration (Vertex AI)

## Architecture

All AI functionality is handled via Vertex AI. No abstraction layer for multiple providers is necessary, which significantly simplifies the architecture.

- **Embeddings**: `gemini-embedding-001` model via Vertex AI API (~$0.10/month for 271 books).
- **Generative Models**: `Gemini 2.5 Flash` for summaries and synthesis (future feature).
- **Vector Storage**: Firestore native vector search (stores embeddings in `kb_items` collection with vector index on `embedding` field) instead of Vertex AI Vector Search (~$0.10/month vs. $100+/month previously).

## Secrets Management

```
Google Secret Manager:
├── /kx-hub/gcp/service-account-key
├── /kx-hub/readwise/api-key
└── /kx-hub/github/token
```

---
