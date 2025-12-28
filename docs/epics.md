# Epics Breakdown - Personal AI Knowledge Base (kx-hub)

**Project:** kx-hub - Personal AI Knowledge Base (Google Cloud + Vertex AI)

**PRD Version:** V4

**Last Updated:** 2025-12-28

---

## Epic 1: Core Batch Processing Pipeline & Knowledge Base Infrastructure

**Goal:** Build the foundational serverless batch processing pipeline to automatically ingest, process, embed, and store highlights/articles from Readwise/Reader with intelligent chunking and semantic search capabilities.

**Business Value:** Enables daily automated processing of knowledge items with semantic search, clustering, and intelligent document chunking for precise passage-level retrieval.

**Dependencies:** None (foundation epic)

**Estimated Complexity:** High - Core infrastructure with vector search, embedding pipeline, and intelligent chunking

**Status:** Complete

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

**Status:** Done

**Summary:** Generate embeddings using Vertex AI gemini-embedding-001 model and store vectors in Vector Search with metadata in Firestore for semantic search capabilities.

**Key Features:**
- Vertex AI Embeddings API integration (gemini-embedding-001)
- Firestore native vector search (768-dimensional embeddings)
- Metadata storage in kb_items collection
- Rate limiting and retry logic
- Error handling with structured logging

---

### Story 1.4: Pipeline Delta Manifests & Resume Controls

**Status:** Done

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

**Status:** Done

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

**Status:** Done

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

## Epic 2: Enhanced Knowledge Graph & Clustering

**Goal:** Build AI-powered knowledge graph capabilities including automatic knowledge card generation and semantic clustering to organize and surface insights from the knowledge base.

**Business Value:** Enables quick insight scanning through AI-generated summaries and automatic topic clustering for knowledge discovery and synthesis.

**Dependencies:** Epic 1 (Story 1.6 - Intelligent Chunking must be complete with 813+ chunks)

**Estimated Complexity:** Medium - AI generation and clustering algorithms with pipeline integration

**Status:** Complete

---

### Story 2.1: Knowledge Card Generation

**Status:** Done

**Summary:** Generate AI-powered knowledge cards with one-line summaries and key takeaways for all chunks using Gemini 2.5 Flash. Support initial bulk generation (local script) and ongoing pipeline integration (Cloud Function) for new chunks.

**Key Features:**
- **Initial Generation Mode:** Local Python script for bulk card generation
- **Pipeline Integration Mode:** Cloud Function in daily batch pipeline for new chunks
- Gemini 2.5 Flash-based generation (concise summaries + 3-5 actionable takeaways)
- Firestore storage in `kb_items.knowledge_card` field
- Cost: $0.10/month (within budget)

**Success Metrics:**
- ✅ 100% coverage (818/818 chunks have knowledge cards)
- ✅ Concise summaries (<200 characters)
- ✅ Actionable takeaways (3-5 per chunk)
- ✅ Cost ≤$0.10/month
- ✅ Quality validation: ≥80% accuracy (manual spot-check)

---

### Story 2.2: Semantic Clustering with Initial Load & Delta Processing

**Status:** Done

**Summary:** Implement semantic clustering using UMAP + HDBSCAN to automatically group related knowledge chunks into topics. Support two execution modes: initial load (local script) and delta processing (Cloud Function).

**Key Features:**
- **Clustering Algorithm:** UMAP (768D → 5D) + HDBSCAN density-based clustering
- **Initial Load Mode:** Local Python script for bulk cluster assignment
  - Direct Firestore updates (kb_items.cluster_id field)
  - Processes all 823 chunks in batches
  - AI-generated cluster names via Gemini
  - Idempotent: can be re-run to recompute clusters
- **Delta Processing Mode:** Cloud Function integrated into daily batch pipeline
  - Assigns new chunks to nearest existing cluster centroid
  - Triggered by Cloud Workflows after Knowledge Cards step
- **Cluster Storage:**
  - cluster_id array field in kb_items Firestore documents
  - clusters collection with metadata (name, description, size, centroid)
- **Graph Export:** Generate graph.json in Cloud Storage

**Dependencies:** Story 2.1 (Knowledge Cards) - requires chunks with embeddings

**Technical Approach:**
- UMAP for dimensionality reduction (cosine metric)
- HDBSCAN for density-based clustering (min_cluster_size=10)
- AI-generated cluster names via Gemini 2.5 Flash
- Initial load: `python3 -m src.clustering.initial_load`
- Delta processing: Cloud Function `clustering-function`

