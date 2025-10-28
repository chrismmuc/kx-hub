# Overview

A serverless knowledge base system that automates daily ingestion of reading highlights and articles, transforms them into searchable embeddings, and stores them in Firestore with native vector search. Uses Vertex AI for embeddings and Google Cloud for orchestration and storage.

## Current Implementation Status (October 2025)

### ✅ Fully Implemented & Production Ready
- **Story 1.1**: Daily ingest from Readwise/Reader APIs → Cloud Storage (raw JSON)
- **Story 1.2**: JSON normalization to Markdown with YAML frontmatter → Cloud Storage
- **Story 1.3**: Embedding generation via Vertex AI and storage in Firestore with native vector index
- **Story 1.5**: Upgraded to Firestore native vectors (completed 2025-10-26)

### 📋 Not Yet Implemented
- **Story 1.4+**: Clustering, semantic linking, knowledge synthesis, export to GitHub, email digests

### 💰 Cost Optimization
- **Previous approach** (Vertex AI Vector Search): $100+/month
- **Current approach** (Firestore native vectors): ~$0.90/month
- **Savings**: 99% cost reduction

---
