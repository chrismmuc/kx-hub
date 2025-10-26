# AI Provider Integration (Vertex AI)

## Architecture

All AI functionality is handled via Vertex AI. No abstraction layer for multiple providers is necessary, which significantly simplifies the architecture.

- **Embeddings**: `gemini-embedding-001` model via Vertex AI API.
- **Generative Models**: `Gemini 2.5 Flash` for summaries and synthesis.
- **Vector Search**: Vertex AI Vector Search for storage and similarity search, using the gRPC `MatchingEngineIndexEndpointServiceClient.upsert_datapoints` API (requires `google-cloud-aiplatform>=1.44` in Cloud Function runtimes).

## Secrets Management

```
Google Secret Manager:
├── /kx-hub/gcp/service-account-key
├── /kx-hub/readwise/api-key
└── /kx-hub/github/token
```

---