**Success Metrics:**
- ✅ Initial load successfully clusters all existing chunks (38 clusters found)
- ✅ Delta processing assigns clusters to new chunks in daily pipeline
- ✅ Cluster quality: ≥80% of cluster members are semantically related
- ✅ Graph.json exported to Cloud Storage
- ✅ Cost impact: <$0.10/month

---

### Story 2.6: MCP Server Enhancements - Knowledge Cards & Clusters

**Status:** Done

**Summary:** Extend MCP server to expose knowledge cards and cluster data to Claude Desktop, enabling cluster-based browsing, knowledge card summaries, and enhanced search results.

**Key Features:**
- **Enhanced Search Results:** Include knowledge_card and cluster metadata in all search tool responses
- **Knowledge Card Tools:**
  - `get_knowledge_card` - Get AI summary and takeaways for a specific chunk
  - `search_knowledge_cards` - Semantic search across knowledge card summaries
- **Cluster Discovery Tools:**
  - `list_clusters` - List all clusters with names, descriptions, and sizes
  - `get_cluster` - Get detailed cluster info with member chunks
  - `search_within_cluster` - Semantic search restricted to specific cluster
- **Cluster Resources:**
  - `kxhub://clusters` - Browse all clusters
  - `kxhub://cluster/{cluster_id}` - View specific cluster with chunks
  - `kxhub://cluster/{cluster_id}/cards` - Cluster overview with knowledge cards

**Dependencies:**
- Story 2.1 (Knowledge Cards) - knowledge_card field in Firestore
- Story 2.2 (Semantic Clustering) - cluster_id field and clusters collection
- Story 2.3 (Clustering Consistency) - Optional but recommended for quality

**Technical Approach:**
- Extend existing MCP tools (search_semantic, search_by_metadata, get_related_chunks)
- Add 5 new MCP tools for knowledge cards and clusters
- Add 3 new MCP resources for cluster browsing
- Reuse Firestore client and existing infrastructure
- No breaking changes to existing tools

**Success Metrics:**
- All existing search tools return knowledge_card + cluster data
- 5 new tools added successfully
- Cluster resources browsable in Claude Desktop
- <1 second response time for all new tools (P95)
- Zero cost increase (uses existing Firestore data)

**Business Value:**
- Quick insight scanning via knowledge cards (no need to read full chunks)
- Topic-based knowledge discovery via cluster browsing
- Faster triage of search results with summaries
- Better understanding of knowledge base structure

---

### Story 2.7: URL Link Storage & Backfill

**Status:** Done

**Summary:** Extend Firestore data model to capture and store URL links (book readwise_url, book source_url, highlight readwise_url) from Readwise API. Update pipeline functions to extract and store URLs, extend MCP server to return URLs in results, and create backfill script for existing 825+ chunks.

**Key Features:**
- **Data Model Extension:** Add URL fields to Firestore kb_items schema
  - `readwise_url` - Book review URL from Readwise
  - `source_url` - Original source URL (article/book)
  - `highlight_url` - Individual highlight URL (optional, for traceability)
- **Pipeline Updates:**
  - Modify normalize function to extract URLs from raw JSON
  - Update embed function to store URLs in Firestore
  - Add URL fields to markdown frontmatter for consistency
- **MCP Server Enhancement:** Include URLs in all search tool responses
- **Backfill Script:** Local Python script to populate URLs for existing chunks
  - Read raw JSON from GCS
  - Extract URLs
  - Update Firestore documents in batches
  - Handle missing source_url gracefully (many are null)

**Dependencies:** Story 1.6 (Intelligent Chunking) - requires chunk-level data model

**Technical Approach:**
- Readwise API provides URLs in raw JSON (verified in sample data)
- Add 3 new fields to Firestore schema (string type, indexed for search)
- Reuse existing GCS→Firestore update patterns from Story 1.6
- Backfill script similar to knowledge cards initial_load pattern

**Success Metrics:**
- All new chunks (100%) capture URLs from Readwise API
- Backfill completes for 825+ existing chunks
- MCP search results include clickable URLs
- Zero cost increase (uses existing data)
- <5 minutes execution time for backfill script

**Business Value:**
- Enables traceability back to original Readwise highlights
- Supports "open in Readwise" workflows from Claude Desktop
- Enables future features (web clipping, source verification)
- Closes data model gap identified during usage

---

## Epic 3: Knowledge Graph Enhancement & Optimization

**Goal:** Enhance knowledge graph capabilities with cluster relationship discovery, automated quality maintenance, and graph regeneration to enable concept chaining and maintain cluster quality at scale.

**Business Value:** Enables emergent idea discovery through cluster relationships, prevents cluster drift over time, ensures graph stays current with delta updates, and future-proofs the clustering system for knowledge bases beyond 10,000 chunks.

