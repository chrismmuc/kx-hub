# Epics Breakdown - Personal AI Knowledge Base (kx-hub)

**Project:** kx-hub - Personal AI Knowledge Base (Google Cloud + Vertex AI)

**PRD Version:** V3

**Last Updated:** 2025-10-30

---

## Epic 1: Core Batch Processing Pipeline & Knowledge Base Infrastructure

**Goal:** Build the foundational serverless batch processing pipeline to automatically ingest, process, embed, and store highlights/articles from Readwise/Reader with intelligent chunking and semantic search capabilities.

**Business Value:** Enables daily automated processing of knowledge items with semantic search, clustering, and intelligent document chunking for precise passage-level retrieval.

**Dependencies:** None (foundation epic)

**Estimated Complexity:** High - Core infrastructure with vector search, embedding pipeline, and intelligent chunking

**Status:** Active Development (Stories 1.1-1.6 Complete, 1.7 Ready)

---

### Story 1.1: Daily Ingest of New Articles/Highlights via API

**Status:** Done

**Summary:** Cloud Function triggered daily by Cloud Scheduler to fetch new highlights/articles from Readwise API and store raw JSON in Cloud Storage, publishing to Pub/Sub to trigger the next pipeline step.

**Key Features:**
- Cloud Scheduler + Pub/Sub trigger (daily at 2am)
- Readwise API integration with delta sync
- Raw JSON storage in GCS bucket
- Secure API key management via Google Secret Manager
- Error handling with retry logic and rate limiting

---

### Story 1.2: Transform Raw JSON to Normalized Markdown

**Status:** Done

**Summary:** Cloud Workflow orchestrates normalization function to transform raw JSON into structured Markdown files with YAML frontmatter for consistent processing.

**Key Features:**
- Cloud Workflows orchestration via Pub/Sub trigger
- JSON → Markdown transformation with frontmatter
- GCS storage of normalized markdown files
- Comprehensive error handling and logging
- 271 books successfully processed

---

### Story 1.3: Embed & Store to Vertex AI Vector Search + Firestore

**Status:** Ready for Review

**Summary:** Generate embeddings using Vertex AI gemini-embedding-001 model and store vectors in Vector Search with metadata in Firestore for semantic search capabilities.

**Key Features:**
- Vertex AI Embeddings API integration (gemini-embedding-001)
- Firestore native vector search (768-dimensional embeddings)
- Metadata storage in kb_items collection
- Rate limiting and retry logic
- Error handling with structured logging

---

### Story 1.4: Pipeline Delta Manifests & Resume Controls

**Status:** Ready for Review

**Summary:** Implement manifest-based delta processing and resume controls to ensure the pipeline processes only new/changed items and can safely recover from failures without duplicates.

**Key Features:**
- Run manifest generation with SHA-256 checksums
- Firestore pipeline_items tracking with status management
- Idempotent Vector Search upserts
- 15-minute timeout handling for stuck processing entries
- Replay detection and skip logic

---

### Story 1.5: Migrate to Firestore Native Vector Search

**Status:** Done

**Summary:** Migrate from Vertex AI Vector Search (~$100/month) to Firestore native vector search (~$0.10/month) to achieve 99% cost reduction while maintaining functionality.

**Key Features:**
- Remove Vertex AI Vector Search dependencies
- Direct Firestore storage using native Vector type
- 768-dimensional embedding storage
- 99% cost reduction ($100/month → $0.10/month)
- Simplified architecture

---

### Story 1.6: Intelligent Document Chunking with Overlap

**Status:** Completed

**Summary:** Implement intelligent document chunking with semantic boundary detection and overlap to enable passage-level search results instead of whole-document retrieval, with full content storage in Firestore for single-query retrieval.

**Key Features:**
- Configurable chunk sizes (512-1024 tokens)
- Sliding window with 75-token overlap
- Semantic boundary detection (highlight → paragraph → sentence → token limit)
- Full chunk content storage in Firestore (eliminates GCS fetch)
- 273 documents → 813 chunks
- Single-query retrieval (<100ms response time)
- Cost: $1.40/month total (98.6% reduction from previous $100+/month)

**Success Metrics:**
- ✅ 813 chunks created from 273 documents (avg 3 chunks/doc)
- ✅ 100% embedding success rate
- ✅ <100ms retrieval latency (single Firestore query)
- ✅ $1.40/month total system cost
- ✅ Passage-level search results with full content

---

### Story 1.7: MCP Server for Conversational Knowledge Base Access

**Status:** Ready

**Summary:** Build a local MCP (Model Context Protocol) server to expose the knowledge base to Claude Desktop for conversational queries, eliminating context switching and enabling natural language access to 813 semantically-searchable chunks.

**Key Features:**
- MCP stdio server for Claude Desktop integration
- Firestore resource exposure (kxhub://chunk/{chunk_id} URIs)
- Semantic search tool (gemini-embedding-001 query embeddings)
- Metadata search tools (by author, tag, source)
- Related chunks discovery
- Pre-defined prompt templates
- Local server (zero hosting cost)
- <1s query response time (P95)

**Dependencies:** Story 1.6 (Intelligent Document Chunking) must be complete with 813 chunks deployed

**Technical Approach:**
- Local Python MCP server using stdio transport
- Reuses Vertex AI gemini-embedding-001 for query embeddings (768 dimensions)
- Leverages Firestore native vector search FIND_NEAREST queries
- No breaking changes - additive functionality
- Estimated cost impact: +$0.10-0.20/month for query embeddings

**Success Metrics:**
- MCP server connects to Claude Desktop
- Semantic search returns relevant results in <1 second
- 4 tools functional (search_semantic, search_by_metadata, get_related_chunks, get_stats)
- Zero infrastructure cost (local server)
- Conversational knowledge access without context switching

---

## Future Epics (Beyond MVP)

See [PRD Section 8: Future Features & Backlog](./prd.md#8-future-features--backlog) for planned enhancements:

- **Epic 2:** Enhanced Knowledge Graph & Clustering
  - Semantic clustering and topic detection
  - Knowledge cards generation (TL;DR + takeaways)
  - Idea synthesis per cluster/topic

- **Epic 3:** Export & Distribution
  - GitHub export (Markdown + graph.json)
  - Obsidian vault sync
  - Weekly email digest

- **Epic 4:** Advanced Features
  - DayOne Journal import
  - Current article recommendations
  - Multi-source integration

---

## Epic Summary

| Epic | Stories | Status | Completion |
|------|---------|--------|------------|
| Epic 1: Core Pipeline & KB Infrastructure | 7 | Active | 6/7 Complete (85%) |
| Epic 2: Knowledge Graph (Future) | TBD | Planned | 0% |
| Epic 3: Export & Distribution (Future) | TBD | Planned | 0% |
| Epic 4: Advanced Features (Future) | TBD | Backlog | 0% |

---

## Notes

- **Architecture:** Serverless Google Cloud (Cloud Functions, Workflows, Firestore, Vertex AI)
- **Cost Target:** <$5/month (Current: $1.40/month - **72% under budget**)
- **Success Criteria:** All PRD section 7 metrics met or exceeded
- **Next Milestone:** Complete Story 1.7 (MCP Server) to enable conversational knowledge access
