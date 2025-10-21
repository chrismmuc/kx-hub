# System Architecture

## Batch Processing Pipeline (Daily)

```mermaid
flowchart TB
  RW[Readwise API] -->|pull| F1[Cloud Function: Ingest]
  RR[Reader API]   -->|pull| F1

  F1 --> GCS_RAW[(Cloud Storage: raw-json)]
  F1 --> PS_TOPIC[Pub/Sub Topic: daily-ingest]
  F1 --> MANIFEST[(Cloud Storage: pipeline manifests)]

  PS_TOPIC --> WF[Cloud Workflows: Pipeline]

  WF --> F2[Cloud Function: Normalize/Markdown]
  F2 --> GCS_MD[(Cloud Storage: markdown-normalized)]
  F2 --> PIPESTATE[(Firestore: pipeline_items)]

  WF --> F3[Cloud Function: Embed & Store]
  F3 -->|gemini-embedding-001| V_EMB[Vertex AI: Embeddings API]
  V_EMB --> F3
  F3 --> V_VS[Vertex AI Vector Search]
  F3 --> FS_META[(Firestore: metadata/links)]
  F3 --> PIPESTATE

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

The manifest bucket (`pipeline manifests`) captures each ingest run’s item IDs and timestamps, while the shared `pipeline_items` Firestore collection records `normalize_status`, `embedding_status`, hashes, and retry metadata so downstream stages can resume safely and avoid duplicate work.

## On-Demand Query Flow (User-Initiated)

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