**Dependencies:** Epic 2 (Story 2.3 - Clustering Consistency Fix must be complete)

**Estimated Complexity:** High - Advanced ML operations, Firestore vector search, Cloud Run jobs, automated drift detection

**Status:** Active Development (Stories 3.1, 3.1.1, 3.4, 3.5 Done)

---

### Story 3.1: Remote MCP Server Deployment

**Status:** Done

**Summary:** Deploy MCP server as a remote service (Cloud Run or Cloud Function) to eliminate local setup requirements and enable access from multiple devices. Currently MCP server runs locally requiring manual Python environment setup on each device.

**Key Features:**
- Remote MCP server deployment (Cloud Run or Cloud Function)
- HTTP endpoint with authentication
- Support for multiple concurrent users
- Zero local setup required
- Access from any device with Claude Desktop

**Dependencies:** Story 2.6 (MCP Enhancements) - requires functional MCP server

**Technical Approach:**
- Deploy existing MCP server code to Cloud Run
- Add authentication layer (API key or OAuth)
- Configure Claude Desktop to use remote endpoint
- Test concurrent access patterns

**Success Metrics:**
- MCP server accessible remotely from any device
- <1 second response time for queries (P95)
- Zero local Python setup required
- Support for 3+ concurrent users
- Cost impact: <$1/month (Cloud Run free tier)

**Business Value:**
- Multi-device access (laptop, desktop, tablet)
- No local Python environment setup
- Simplified onboarding
- Better reliability (always-on service)

---

### Story 3.1.1: OAuth 2.1 + Dynamic Client Registration for Mobile Access

**Status:** Done

**Summary:** Implement OAuth 2.1 authentication with Dynamic Client Registration (RFC 7591) to enable kx-hub MCP server access from Claude Mobile and Claude.ai Web. Claude Mobile requires DCR-compliant OAuth, which Google Cloud OAuth does not support natively. This story builds a lightweight OAuth 2.1 authorization server directly into the Cloud Run MCP server.

**Key Features:**
- **Dynamic Client Registration (RFC 7591):**
  - `POST /register` endpoint for client registration
  - Auto-generate client_id and client_secret
  - Store registrations in Firestore `oauth_clients` collection
  - Support client metadata (redirect_uris, client_name, etc.)
- **OAuth 2.1 Authorization Flow:**
  - `GET /authorize` - Authorization endpoint with user consent
  - `POST /token` - Token exchange endpoint (authorization_code grant)
  - `POST /token` - Refresh token support
  - JWT-based access tokens with expiry
- **Authentication Method:**
  - Single-user setup (you are the only authorized user)
  - Google Sign-In for /authorize endpoint (via Identity Platform)
  - Alternative: Simple password-based auth for personal use
- **Token Management:**
  - JWT signing with keys from Secret Manager
  - Access token expiry (1 hour default)
  - Refresh token expiry (30 days default)
  - Token validation middleware for /sse endpoint
- **Claude Integration:**
  - OAuth callback URL: `https://claude.ai/api/mcp/auth_callback`
  - OAuth client name: `Claude`
  - Supports token refresh for long sessions

**Dependencies:**
- Story 3.1 (Remote MCP Server Deployment) - requires Cloud Run deployment
- Story 2.6 (MCP Enhancements) - requires functional MCP tools

**Technical Approach:**
- **OAuth Library:** `authlib` Python library (OAuth 2.1 + RFC 7591 compliant)
- **Client Storage:** Firestore collection `oauth_clients` with schema:
  ```json
  {
    "client_id": "generated-uuid",
    "client_secret": "hashed-secret",
    "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
    "client_name": "Claude",
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "created_at": "2025-12-20T..."
  }
  ```
- **Token Storage:** Firestore collection `oauth_tokens` for authorization codes and refresh tokens
- **JWT Signing:** RSA keys stored in Secret Manager (`oauth-jwt-private-key`, `oauth-jwt-public-key`)
- **Authorization UI:** Simple HTML form for user consent (served at /authorize)
- **User Authentication:** Google Sign-In via Identity Platform (or password for single-user)
- **Token Validation:** Middleware validates JWT on every /sse request
- **Existing SSE Logic:** No changes to MCP protocol, only adds auth layer

**Implementation Details:**
1. **New Python Modules:**
   - `src/mcp_server/oauth_server.py` - OAuth endpoints (register, authorize, token)
   - `src/mcp_server/oauth_storage.py` - Firestore storage for clients/tokens
   - `src/mcp_server/oauth_middleware.py` - JWT validation middleware
   - `src/mcp_server/oauth_templates.py` - HTML templates for consent UI

