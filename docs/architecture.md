# Architecture – Google Cloud + Vertex AI (MVP)

## Overview

The system uses Google Cloud Serverless components and Vertex AI to create a simple, scalable, and cost-effective solution for processing and querying knowledge data.

---

## System Architecture

### Batch Processing Pipeline (Daily)

```mermaid
flowchart TB
  RW[Readwise API] -->|pull| F1[Cloud Function: Ingest]
  RR[Reader API]   -->|pull| F1

  F1 --> GCS_RAW[(Cloud Storage: raw-json)]
  F1 --> PS_TOPIC[Pub/Sub Topic: daily-ingest]

  PS_TOPIC --> WF[Cloud Workflows: Pipeline]

  WF --> F2[Cloud Function: Normalize/Markdown]
  F2 --> GCS_MD[(Cloud Storage: markdown-normalized)]

  WF --> F3[Cloud Function: Embed & Store]
  F3 -->|gemini-embedding-001| V_EMB[Vertex AI: Embeddings API]
  V_EMB --> F3
  F3 --> V_VS[Vertex AI Vector Search]
  F3 --> FS_META[(Firestore: metadata/links)]

  WF --> F4[Cloud Function: Cluster & Link]
  F4 --> FS_META
  F4 --> GCS_GRAPH[(Cloud Storage: graph.json)]

  WF --> F5[Cloud Function: Summaries & Synthesis]
  F5 -->|Gemini 2.5 Flash| V_GEN[Vertex AI: Generative AI]
  F5 --> GCS_KC[(Cloud Storage: knowledge-cards md)]

  WF --> F6[Cloud Function: Export → GitHub]
  GCS_MD --> F6
  GCS_KC --> F6
  GCS_GRAPH --> F6

  WF --> F7[Cloud Function: Email Digest]
  FS_META --> F7
  F7 --> SENDGRID[SendGrid API]
```

### On-Demand Query Flow (User-Initiated)

```mermaid
flowchart LR
  USER[User CLI/API] -->|Natural Language Query| APIGW[API Gateway]
  APIGW --> F8[Cloud Function: Query Handler]

  F8 -->|Embed Query| V_EMB[Vertex AI: Embeddings API]
  V_EMB --> F8

  F8 -->|Find Neighbors| V_VS[Vertex AI Vector Search]
  V_VS --> F8

  F8 -->|Fetch Metadata| FS_META[(Firestore)]
  FS_META --> F8

  F8 -->|Fetch Content| GCS_MD[(Cloud Storage: markdown)]
  F8 -->|Fetch Cards| GCS_KC[(Cloud Storage: knowledge-cards)]

  F8 -->|Ranked Results| USER
```

---

## AI Provider Integration (Vertex AI)

### Architecture

All AI functionality is handled via Vertex AI. No abstraction layer for multiple providers is necessary, which significantly simplifies the architecture.

- **Embeddings**: `gemini-embedding-001` model via Vertex AI API.
- **Generative Models**: `Gemini 2.5 Flash` for summaries and synthesis.
- **Vector Search**: Vertex AI Vector Search for storage and similarity search.

### Secrets Management

```
Google Secret Manager:
├── /kx-hub/gcp/service-account-key
├── /kx-hub/readwise/api-key
└── /kx-hub/github/token
```

---

## Data Flow Details

### Batch Pipeline (Cloud Workflows Orchestration)

1. **Ingest**: Pub/Sub (daily 2am) → Cloud Function Ingest → GCS raw JSON
2. **Normalize**: Cloud Workflow → Cloud Function Normalize → GCS Markdown (+ Frontmatter)
3. **Embed & Store**: Cloud Function → Vertex AI Embeddings API → Vertex AI Vector Search + Firestore metadata
4. **Cluster**: Cloud Function Cluster & Link → Firestore + GCS graph.json
5. **Summarize/Synthesize**: Cloud Function (Gemini 2.5 Flash) → GCS knowledge-cards
6. **Export**: Cloud Function Export → GitHub Commit/PR
7. **Digest**: Cloud Function Email (weekly on Mondays) → SendGrid

### Query Flow (Synchronous API)

1. **User Query**: CLI/API → API Gateway → Cloud Function Query Handler
2. **Query Embedding**: Vertex AI `gemini-embedding-001`
3. **Similarity Search**: Vertex AI Vector Search `FindNeighbors`
4. **Context Enrichment**: Fetch Metadata from Firestore, Content from GCS
5. **Response**: JSON with ranked results + context + highlights
   - Response time target: <1s (P95) thanks to managed Vector Search

---

## Cost Optimization & Scaling

### Strategy

The use of Vertex AI and Google Cloud Serverless components significantly simplifies the cost structure and scaling.

- **No Manual Scaling**: Vertex AI Vector Search and Cloud Functions scale automatically.
- **Pay-per-Use**: Costs are only incurred for actual usage.
- **Simplified MLOps**: No need to manage custom models or indexes.

### Estimated Monthly Costs

| Component | Service | Monthly (estimated) |
|-----------|-------|-----------|
| Embeddings | Vertex AI Embeddings API | $0.10 |
| Vector Search | Vertex AI Vector Search | $3.00 (base index) |
| Generative | Vertex AI (Gemini 2.5 Flash) | $1.50 |
| Functions/Storage | Google Cloud | $0.50 |
| **Total** | | **~$5.10** |

✅ **Goal achieved: ~$5/month. The cost is comparable, but the complexity is drastically reduced.**

---

## Scaling & Upgrade Paths

The architecture is designed to be scalable from the ground up.

- **MVP**: The current architecture is already the scalable solution. Vertex AI Vector Search can handle billions of vectors with low latency.
- **Phase 2**: For extremely high demands, the number of replicas in the Vector Search Index can be increased to further boost throughput.
- **Phase 3**: Not required. The need to migrate to another Vector DB solution is eliminated.

---

## Security & Best Practices

### IAM Least-Privilege
- Each Cloud Function has a dedicated Service Account with minimal permissions.
- GCS: Bucket policies restrict access per Service Account.
- Secret Manager: Strict access control on secrets.

### Monitoring & Alerting
- Cloud Monitoring:
  - Function execution times
  - API Gateway latency
  - Vector Search query latency
  - Cost budgets
- Cloud Logging for all services.

### Deployment
- Terraform for Infrastructure as Code
- CI/CD via GitHub Actions

---