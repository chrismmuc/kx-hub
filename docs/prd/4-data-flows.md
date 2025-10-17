# 4. Data Flows

## Batch Processing Pipeline (daily)
1) Ingest (Readwise/Reader APIs) → **Cloud Storage (raw)**
2) Normalize → **Cloud Storage (markdown)** (+ Frontmatter)
3) Embed & Store (Vertex AI `gemini-embedding-001`) → **Vertex AI Vector Search** + **Firestore metadata**
4) Cluster & Link → **Firestore links** + **Cloud Storage graph.json**
5) Summaries & Synthesis (Vertex AI `Gemini 2.5 Flash`) → **Cloud Storage /content/cards**
6) Export → **GitHub** (Commit/PR)
7) Weekly Digest → **SendGrid Email**

## On-Demand Query Flow (User-initiated)
8) User Query (CLI/API) → **Cloud Function Query Handler**
9) Query Embedding (Vertex AI `gemini-embedding-001`) → **Vertex AI Vector Search**
10) Ranked Results → **Return**: Articles/highlights with context + Knowledge Cards