2. **Updated Modules:**
   - `src/mcp_server/server_sse.py` - Add OAuth middleware to SSE app
   - `src/mcp_server/main.py` - Register OAuth endpoints alongside /sse

3. **Terraform Updates:**
   - Generate JWT RSA key pair and store in Secret Manager
   - Grant Cloud Run service account access to oauth secrets
   - Add Firestore indexes for oauth_clients and oauth_tokens collections

4. **Environment Variables:**
   - `OAUTH_ISSUER` - Token issuer (e.g., `https://kx-hub-mcp.run.app`)
   - `OAUTH_JWT_PRIVATE_KEY` - Secret Manager reference
   - `OAUTH_JWT_PUBLIC_KEY` - Secret Manager reference
   - `OAUTH_USER_EMAIL` - Authorized user email (for single-user mode)

**Success Metrics:**
- DCR endpoint compliant with RFC 7591 (passes validation)
- Claude.ai Web successfully registers and obtains access token
- Claude Mobile successfully connects to MCP server
- Token refresh works without re-authentication
- <200ms token validation overhead per request (P95)
- Zero authentication failures for valid tokens
- Cost impact: ~$0.05/month (minimal Firestore reads/writes)

**Business Value:**
- ✅ Access kx-hub from Claude Mobile (iPhone/Android)
- ✅ Access kx-hub from Claude.ai Web (any browser)
- ✅ Single sign-in across all devices (token refresh)
- ✅ No dependency on external OAuth providers (Auth0, Okta)
- ✅ 100% Google Cloud native solution
- ✅ Secure, standards-compliant authentication

**Security Considerations:**
- JWT tokens signed with RSA-256 (asymmetric)
- Client secrets hashed with bcrypt before storage
- Refresh tokens one-time use (rotated on each refresh)
- Authorization codes expire after 10 minutes
- Rate limiting on /register and /token endpoints
- HTTPS enforced (Cloud Run default)
- Secret Manager for sensitive keys (never in code/env)

**Testing Strategy:**
- Unit tests for OAuth flows (register, authorize, token, refresh)
- Integration tests with mock Claude client
- Manual testing with Claude.ai Web UI
- Manual testing with Claude Mobile app
- Token expiry and refresh validation
- Security testing (invalid tokens, expired codes, etc.)

---

### Story 3.4: Cluster Relationship Discovery via Vector Search

**Status:** Done

**Summary:** Enable cluster relationship discovery using Firestore native vector search on cluster centroids. Users can discover how different concept clusters relate to each other, enabling concept chaining and emergent idea discovery.

**Key Features:**
- **Firestore Vector Index:** Create vector index on `clusters.centroid` field (768-dim)
- **MCP Tool:** New `get_related_clusters(cluster_id, limit)` tool
- **Distance Measures:** Support COSINE, EUCLIDEAN, DOT_PRODUCT similarity
- **Concept Exploration:** Users traverse cluster relationships to discover emergent patterns
- **Bridge Discovery:** Find how seemingly unrelated clusters connect

**Dependencies:**
- Story 2.2 (Semantic Clustering) - produces cluster centroids
- Story 2.6 (MCP Enhancements) - provides MCP infrastructure

**Technical Approach:**
- **Terraform:** Create Firestore vector index on centroid field
- **MCP Tool:** Implement `get_related_clusters()` using Firestore `find_nearest()`
- **Performance:** 5-10x faster than manual scan (<50ms P95)
- **Cost:** ~$0.01/month (negligible)

**Success Metrics:**
- Vector index created and operational
- MCP tool returns top-K similar clusters in <50ms (P95)
- Related clusters have meaningful conceptual connections (manual validation)
- All distance measures work correctly
- Edge cases handled (invalid IDs, missing centroids)

**Business Value:**
- **Research-backed:** Aligns with modern PKM systems (Heptabase, Mem.ai, Obsidian)
- **Discover patterns:** "Your reading on X connects to Y via Z"
- **Explore knowledge graph:** Navigate from one concept to related concepts
- **Synthesize insights:** Combine ideas from multiple clusters
- **Periodic insights:** "This month's reading formed 3 new concepts that connect to..."

**Example Usage:**
```
User: "What concepts relate to semantic search?"
Claude: Your semantic search notes connect to:
1. Personal Knowledge Management (87% similar)
2. MCP and AI Context (82% similar)
3. Reading Workflows (78% similar)

Emergent pattern: "AI-augmented personal knowledge systems"
```

