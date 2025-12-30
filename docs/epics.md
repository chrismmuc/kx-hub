# Epics - kx-hub

**Last Updated:** 2025-12-30

---

## Epic 1: Core Pipeline & Infrastructure ✅

**Goal:** Serverless batch pipeline to ingest, embed, and store Readwise highlights with semantic search.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 1.1 | Daily Readwise API ingest → GCS | ✅ Done |
| 1.2 | JSON → Markdown normalization | ✅ Done |
| 1.3 | Vertex AI embeddings → Firestore | ✅ Done |
| 1.4 | Delta manifests & resume controls | ✅ Done |
| 1.5 | Migrate to Firestore vector search (99% cost reduction) | ✅ Done |
| 1.6 | Intelligent chunking (273 docs → 813 chunks) | ✅ Done |
| 1.7 | MCP Server for Claude Desktop | ✅ Done |

---

## Epic 2: Knowledge Cards & Clustering ✅

**Goal:** AI-powered summaries and automatic topic clustering.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 2.1 | Knowledge card generation (Gemini Flash) | ✅ Done |
| 2.2 | UMAP + HDBSCAN clustering (38 clusters) | ✅ Done |
| 2.6 | MCP tools for cards & clusters | ✅ Done |
| 2.7 | URL link storage & backfill | ✅ Done |

---

## Epic 3: Remote Access & Recommendations ✅

**Goal:** Multi-device access and personalized reading recommendations.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 3.1 | Cloud Run MCP deployment | ✅ Done |
| 3.1.1 | OAuth 2.1 for Claude Mobile/Web | ✅ Done |
| 3.4 | Cluster relationship discovery | ✅ Done |
| 3.5 | AI reading recommendations (Tavily) | ✅ Done |

---

## Epic 4: Knowledge Graph 🚧

**Goal:** Entity & relation extraction for multi-hop queries and contradiction detection.

**Status:** In Progress

| Story | Description | Status |
|-------|-------------|--------|
| 4.1 | Entity extraction from chunks | 📋 Planned |
| 4.2 | Relation extraction between entities | 📋 Planned |
| 4.3 | MCP tools for graph queries | 📋 Planned |
| 4.4 | Proactive knowledge connections | 📋 Planned |

**Next Step:** Story 4.1 - Run entity type discovery on sample chunks

---

## Backlog

See [backlog.md](backlog.md) for future ideas:
- Email digests
- Reader article integration
- Blogging engine
- MCP tool consolidation
