# Epics - kx-hub

**Last Updated:** 2026-01-07

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

## Epic 2: Knowledge Cards ✅

**Goal:** AI-powered summaries per chunk.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 2.1 | **Knowledge Cards** - Gemini Flash generates summaries, key takeaways, related topics per chunk | ✅ Done |
| 2.7 | **URL Backfill** - Extract and store source URLs from highlights, backfill existing 800+ chunks | ✅ Done |

*Note: Clustering (Stories 2.2, 2.6) deprecated in Epic 4.4 - replaced by source-based organization.*

---

## Epic 3: Remote Access & Recommendations ✅

**Goal:** Multi-device access and personalized reading recommendations.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 3.1 | **Cloud Run Deployment** - Deploy MCP server to Cloud Run with SSE transport for remote access | ✅ Done |
| 3.1.1 | **OAuth 2.1 Authentication** - Secure authentication for Claude Mobile/Web with token refresh | ✅ Done |
| 3.4 | **Source Relationships** - Discover and store relationships between sources (moved to Epic 4) | ✅ Done |
| 3.5 | **Reading Recommendations** - AI-powered article recommendations via Tavily search based on interests | ✅ Done |

---

## Epic 4: Source-Based Knowledge Graph ✅

**Goal:** Build connected knowledge network based on Sources (books/articles) with explicit relationships. Replace cluster abstraction.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 4.1 | **Source Extraction & Migration** - Extract sources from chunks, create sources collection | ✅ Done |
| 4.2 | **Cross-Source Relationship Extraction** - LLM-based relationship discovery between sources | ✅ Done |
| 4.3 | **MCP Source Tools** - `list_sources`, `get_source`, `search_within_source`, `get_contradictions` | ✅ Done |
| 4.4 | **Cluster Deprecation** - Remove all cluster logic from MCP server, use sources instead | ✅ Done |
| 4.5 | **Incremental Updates** - Auto-find relationships when new chunks ingested (pipeline integration) | ✅ Done |

**Key Changes:**
- Clusters replaced by Sources (books, articles) as first-class entities
- Explicit typed relationships (`extends`, `supports`, `contradicts`)
- 18 MCP tools (down from 22, removed cluster tools)
- Automatic relationship extraction in daily pipeline

See [epic4.md](epic4.md) for full details.

---

## Epic 6: AI-Powered Blogging Engine 🚧

**Goal:** Transform KB content into polished blog articles with AI assistance.

**Status:** In Progress

| Story | Description | Status |
|-------|-------------|--------|
| 6.1 | **Blog Idea Extraction** - `suggest_article_ideas`, `list_ideas`, `accept_idea`, `reject_idea` | ✅ Done |
| 6.2 | **Article Outline Generation** - Structure and outline creation | Planned |
| 6.3 | **AI-Assisted Drafting** - Section expansion and refinement | Planned |
| 6.4 | **Article Development Log** - Session tracking and history | Planned |
| 6.5 | **Article Series** - Multi-part article management | Planned |
| 6.6 | **Obsidian Export** - Markdown export with frontmatter | Planned |
| 6.7 | **Claude Code Integration** - Direct editing support | Planned |

See [epics/epic6.md](epics/epic6.md) for full details.

---

## Epic 7: Async MCP Interface ✅

**Goal:** Replace long-running synchronous MCP tools with async job pattern to prevent client timeouts.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 7.1 | **Async Recommendations** - `recommendations`, `recommendations_history` via Cloud Tasks | ✅ Done |
| 7.2 | **Simplified Interface** - Config-based defaults, optional `topic` override | ✅ Done |
| 7.3 | **Async Article Ideas** - Apply pattern to article ideas if needed | Optional |

See [epics/epic7.md](epics/epic7.md) for full details.

---

## Backlog

See [backlog.md](backlog.md) for future ideas:
- Email digests
- Reader article integration
- MCP tool consolidation