**Future Enhancements:**
- Phase 2: Multi-hop graph traversal
- Phase 3: Pre-computed relationship caching
- Phase 4: Natural language cluster search

---

### Story 3.5: AI-Powered Reading Recommendations

**Status:** Done

**Summary:** Implement an on-demand MCP tool that generates personalized reading recommendations based on recent reads and top clusters. Uses Tavily Search API with domain whitelisting to find high-quality, recent articles related to the user's knowledge base, with LLM-based quality filtering and deduplication against existing content.

**Key Features:**
- **MCP Tool:** `get_reading_recommendations(scope, days, limit)` - On-demand recommendation generation
- **Scope Options:**
  - `recent` - Recommendations based on last N days of reading
  - `clusters` - Recommendations based on top clusters by size
  - `both` - Union of recent reads and top clusters (default)
- **Quality Assurance:**
  - Dynamic domain whitelist stored in Firestore (configurable)
  - Tavily Search API with `include_domains` filtering
  - Recency filtering (last 30 days of publications)
  - Gemini-based quality scoring (depth assessment, author authority)
  - Deduplication against existing KB (embedding similarity check)
  - Source diversity (max 2 recommendations per domain)
- **Smart Query Generation:**
  - Generate queries from cluster themes + existing takeaways
  - "Beyond what you know" queries to find new content
  - Gap detection for stale-but-important clusters
- **Response Structure:**
  - Title, URL, author, domain, published date
  - Relevance score and recency score
  - Related cluster/article information
  - "Why recommended" explanation linking to user's existing content

**Dependencies:**
- Story 2.6 (MCP Enhancements) - MCP infrastructure
- Story 2.1 (Knowledge Cards) - takeaways for query generation
- Story 2.2 (Semantic Clustering) - cluster themes for recommendations

**Technical Approach:**
- Tavily Search API for AI-native web search (~1000 free queries/month)
- Domain whitelist in Firestore `config/recommendation_domains`
- Gemini 2.0 Flash for quality filtering and explanation generation
- Embedding comparison for KB deduplication
- Processing time: ~25-35 seconds (quality over speed)

**Success Metrics:**
- Recommendations return in <60 seconds
- >80% of recommendations rated "relevant" by user
- Zero duplicate recommendations (already in KB)
- >90% from whitelisted quality domains
- Cost impact: <$0.10/month (free tier Tavily + minimal Gemini)

**Business Value:**
- Proactive knowledge discovery (find articles you'd want to read)
- Stay current on topics you care about
- Quality filtering eliminates noise/clickbait
- Connects new content to existing knowledge structure
- Future: Enable scheduled digest emails

**Configuration (Firestore `config/recommendation_domains`):**
```json
{
  "quality_domains": [
    "martinfowler.com", "infoq.com", "thoughtworks.com",
    "thenewstack.io", "oreilly.com", "acm.org",
    "anthropic.com", "openai.com", "huggingface.co",
    "hbr.org", "mckinsey.com", "heise.de", "golem.de"
  ],
  "excluded_domains": ["medium.com"],
  "last_updated": "2025-12-08"
}
```

**MCP Tool Interface:**
```python
get_reading_recommendations(
    scope: str = "both",      # "recent" | "clusters" | "both"
    days: int = 14,           # lookback for recent reads
    limit: int = 10           # max recommendations
) -> RecommendationResponse

update_recommendation_domains(
    add_domains: List[str] = None,
    remove_domains: List[str] = None
) -> ConfigUpdateResponse
```

---

## Epic 3 Summary

| Story | Description | Status |
|-------|-------------|--------|
| 3.1 | Remote MCP Server Deployment | Done |
| 3.1.1 | OAuth 2.1 + Dynamic Client Registration | Done |
| 3.4 | Cluster Relationship Discovery | Done |
| 3.5 | AI-Powered Reading Recommendations | Done |

---

## Overall Summary

| Epic | Status | Stories |
|------|--------|---------|
| Epic 1: Core Pipeline & Infrastructure | Complete | 7/7 Done |
| Epic 2: Knowledge Graph & Clustering | Complete | 5/5 Done |
| Epic 3: Knowledge Graph Enhancement | Active | 4/4 Done (open stories in backlog) |

---

## Backlog

Open stories and planned epics are tracked in **[backlog.md](backlog.md)**:
- Stories 2.3-2.5: Consistency fixes
- Stories 3.2-3.3, 3.6-3.7: Reclustering, Graph, Email, Reader integration
- Epic 4: MCP Tool Consolidation
- Epic 5: Knowledge Digest & Email Summaries
- Epic 6: AI-Powered Blogging Engine
