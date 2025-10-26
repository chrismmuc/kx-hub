# 4. Data Flows

## Batch Processing Pipeline (daily)
1) Ingest (Readwise/Reader APIs) → **Cloud Storage (raw)** + Pub/Sub completion signal **with run manifest** (`pipeline/manifests/{date}.json`)
2) Normalize → Process **only item IDs listed in the manifest**, write markdown to **Cloud Storage (notes/{id}.md)**, record status + `content_hash` in **Firestore `pipeline_items`**
3) Embed & Store (Vertex AI `gemini-embedding-001`) → Pull from `pipeline_items` where `embedding_status != "complete"` → **Vertex AI Vector Search (gRPC `MatchingEngineIndexEndpointServiceClient.upsert_datapoints`)** + **Firestore metadata** (`embedding_status`, `last_embedded_at`) — requires `google-cloud-aiplatform>=1.44` in the embed deployment
4) Cluster & Link → **Firestore links** + **Cloud Storage graph.json**
5) Summaries & Synthesis (Vertex AI `Gemini 2.5 Flash`) → **Cloud Storage /content/cards**
6) Export → **GitHub** (Commit/PR)
7) Weekly Digest → **SendGrid Email**

## On-Demand Query Flow (User-initiated)
8) User Query (CLI/API) → **Cloud Function Query Handler**
9) Query Embedding (Vertex AI `gemini-embedding-001`) → **Vertex AI Vector Search**
10) Ranked Results → **Return**: Articles/highlights with context + Knowledge Cards
