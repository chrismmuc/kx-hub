# Epics - kx-hub

**Last Updated:** 2025-12-30

---

## Epic 1: Core Pipeline & Infrastructure ✅

**Goal:** Serverless batch pipeline to ingest, embed, and store Readwise highlights with semantic search.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 1.1 | **Daily Readwise Ingest** - Cloud Function pulls new highlights via Readwise API, stores raw JSON in GCS | ✅ Done |
| 1.2 | **Markdown Normalization** - Transform raw JSON into structured markdown with metadata (author, tags, highlights) | ✅ Done |
| 1.3 | **Embedding & Storage** - Generate 768-dim embeddings via Vertex AI, store in Firestore with vector index | ✅ Done |
| 1.4 | **Delta Processing** - Manifest tracking for incremental updates, skip already-processed docs, resume on failure | ✅ Done |
| 1.5 | **Firestore Vector Search** - Migrate from Vertex AI Vector Search to native Firestore (99% cost reduction) | ✅ Done |
| 1.6 | **Smart Chunking** - Split long documents into semantic chunks (273 docs → 813 chunks), preserve context | ✅ Done |
| 1.7 | **MCP Server** - Local Model Context Protocol server for Claude Desktop integration | ✅ Done |

---

## Epic 2: Knowledge Cards & Clustering ✅

**Goal:** AI-powered summaries and automatic topic clustering.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 2.1 | **Knowledge Cards** - Gemini Flash generates summaries, key takeaways, related topics per chunk | ✅ Done |
| 2.2 | **Semantic Clustering** - UMAP dimensionality reduction + HDBSCAN clustering (38 auto-discovered topics) | ✅ Done |
| 2.6 | **MCP Card Tools** - `get_cluster`, `list_clusters`, `search_within_cluster` tools for Claude | ✅ Done |
| 2.7 | **URL Backfill** - Extract and store source URLs from highlights, backfill existing 800+ chunks | ✅ Done |

---

## Epic 3: Remote Access & Recommendations ✅

**Goal:** Multi-device access and personalized reading recommendations.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 3.1 | **Cloud Run Deployment** - Deploy MCP server to Cloud Run with SSE transport for remote access | ✅ Done |
| 3.1.1 | **OAuth 2.1 Authentication** - Secure authentication for Claude Mobile/Web with token refresh | ✅ Done |
| 3.4 | **Cluster Relationships** - Discover and store relationships between topic clusters (cosine similarity) | ✅ Done |
| 3.5 | **Reading Recommendations** - AI-powered article recommendations via Tavily search based on interests | ✅ Done |

---

## Epic 4: Knowledge Graph 🚧

**Goal:** Entity & relation extraction for multi-hop queries and contradiction detection.

**Status:** In Progress

| Story | Description | Status |
|-------|-------------|--------|
| 4.1 | **Entity Extraction** - Extract named entities (people, concepts, technologies) from chunks via LLM | 📋 Planned |
| 4.2 | **Relation Extraction** - Identify relationships between entities (influences, contradicts, related_to) | 📋 Planned |
| 4.3 | **Graph Query Tools** - MCP tools for entity lookup, path finding, neighborhood exploration | 📋 Planned |
| 4.4 | **Proactive Connections** - Surface unexpected connections and contradictions during search | 📋 Planned |

**Next Step:** Story 4.1 - Run entity type discovery on sample chunks

---

## Backlog

See [backlog.md](backlog.md) for future ideas:
- Email digests
- Reader article integration
- Blogging engine
- MCP tool consolidation
