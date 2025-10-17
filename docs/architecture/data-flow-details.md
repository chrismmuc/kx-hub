# Data Flow Details

## Batch Pipeline (Cloud Workflows Orchestration)

1. **Ingest**: Pub/Sub (daily 2am) → Cloud Function Ingest → GCS raw JSON
2. **Normalize**: Cloud Workflow → Cloud Function Normalize → GCS Markdown (+ Frontmatter)
3. **Embed & Store**: Cloud Function → Vertex AI Embeddings API → Vertex AI Vector Search + Firestore metadata
4. **Cluster**: Cloud Function Cluster & Link → Firestore + GCS graph.json
5. **Summarize/Synthesize**: Cloud Function (Gemini 2.5 Flash) → GCS knowledge-cards
6. **Export**: Cloud Function Export → GitHub Commit/PR
7. **Digest**: Cloud Function Email (weekly on Mondays) → SendGrid

## Query Flow (Synchronous API)

1. **User Query**: CLI/API → API Gateway → Cloud Function Query Handler
2. **Query Embedding**: Vertex AI `gemini-embedding-001`
3. **Similarity Search**: Vertex AI Vector Search `FindNeighbors`
4. **Context Enrichment**: Fetch Metadata from Firestore, Content from GCS
5. **Response**: JSON with ranked results + context + highlights
   - Response time target: <1s (P95) thanks to managed Vector Search

---
