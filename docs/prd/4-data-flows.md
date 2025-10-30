# 4. Data Flows

## Batch Processing Pipeline (daily)
1) Ingest (Readwise/Reader APIs) → **Cloud Storage (raw)** + Pub/Sub completion signal **with run manifest** (`pipeline/manifests/{date}.json`)
2) Normalize → Process **only item IDs listed in the manifest**, **split documents into semantic chunks** (512-1024 tokens with 75-token overlap), write chunk markdown to **Cloud Storage (notes/{chunk_id}.md)**, record chunk status + `content_hash` in **Firestore `pipeline_items`**
3) Embed & Store (Vertex AI `gemini-embedding-001`) → Pull from `pipeline_items` where `embedding_status != "complete"` → Store embeddings in **Firestore `kb_items` with native Vector type** (includes full chunk content for retrieval) + update metadata (`embedding_status`, `last_embedded_at`)
4) Cluster & Link → **Firestore links** + **Cloud Storage graph.json**
5) Summaries & Synthesis (Vertex AI `Gemini 2.5 Flash`) → **Cloud Storage /content/cards**
6) Export → **GitHub** (Commit/PR)
7) Weekly Digest → **SendGrid Email**

## On-Demand Query Flow (User-initiated)
8) User Query (CLI/API) → **Cloud Function Query Handler**
9) Query Embedding (Vertex AI `gemini-embedding-001`) → **Firestore Vector Search** (FIND_NEAREST query)
10) Ranked Results → **Return**: Passage-level chunks with full content + parent metadata + Knowledge Cards
