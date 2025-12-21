# Epics Breakdown - Personal AI Knowledge Base (kx-hub)

**Project:** kx-hub - Personal AI Knowledge Base (Google Cloud + Vertex AI)

**PRD Version:** V4

**Last Updated:** 2025-12-11

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

## Epic 2: Enhanced Knowledge Graph & Clustering

**Goal:** Build AI-powered knowledge graph capabilities including automatic knowledge card generation and semantic clustering to organize and surface insights from the knowledge base.

**Business Value:** Enables quick insight scanning through AI-generated summaries and automatic topic clustering for knowledge discovery and synthesis.

**Dependencies:** Epic 1 (Story 1.6 - Intelligent Chunking must be complete with 813+ chunks)

**Estimated Complexity:** Medium - AI generation and clustering algorithms with pipeline integration

**Status:** Active Development (Stories 2.1-2.2 Complete, Stories 2.3-2.6 Planned)

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

**Status:** In Progress

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

### Story 2.3: Clustering Consistency Fix

**Status:** Planned

**Summary:** Fix inconsistency between initial UMAP-based clustering and delta centroid-based assignment by implementing unified UMAP transform for both processes. Store UMAP model in Cloud Storage and use 5D UMAP-reduced centroids for consistent cluster assignments.

**Key Features:**
- Store UMAP model in Cloud Storage after initial clustering
- Update cluster centroids to use 5D UMAP-reduced space (not 768D)
- Implement `transform_and_assign()` method for delta clustering
- Ensure both initial and delta use same 5D embedding space
- UMAP model versioning for future re-clustering compatibility

**Dependencies:** Story 2.2 (Semantic Clustering) - requires UMAP clustering implemented

**Technical Approach:**
- Save UMAP model to `gs://kx-hub-pipeline/models/umap_model.pkl`
- Store both 768D (reference) and 5D (active) centroids in clusters collection
- Cloud Function loads UMAP model and transforms new chunks to 5D before assignment
- Cluster ID mapping preserves continuity when re-clustering

**Success Metrics:**
- UMAP model saved to Cloud Storage
- Centroids stored in 5D UMAP space
- Delta clustering uses UMAP transform (not raw 768D)
- Cluster assignments consistent between initial and delta
- Performance: Delta processing <1.4 seconds (5x faster than before)

**Business Value:**
- Prevents cluster quality degradation over time
- Ensures accurate cluster assignments for new chunks
- Maintains cluster coherence as KB grows
- Better user experience with consistent clustering

---

### Story 2.4: Knowledge Cards Consistency Check

**Status:** Planned

**Summary:** Verify that Knowledge Cards generation is consistent between initial load and delta processing. Investigate if prompts, models, and parameters are identical to prevent inconsistencies similar to clustering (Story 2.3).

**Key Features:**
- Compare AI prompts between initial script and Cloud Function
- Verify Gemini model versions match (gemini-2.5-flash)
- Check temperature, top_p, and max_tokens consistency
- Validate code reuse patterns (shared generator module)

**Dependencies:** Story 2.1 (Knowledge Cards) - requires both modes implemented

**Technical Approach:**
- Code review: `src/knowledge_cards/` vs `functions/knowledge_cards/`
- Verify shared module usage (`KnowledgeCardGenerator` class)
- Test consistency: generate card in both modes, compare results
- Document any inconsistencies and create fixes if needed

**Success Metrics:**
- Prompts identical between initial and delta
- Model versions match
- Parameters consistent
- Code duplication eliminated (shared module)
- Documentation updated with findings

---

### Story 2.5: Graph Regeneration & Storage Permissions

**Status:** Planned

**Summary:** Enable graph regeneration after delta clustering and fix storage permissions for graph.json uploads. Currently graph.json becomes stale after new chunks are added, and service account lacks storage.objects.create permission.

**Key Features:**
- **Graph Regeneration:** Add graph regeneration to delta clustering Cloud Function
  - Smart caching: Only regenerate if cluster membership changed significantly
  - Async generation: Don't block delta processing
- **Permission Fix:** Grant service account `storage.objects.create` permission
  - Update IAM role bindings in Terraform
  - Test graph.json upload to `gs://kx-hub-pipeline/graphs/`

**Dependencies:** Story 2.2 (Semantic Clustering) - requires clustering implemented

**Technical Approach:**
- Update `functions/clustering/main.py` to call graph generator
- Add threshold check: regenerate if >5% of chunks assigned to new clusters
- Update Terraform `terraform/iam.tf` with storage permissions
- Test with manual delta clustering run

**Success Metrics:**
- Graph.json regenerated after delta clustering
- Service account has storage.objects.create permission
- Graph upload succeeds without 403 errors
- Graph stays up-to-date with latest cluster memberships
- Performance impact: <2 seconds additional latency

---

### Story 2.6: MCP Server Enhancements - Knowledge Cards & Clusters

**Status:** Drafted

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

**Status:** Backlog

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

**Status:** Active Development (Stories 3.3-3.4 Ready, Story 3.2 Planned, Story 3.1 Backlog)

---

### Story 3.1: Remote MCP Server Deployment

**Status:** Backlog

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

**Status:** Ready

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

### Story 3.2: Periodic Reclustering with Drift Detection

**Status:** Planned

**Summary:** Implement automated cluster quality monitoring and periodic re-clustering to prevent cluster drift over time. Includes drift detection triggers, Cloud Run re-clustering job, cluster ID mapping for continuity, and UMAP model versioning.

**Key Features:**
- **Drift Detection System:**
  - Weekly Cloud Scheduler job to monitor cluster quality
  - Trigger conditions: 90+ days, 20%+ corpus growth, or silhouette score <0.55
  - Manual override flag for forced re-clustering
- **Re-clustering Cloud Run Job:**
  - Full corpus re-clustering with UMAP re-training
  - Cluster ID mapping (preserves IDs with >70% overlap)
  - Automated metadata updates and UMAP model versioning
  - Handles up to 50,000 chunks in <10 minutes
- **Quality Preservation:**
  - Maintains cluster coherence as KB grows
  - Prevents semantic drift from frozen UMAP models
  - Enables cluster splitting/merging based on corpus evolution

**Dependencies:** Story 2.3 (UMAP-consistent delta clustering)

**Technical Approach:**
- Cloud Scheduler for weekly drift checks
- Cloud Run job for long-running re-clustering (up to 60 minutes)
- Firestore metadata collection for tracking state
- Cluster ID mapping algorithm for continuity
- UMAP model versioning in Cloud Storage

**Success Metrics:**
- Re-clustering completes in <5 minutes for 5,000 chunks
- >90% of cluster IDs preserved between re-clusterings (70%+ overlap)
- Cluster silhouette score maintained >0.60 over time
- Zero manual intervention required for drift management
- Cost impact: <$1/year (quarterly re-clustering)

---

### Story 3.3: Graph Regeneration on Delta Clustering

**Status:** Backlog

**Summary:** Add smart graph regeneration to delta clustering Cloud Function to keep graph.json current after new chunks are added. Currently graph.json becomes stale after delta updates, requiring manual regeneration.

**Key Features:**
- **Smart Regeneration:** Only regenerate if data change exceeds threshold (>1% new chunks)
- **Non-blocking:** Regeneration doesn't delay delta processing
- **Threshold-based:** Skip regeneration for small updates (<1% changes)
- **Environment Configurable:** `GRAPH_REGEN_THRESHOLD` variable
- **Future Enhancement:** Incremental updates instead of full regeneration

**Dependencies:**
- Story 2.5 (Storage Permissions) - prerequisite for graph.json uploads
- Story 2.3 (Clustering Consistency) - produces graph.json

**Technical Approach:**
- Add `should_regenerate_graph()` function with 1% default threshold
- Call graph generation after delta clustering completes
- Upload to `gs://kx-hub-pipeline/graphs/graph.json`
- Non-blocking error handling (graph failure doesn't fail clustering)

**Success Metrics:**
- Graph regeneration skipped for <1% changes (most runs)
- Graph regenerated for ≥1% changes (~1-2 times/week)
- Regeneration completes in <5 seconds for current dataset
- Monitoring for graph regeneration failures
- Zero impact on delta clustering performance

**Business Value:**
- Future visualization features will show current cluster structure
- No manual intervention required to keep graph updated
- Scales to large datasets with smart thresholding

**Why Deferred:**
- No current visualization feature using graph.json
- Implement when Epic 3 visualization is actually needed
- Estimated effort: 4-6 hours for Phase 1 implementation

---

### Story 3.4: Cluster Relationship Discovery via Vector Search

**Status:** Ready for Implementation

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

**Status:** Backlog

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

### Story 3.6: Email Digest for Reading Recommendations

**Status:** Backlog

**Summary:** Implement a scheduled email digest that sends personalized reading recommendations to the user on a configurable schedule (weekly/daily). Extends Story 3.5's recommendation engine with email delivery via SendGrid, allowing users to receive curated article suggestions without actively querying Claude.

**Key Features:**
- **Scheduled Delivery:** Cloud Scheduler triggers weekly (default: Monday 8am) or daily
- **Email Template:** HTML email with recommendation cards, "why recommended" explanations
- **SendGrid Integration:** Transactional email delivery via SendGrid API
- **Digest Configuration:** Firestore config for schedule, recipient, preferences
- **MCP Tool:** `configure_email_digest(enabled, schedule, email)` for setup
- **Unsubscribe:** One-click unsubscribe link in emails

**Dependencies:**
- Story 3.5 (Reading Recommendations) - provides recommendation engine
- SendGrid account and API key

**Technical Approach:**
- Cloud Function triggered by Cloud Scheduler
- Reuses `get_reading_recommendations()` logic from Story 3.5
- SendGrid API for email delivery (~100 free emails/day)
- HTML email template with responsive design
- Configuration in Firestore `config/email_digest`

**Success Metrics:**
- Email delivered within 5 minutes of scheduled time
- >90% email delivery rate (SendGrid metrics)
- Responsive HTML renders correctly in Gmail, Outlook, Apple Mail
- Cost impact: <$0.05/month (SendGrid free tier)

**Business Value:**
- Passive knowledge discovery (recommendations come to you)
- Stay informed without active querying
- Weekly digest promotes consistent learning habits
- Future: Personalized digest based on reading patterns

---

### Story 3.7: Save Recommendations to Readwise Reader

**Status:** Backlog

**Summary:** Enable users to save recommended articles directly to their Readwise Reader library via MCP tool, creating a seamless "discover → save → read → highlight" workflow. Recommendations from Story 3.5 can be sent to Reader with one command, closing the loop between discovery and consumption.

**Key Features:**
- **MCP Tool:** `save_to_reader(url, tags)` - Save single article to Readwise Reader
- **Batch Save:** `save_recommendations_to_reader(recommendation_ids, tags)` - Save multiple recommendations
- **Auto-Tagging:** Automatically tag saved articles with source cluster name
- **Readwise Reader API:** Integration with Reader's "save URL" endpoint
- **Confirmation:** Returns saved article metadata (title, estimated read time)
- **Duplicate Detection:** Check if URL already exists in Reader before saving

**Dependencies:**
- Story 3.5 (Reading Recommendations) - provides recommendations to save
- Readwise Reader API access (uses existing Readwise API key)

**Technical Approach:**
- Readwise Reader API: `POST /api/v3/save/` endpoint
- Reuse existing Readwise API key from Secret Manager
- Add `reader_client.py` for Reader-specific API calls
- Auto-tag with cluster name for organization
- Store saved URLs in Firestore to prevent duplicates

**Success Metrics:**
- Articles save to Reader in <3 seconds
- 100% success rate for valid URLs
- Auto-tags appear correctly in Reader
- No duplicate saves (URL deduplication)
- Cost impact: $0 (uses existing Readwise subscription)

**Business Value:**
- Complete workflow: Discover → Save → Read → Highlight → Back to KB
- Reduces friction between recommendation and consumption
- Articles saved to Reader get highlighted and return to kx-hub
- Creates virtuous knowledge cycle

**MCP Tool Interface:**
```python
save_to_reader(
    url: str,                    # Article URL to save
    tags: List[str] = None,      # Optional tags (auto-adds cluster tag)
    notes: str = None            # Optional note to add
) -> SavedArticleResponse

save_recommendations_to_reader(
    recommendation_ids: List[str],  # IDs from get_reading_recommendations
    add_tags: List[str] = None      # Additional tags for all
) -> BatchSaveResponse
```

**Example Usage:**
```
User: "What should I read next?"
Claude: [Shows 5 recommendations]

User: "Save the first two to Reader"
Claude: [Calls save_recommendations_to_reader]
       "Saved 2 articles to Readwise Reader:
        - 'Platform Engineering in 2025' (tagged: platform-engineering, kx-recommended)
        - 'AI Agents Best Practices' (tagged: ai-agents, kx-recommended)"
```

---

## Epic 4: MCP Tool Consolidation

**Goal:** Reduce MCP tool count from 21 to 8 through smart consolidation, decreasing token overhead by ~60% and improving AI tool selection accuracy.

**Problem Statement:**
- kx-hub currently exposes 21 MCP tools
- Tool definitions consume ~15-20K tokens before conversation starts
- Research shows Claude's tool selection degrades with many similar tools
- Multiple overlapping search tools create confusion (6 different search variants)
- Configuration tools rarely used but always loaded

**Business Value:** Fewer, better-designed tools improve AI response quality, reduce API costs, and make the system easier to maintain. No new infrastructure required.

**Dependencies:** None (refactoring existing tools)

**Status:** Ready for Implementation

---

### Approach: Consolidation Over Abstraction

Rather than wrapping existing tools in "workflow mega-tools" that hide complexity, we consolidate redundant tools into focused primitives. This maintains composability while reducing cognitive and token overhead.

**Design Principle:** The AI can chain simple tools effectively. The problem isn't tool chaining—it's having too many similar tools to choose from.

---

## Current State: 21 Tools

### Search & Query (6 tools) → Consolidate to 1
| Current Tool | Purpose |
|--------------|---------|
| `search_semantic` | Natural language vector search |
| `search_by_metadata` | Filter by tags, author, source |
| `search_by_date_range` | Query by absolute dates |
| `search_by_relative_time` | Query by "last week", etc. |
| `search_knowledge_cards` | Search AI summaries only |
| `search_within_cluster` | Semantic search scoped to cluster |

### Chunks & Content (4 tools) → Consolidate to 2
| Current Tool | Purpose |
|--------------|---------|
| `get_related_chunks` | Find similar chunks |
| `get_knowledge_card` | Get AI summary for chunk |
| `get_recently_added` | Latest chunks |
| `get_reading_activity` | Activity stats |

### Clusters (4 tools) → Keep 3
| Current Tool | Purpose |
|--------------|---------|
| `list_clusters` | List all clusters |
| `get_cluster` | Get cluster details + members |
| `get_related_clusters` | Find conceptually related clusters |
| `get_stats` | KB statistics |

### Recommendations (3 tools) → Keep 1
| Current Tool | Purpose |
|--------------|---------|
| `get_reading_recommendations` | AI-powered recommendations |
| `get_recommendation_config` | View domain whitelist |
| `update_recommendation_domains` | Modify whitelist |

### Configuration (4 tools) → Consolidate to 1
| Current Tool | Purpose |
|--------------|---------|
| `get_ranking_config` | View ranking weights |
| `update_ranking_config` | Modify ranking |
| `get_hot_sites_config` | View source categories |
| `update_hot_sites_config` | Modify hot sites |

---

## Target State: 8 Tools

```
┌─────────────────────────────────────────────────────────────────┐
│                    Consolidated MCP Tools (8)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SEARCH & DISCOVERY                                              │
│  ├── search_kb(query, filters?)      # Unified search           │
│  └── get_chunk(chunk_id)             # Chunk + card + related   │
│                                                                  │
│  TEMPORAL                                                        │
│  └── get_recent(period?)             # Recent items + activity  │
│                                                                  │
│  CLUSTERS                                                        │
│  ├── list_clusters()                 # All clusters             │
│  ├── get_cluster(id)                 # Details + related        │
│  └── get_stats()                     # KB statistics            │
│                                                                  │
│  RECOMMENDATIONS                                                 │
│  └── get_recommendations(...)        # AI recommendations       │
│                                                                  │
│  CONFIGURATION                                                   │
│  └── configure_kb(action, params)    # All config in one        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Consolidated Tool Specifications

### 1. `search_kb` (replaces 6 tools)

**Purpose:** Unified search across the knowledge base with optional filters.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Natural language search query |
| `filters` | object | No | Optional filters (see below) |
| `limit` | integer | No | Max results (default 10) |

**Filter options:**
```json
{
  "cluster_id": "cluster-28",      // Scope to cluster
  "tags": ["ai", "agents"],        // Tag filter
  "author": "Simon Willison",      // Author filter
  "source": "reader",              // Source filter
  "date_range": {                  // Absolute dates
    "start": "2025-01-01",
    "end": "2025-01-31"
  },
  "period": "last_week",           // Relative time
  "search_cards_only": true        // Search summaries only
}
```

**Behavior:**
- If only `query` provided → semantic vector search
- If `cluster_id` provided → scoped search within cluster
- If `period` or `date_range` provided → time-filtered search
- Filters combine with AND logic
- Returns chunks with knowledge cards and cluster info included

---

### 2. `get_chunk` (replaces 2 tools)

**Purpose:** Get full details for a specific chunk including knowledge card and related chunks.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `chunk_id` | string | Yes | Chunk ID to retrieve |
| `include_related` | boolean | No | Include related chunks (default true) |
| `related_limit` | integer | No | Max related chunks (default 5) |

**Returns:**
- Full chunk content
- Knowledge card (summary + takeaways)
- Related chunks (via vector similarity)
- Cluster membership info
- All URLs (source, Readwise, highlight)

---

### 3. `get_recent` (replaces 2 tools)

**Purpose:** Get recent reading activity and items.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `period` | string | No | Time period (default "last_7_days") |
| `limit` | integer | No | Max items (default 10) |

**Returns:**
- Recent chunks ordered by date
- Activity summary (chunks per day)
- Top sources and authors for period
- Cluster distribution of recent items

---

### 4. `list_clusters` (unchanged)

**Purpose:** List all semantic clusters with metadata.

**Returns:**
- All clusters with names, descriptions, sizes
- Sorted by size descending

---

### 5. `get_cluster` (absorbs get_related_clusters)

**Purpose:** Get cluster details with members and related clusters.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `cluster_id` | string | Yes | Cluster ID |
| `include_members` | boolean | No | Include member chunks (default true) |
| `include_related` | boolean | No | Include related clusters (default true) |
| `member_limit` | integer | No | Max members (default 20) |
| `related_limit` | integer | No | Max related clusters (default 5) |

**Returns:**
- Cluster metadata (name, description, size)
- Member chunks with knowledge cards
- Related clusters via centroid similarity

---

### 6. `get_stats` (unchanged)

**Purpose:** Get knowledge base statistics.

**Returns:**
- Total chunks and documents
- Unique sources, authors, tags
- Cluster count
- Date range of content

---

### 7. `get_recommendations` (unchanged, rename only)

**Purpose:** AI-powered reading recommendations.

**Note:** This tool is already well-designed with appropriate parameters. Rename from `get_reading_recommendations` for consistency.

---

### 8. `configure_kb` (replaces 4 tools)

**Purpose:** Single entry point for all configuration.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Action to perform (see below) |
| `params` | object | No | Action-specific parameters |

**Actions:**
| Action | Description | Params |
|--------|-------------|--------|
| `show_all` | Display all configuration | - |
| `show_ranking` | Show ranking weights | - |
| `show_domains` | Show domain whitelist | - |
| `show_hot_sites` | Show hot sites categories | - |
| `update_ranking` | Update ranking weights | `{weights: {...}}` |
| `update_domains` | Modify domain whitelist | `{add: [...], remove: [...]}` |
| `update_hot_sites` | Modify hot sites | `{category, add, remove}` |

---

## Implementation Stories

| Story | Description | Complexity | Effort |
|-------|-------------|------------|--------|
| 4.1 | Create `search_kb` unified search tool | Medium | 3 days |
| 4.2 | Create `get_chunk` with embedded related + knowledge card | Low | 1 day |
| 4.3 | Create `get_recent` combining activity + recent items | Low | 1 day |
| 4.4 | Enhance `get_cluster` to include related clusters | Low | 0.5 days |
| 4.5 | Create `configure_kb` unified configuration tool | Medium | 1.5 days |
| 4.6 | Deprecate and remove old tools from MCP server | Low | 1 day |
| 4.7 | Update documentation and test coverage | Low | 1 day |

**Total Estimated Effort:** 9 days

---

## Migration Strategy

### Phase 1: Add New Tools (Stories 4.1-4.5)
- Implement consolidated tools alongside existing tools
- New tools call existing implementation functions
- No breaking changes

### Phase 2: Deprecation Period (1 sprint)
- Mark old tools as deprecated in descriptions
- Log warnings when deprecated tools are called
- Monitor usage to confirm new tools work

### Phase 3: Remove Old Tools (Story 4.6)
- Remove deprecated tool registrations
- Keep internal functions for reuse
- Update all documentation

---

## Success Metrics

| Metric | Before | Target | How to Measure |
|--------|--------|--------|----------------|
| Tool count | 21 | 8 | Count in main.py |
| Token overhead | ~18K | ~7K | Measure tool definitions |
| Tool selection accuracy | Unknown | Improved | Manual testing |
| Maintenance surface | 21 handlers | 8 handlers | Code complexity |

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing workflows | Medium | High | Phased migration with deprecation period |
| Filter complexity in search_kb | Low | Medium | Clear documentation, sensible defaults |
| Missing edge cases | Low | Low | Comprehensive test coverage before removal |

---

## Decision Record

**Decision:** Consolidate 21 MCP tools to 8 through smart combination rather than workflow abstraction.

**Rationale:**
1. AI can chain simple tools effectively—the problem is too many similar tools
2. Workflow wrappers hide complexity but don't reduce it
3. Consolidation reduces token overhead by ~60%
4. Maintains composability for power users
5. No new infrastructure or dependencies

**Alternatives Considered:**
- Option A (Web Interface): Rejected—adds infrastructure, doesn't solve tool overload
- Option B (Obsidian Plugin): Rejected—platform-specific, high maintenance
- Option C (Workflow mega-tools): Rejected—hides rather than reduces complexity

---

## Epic 5: Knowledge Digest & Email Summaries

**Goal:** Build an AI-powered knowledge digest system that regularly summarizes content from the Knowledge Base and Reader Inbox, delivering comprehensive email summaries with key insights, actionable takeaways, and one-click Reader integration—transforming passive content accumulation into active knowledge consumption.

**Business Value:** Enables users to stay informed about their accumulated knowledge without manually reviewing every article. Combines the power of AI synthesis with email delivery for passive knowledge consumption. Users receive rich, scannable summaries (~half DIN A4 page) that capture the essence of multiple articles, making it possible to understand content deeply without reading everything.

**Dependencies:** Epic 3 (Story 3.5 - Reading Recommendations, Story 3.6 - Email Digest infrastructure)

**Estimated Complexity:** High - Multi-document synthesis, email template design, Reader API integration, scheduled delivery

**Status:** Planned

---

### Story 6.1: Knowledge Base Digest Engine

**Status:** Backlog

**Summary:** Build a synthesis engine that generates comprehensive summaries of Knowledge Base content, grouping articles by cluster and generating rich digests with key aspects, detailed summaries, and actionable insights. Unlike brief TL;DRs, these summaries provide substantial content (~half DIN A4 page per topic) for deep understanding.

**Key Features:**
- **Cluster-Based Grouping:** Organize KB content by semantic clusters for thematic coherence
- **Rich Summary Generation:** Generate comprehensive summaries using Gemini 2.0 Pro
  - **Key Aspects Section:** 5-7 bullet points highlighting core ideas at a glance
  - **Detailed Summary:** 300-500 word narrative summary capturing nuances
  - **Notable Quotes:** 2-3 impactful quotes from source articles
  - **Cross-References:** Links to related clusters and concepts
- **Time-Window Processing:** Summarize content from configurable time periods (week, month, custom)
- **Incremental Updates:** Only process new/changed content since last digest
- **Quality Scoring:** Rate synthesis quality for continuous improvement

**Dependencies:**
- Story 2.1 (Knowledge Cards) - base content for synthesis
- Story 2.2 (Clustering) - thematic grouping
- Story 3.5 (Reading Recommendations) - quality domain filtering

**Technical Approach:**
- Gemini 2.0 Pro for long-context multi-document synthesis
- Hierarchical summarization: chunks → cluster summary → digest section
- Template-based output formatting for consistent structure
- Firestore storage of generated digests for caching

**Success Metrics:**
- Summary quality score >4.0/5.0 (user rating)
- Key aspects capture >90% of important themes (manual validation)
- Processing time <60 seconds for weekly digest generation
- Cost impact: ~$0.10/digest (Gemini Pro tokens)

**Business Value:**
- Understand a week's reading in 10 minutes
- Never lose track of accumulated knowledge
- Identify knowledge gaps and patterns
- Foundation for email delivery

**Output Format Example:**
```markdown
## 📚 Platform Engineering & Developer Experience

### Key Aspects
- Internal Developer Platforms reduce cognitive load by 40% on average
- Self-service infrastructure enables faster time-to-production
- Platform teams should be treated as product teams, not utilities
- Golden paths provide sensible defaults without restricting flexibility
- Measuring developer experience requires qualitative + quantitative signals
- Team Topologies patterns align with platform engineering principles
- Platform engineering is NOT just about tooling—culture and processes matter

### Summary
Platform engineering has emerged as a discipline focused on building and maintaining
internal developer platforms (IDPs) that abstract infrastructure complexity. The core
insight across your recent readings is that successful platforms treat developers as
customers, applying product thinking to internal tooling...

[~400 more words with nuanced synthesis]

### Notable Quotes
> "A platform is a foundation of self-service APIs, tools, services, knowledge and
> support which are arranged as a compelling internal product." — Team Topologies

> "The goal isn't to build the perfect platform—it's to reduce cognitive load while
> preserving developer autonomy." — Gregor Hohpe

### Related Topics
- Cognitive Load Theory (3 related articles)
- DevOps Transformation (5 related articles)
- Team Topologies (7 highlights)
```

---

### Story 6.2: Reader Inbox Summarization

**Status:** Backlog

**Summary:** Generate comprehensive summaries of unread articles in the Readwise Reader inbox, helping users understand content they haven't had time to read. Provides pre-read intelligence so users can decide what deserves full attention vs. what can be understood from summaries alone.

**Key Features:**
- **Unread Article Detection:** Query Reader API for inbox items with status "new" or "later"
- **Full-Content Fetching:** Retrieve complete article text via Reader API
- **Rich Summary Generation:** Same format as KB digests
  - Key Aspects bullets (5-7 points)
  - Detailed narrative summary (300-500 words)
  - Reading time estimate vs. summary time
  - Recommended action: "Deep read" | "Summary sufficient" | "Archive"
- **Priority Ranking:** Order summaries by relevance to existing KB
- **Batch Processing:** Summarize multiple articles in single digest
- **Read Status Tracking:** Track which summaries have been delivered

**Dependencies:**
- Story 6.1 (KB Digest Engine) - summary generation infrastructure
- Readwise Reader API - article content access

**Technical Approach:**
- Reader API: `GET /api/v3/list/?category=article&location=new`
- Fetch full content via Reader's document endpoint
- Reuse synthesis prompts from Story 6.1
- Store generated summaries in Firestore for caching
- Track delivered summaries to prevent duplicates

**Success Metrics:**
- >85% of summaries rated "accurate" by users
- "Summary sufficient" recommendations correct >80% of the time
- Processing time <30 seconds per article
- Zero duplicate summaries delivered

**Business Value:**
- Clear inbox backlog without guilt
- Make informed read/skip decisions
- Capture value from articles you'll never fully read
- Reduce reading anxiety ("too much to read")

**Reader API Integration:**
```python
# Fetch unread articles from Reader inbox
GET https://readwise.io/api/v3/list/
Headers: Authorization: Token {access_token}
Params:
  category: "article"
  location: "new"  # or "later" for "Read Later" items

# Response includes full document content for summarization
```

---

### Story 6.3: Weekly Knowledge Email Digest

**Status:** Backlog

**Summary:** Deliver a comprehensive weekly email digest combining KB synthesis and Reader inbox summaries. The email provides a rich, scannable overview of the user's knowledge landscape with one-click actions to save articles to Reader or mark content as processed.

**Key Features:**
- **Scheduled Delivery:** Cloud Scheduler triggers weekly (configurable: daily/weekly/biweekly)
- **Email Sections:**
  1. **This Week's Knowledge Growth:** New KB items summarized by cluster
  2. **Inbox Intelligence:** Summaries of unread Reader articles
  3. **Knowledge Connections:** Cross-cluster insights and emerging themes
  4. **Recommended Deep Reads:** Articles deserving full attention
  5. **Quick Archive Candidates:** Articles where summary suffices
- **Rich HTML Template:** Responsive design with:
  - Expandable/collapsible sections
  - Key Aspects as styled bullet lists
  - "Read More" links to detailed summaries
  - One-click Reader integration buttons
- **Readwise Reader Deep Links:**
  - Desktop: `https://readwise.io/reader/save?url={url}&tags={tags}`
  - Mobile: `readwise://save?url={url}`
  - Auto-tags: cluster name, "kx-digest", week number
- **SendGrid Integration:** Transactional email via SendGrid API

**Dependencies:**
- Story 6.1 (KB Digest Engine) - KB summaries
- Story 6.2 (Reader Inbox Summarization) - inbox summaries
- Story 3.6 (Email Digest) - email infrastructure

**Technical Approach:**
- Extend Story 3.6 email infrastructure
- Jinja2 templates for HTML email generation
- SendGrid dynamic templates for styling
- Cloud Scheduler for timing
- Firestore config for preferences

**Success Metrics:**
- Email open rate >60%
- Click-through rate >20%
- Unsubscribe rate <5%
- Renders correctly on Gmail, Outlook, Apple Mail
- Delivery within 5 minutes of scheduled time

**Business Value:**
- Passive knowledge consumption
- Weekly ritual for knowledge review
- No context-switching required
- Actionable from any device

**Email Template Structure:**
```html
<!-- Header -->
<div class="digest-header">
  <h1>📬 Your Weekly Knowledge Digest</h1>
  <p>Week 50, 2025 · 12 new KB items · 8 unread articles summarized</p>
</div>

<!-- Section 1: KB Growth -->
<div class="section kb-growth">
  <h2>📚 This Week's Knowledge Growth</h2>

  <!-- Cluster Summary Card -->
  <div class="cluster-card">
    <h3>Platform Engineering (5 new items)</h3>
    <div class="key-aspects">
      <strong>Key Aspects:</strong>
      <ul>
        <li>Internal Developer Platforms reduce cognitive load by 40%</li>
        <li>Platform teams should operate like product teams</li>
        <li>Golden paths balance standardization with flexibility</li>
      </ul>
    </div>
    <div class="summary-preview">
      Platform engineering has emerged as a critical discipline...
      <a href="#">Read full summary →</a>
    </div>
  </div>
</div>

<!-- Section 2: Inbox Intelligence -->
<div class="section inbox-intelligence">
  <h2>📥 Inbox Intelligence (8 articles)</h2>

  <div class="article-summary">
    <h4>The Future of AI Agents</h4>
    <span class="meta">martinfowler.com · 15 min read → 2 min summary</span>
    <span class="recommendation badge-deep-read">🔍 Deep Read Recommended</span>
    <div class="key-aspects">
      <ul>
        <li>AI agents differ from chatbots in autonomous action capability</li>
        <li>Tool use enables agents to interact with external systems</li>
      </ul>
    </div>
    <div class="actions">
      <a href="{reader_link}" class="btn">💻 Open in Reader</a>
      <a href="{mobile_link}" class="btn">📱 Mobile</a>
    </div>
  </div>
</div>

<!-- Footer with unsubscribe -->
```

---

### Story 6.4: On-Demand Digest Generation via MCP

**Status:** Backlog

**Summary:** Enable users to generate knowledge digests on-demand via MCP tools in Claude Desktop. Users can request summaries of specific clusters, time periods, or their Reader inbox without waiting for scheduled emails.

**Key Features:**
- **MCP Tools:**
  - `generate_kb_digest(clusters, time_range, format)` - Generate KB summary
  - `summarize_reader_inbox(limit, priority)` - Summarize unread articles
  - `get_cluster_digest(cluster_id)` - Deep dive on specific cluster
  - `send_digest_now()` - Trigger immediate email delivery
- **Format Options:**
  - `detailed` - Full half-page summaries
  - `brief` - Key aspects only
  - `bullets` - Pure bullet points
- **Caching:** Store generated digests for 24 hours to avoid regeneration
- **Conversation Context:** Include digest in Claude conversation for follow-up questions

**Dependencies:**
- Story 6.1 (KB Digest Engine) - digest generation
- Story 6.2 (Reader Inbox Summarization) - inbox summaries
- Story 2.6 (MCP Enhancements) - MCP infrastructure

**Technical Approach:**
- Extend MCP server with new tools
- Reuse digest generation from Stories 4.1/4.2
- Firestore caching with TTL
- Markdown output for Claude conversation

**Success Metrics:**
- Tool response time <30 seconds for digest generation
- Cache hit rate >50% for repeated requests
- User satisfaction >4.0/5.0 for generated digests

**Business Value:**
- Immediate access to knowledge summaries
- No waiting for scheduled emails
- Interactive exploration of knowledge
- Claude as knowledge concierge

**MCP Tool Interface:**
```python
generate_kb_digest(
    clusters: List[str] = None,  # Specific clusters or all
    time_range: str = "week",    # "day", "week", "month", "all"
    format: str = "detailed"     # "detailed", "brief", "bullets"
) -> DigestResponse

summarize_reader_inbox(
    limit: int = 10,             # Max articles to summarize
    priority: str = "relevance"  # "relevance", "recent", "oldest"
) -> InboxSummaryResponse
```

---

### Story 6.5: Digest Personalization & Preferences

**Status:** Backlog

**Summary:** Enable users to personalize their digest experience with preferences for content selection, summary depth, delivery schedule, and focus areas. Store preferences in Firestore and apply them to all digest generation.

**Key Features:**
- **Delivery Preferences:**
  - Schedule: daily, weekly, biweekly, monthly
  - Day of week and time (with timezone)
  - Email address (multiple recipients supported)
- **Content Preferences:**
  - Include/exclude specific clusters
  - Summary depth: detailed (default), brief, bullets
  - Maximum articles per section
  - Include/exclude Reader inbox
- **Focus Areas:**
  - Priority clusters (always included first)
  - Muted clusters (excluded unless explicitly requested)
  - Time decay: prefer recent content vs. comprehensive
- **MCP Configuration Tool:** `configure_digest(preferences)`
- **Unsubscribe:** Secure token-based one-click unsubscribe

**Dependencies:**
- Story 6.3 (Weekly Email Digest) - email delivery
- Story 6.4 (On-Demand MCP) - MCP tools

**Technical Approach:**
- Firestore document `config/digest_preferences`
- Apply preferences in digest generation pipeline
- Validate preferences via MCP tool
- Secure unsubscribe tokens

**Success Metrics:**
- 100% of preferences applied correctly
- Preferences UI/MCP tool easy to use (user feedback)
- Unsubscribe works reliably
- Schedule accuracy within 5 minutes

**Business Value:**
- Personalized knowledge experience
- Control over information flow
- Reduced noise, increased signal

**Firestore Preferences Schema:**
```json
{
  "enabled": true,
  "schedule": {
    "frequency": "weekly",
    "day_of_week": 1,
    "hour": 8,
    "timezone": "Europe/Berlin"
  },
  "recipients": ["user@example.com"],
  "content": {
    "summary_depth": "detailed",
    "max_kb_clusters": 5,
    "max_inbox_articles": 10,
    "include_reader_inbox": true,
    "include_recommendations": true
  },
  "focus": {
    "priority_clusters": ["cluster-28", "cluster-15"],
    "muted_clusters": ["cluster-42"],
    "time_decay": "balanced"
  },
  "unsubscribe_token": "secure-random-token"
}
```

---

### Story 6.6: Digest Analytics & Feedback Loop

**Status:** Backlog

**Summary:** Track digest engagement and collect user feedback to continuously improve summary quality and relevance. Measure open rates, click-through rates, and explicit quality ratings to optimize the digest experience.

**Key Features:**
- **Engagement Tracking:**
  - Email open tracking (SendGrid webhooks)
  - Click tracking on Reader links
  - Section engagement (which clusters/articles clicked)
- **Quality Feedback:**
  - In-email rating widget (thumbs up/down per section)
  - "This summary was helpful" tracking
  - "Mark as inaccurate" flag for corrections
- **Analytics Dashboard (MCP):**
  - `get_digest_analytics(period)` - View engagement metrics
  - Most/least engaged clusters
  - Summary quality trends over time
- **Feedback-Driven Optimization:**
  - Adjust summary prompts based on feedback
  - Prioritize high-engagement clusters
  - Flag consistently low-rated summaries for review

**Dependencies:**
- Story 6.3 (Weekly Email Digest) - email delivery
- SendGrid webhooks for tracking

**Technical Approach:**
- SendGrid event webhooks → Cloud Function → Firestore
- Click tracking via redirect URLs
- Firestore `digest_analytics` collection
- Feedback stored in `digest_feedback` collection

**Success Metrics:**
- Open rate >60%
- Positive feedback rate >80%
- Feedback collection rate >10% (users who rate)
- Summary quality improvement over time (A/B testing)

**Business Value:**
- Continuous improvement
- User-driven optimization
- Quality assurance for AI summaries

---

## Epic 4 Summary

| Story | Description | Complexity |
|-------|-------------|------------|
| 4.1 | Knowledge Base Digest Engine | High |
| 4.2 | Reader Inbox Summarization | Medium |
| 4.3 | Weekly Knowledge Email Digest | Medium |
| 4.4 | On-Demand Digest Generation via MCP | Medium |
| 4.5 | Digest Personalization & Preferences | Low |
| 4.6 | Digest Analytics & Feedback Loop | Low |

**Recommended Implementation Order:**
1. Story 6.1 (KB Digest Engine) - core synthesis capability
2. Story 6.2 (Reader Inbox Summarization) - extend to inbox
3. Story 6.3 (Weekly Email Digest) - delivery mechanism
4. Story 6.4 (On-Demand MCP) - interactive access
5. Story 6.5 (Preferences) + 4.6 (Analytics) - personalization & optimization

**Cost Analysis:**
| Component | Monthly Cost |
|-----------|-------------|
| Gemini Pro (synthesis) | ~$0.30 |
| Gemini Flash (inbox summaries) | ~$0.20 |
| SendGrid (emails) | $0 (free tier) |
| Firestore (digest storage) | ~$0.05 |
| Cloud Functions | ~$0.01 |
| **Total** | **~$0.56/month** |

---

## Epic 6: AI-Powered Blogging Engine

**Goal:** Build an intelligent blogging assistant that transforms Knowledge Base content into polished blog articles. The engine helps identify core ideas, generates article structures, creates drafts with proper referencing, and supports iterative article development over multiple sessions—enabling a workflow from knowledge synthesis to published content in Obsidian.

**Business Value:** Transforms the Knowledge Base from a passive consumption tool into an active content creation platform. Users can leverage their accumulated knowledge to produce blog content, thought leadership pieces, and synthesis articles without starting from scratch. The engine provides AI-assisted drafting while keeping the user in control of the final output.

**Dependencies:** Epic 5 (Story 5.1 - KB Digest Engine provides synthesis foundation)

**Estimated Complexity:** Very High - Content generation, multi-session state management, VS Code integration, Obsidian export

**Status:** Planned

---

### Story 6.1: Blog Idea Extraction from Knowledge Base

**Status:** Backlog

**Summary:** Automatically identify potential blog topics from Knowledge Base clusters, surfacing themes with sufficient depth for article development. The engine analyzes cluster coherence, content density, and novelty to suggest compelling blog ideas.

**Key Features:**
- **Cluster Analysis for Blog Potential:**
  - Assess each cluster for article-worthiness
  - Score based on: content depth, coherence, novelty, controversy
  - Identify clusters with "critical mass" for standalone articles
- **Idea Generation:**
  - Generate 3-5 blog title suggestions per cluster
  - Create one-paragraph pitch for each idea
  - Identify target audience and angle
  - Surface unique insights from the cluster
- **Cross-Cluster Ideas:**
  - Detect bridge opportunities between clusters
  - Suggest synthesis articles combining multiple themes
  - Identify contrarian takes based on cluster contradictions
- **Full Source Traceability (CRITICAL):**
  - Every idea MUST include complete source references
  - **Source Types:** Books, articles, highlights, podcast notes
  - **Reference Details per source:**
    - `source_id` - KB chunk/item ID for direct lookup
    - `source_type` - "book" | "article" | "highlight" | "podcast"
    - `title` - Original source title
    - `author` - Author name(s)
    - `readwise_url` - Direct link to Readwise entry
    - `source_url` - Original article/book URL (if available)
    - `relevance_score` - How relevant this source is to the idea
    - `key_quote` - Most relevant quote from this source
  - Minimum 3 sources per idea for credibility
  - Sources ranked by relevance and authority
- **MCP Tool:** `get_blog_ideas(clusters, style, count)`
- **Idea Storage:** Store generated ideas in Firestore for reference

**Dependencies:**
- Story 2.2 (Clustering) - cluster infrastructure
- Story 6.1 (KB Digest Engine) - synthesis capabilities

**Technical Approach:**
- Gemini analysis of cluster content and knowledge cards
- Scoring algorithm for blog-worthiness
- Title generation via few-shot prompting
- Cross-cluster relationship analysis

**Success Metrics:**
- >80% of generated ideas rated "interesting" by user
- Blog potential scores correlate with cluster quality
- Title suggestions are unique and non-generic
- Processing time <30 seconds for full KB scan

**Business Value:**
- Never face blank page syndrome
- Leverage existing knowledge for content
- Discover unexpected article angles
- Continuous content pipeline from reading

**MCP Tool Interface:**
```python
get_blog_ideas(
    clusters: List[str] = None,      # Specific clusters or all
    style: str = "thought_leadership", # "tutorial", "opinion", "synthesis", "how_to"
    count: int = 5,                   # Number of ideas to generate
    include_cross_cluster: bool = True
) -> BlogIdeasResponse

# Response structure with FULL source traceability
{
  "ideas": [
    {
      "id": "idea-001",
      "title": "Why Platform Engineering Is Not About Tools",
      "pitch": "Most articles about platform engineering focus on tooling...",
      "source_clusters": ["cluster-28"],
      "angle": "contrarian",
      "target_audience": "Engineering leaders",
      "estimated_depth": "high",
      "blog_potential_score": 0.89,

      # CRITICAL: Full source references for every idea
      "sources": [
        {
          "source_id": "chunk-123",
          "source_type": "book",
          "title": "Team Topologies",
          "author": "Matthew Skelton, Manuel Pais",
          "readwise_url": "https://readwise.io/bookreview/12345",
          "source_url": "https://teamtopologies.com/book",
          "relevance_score": 0.95,
          "key_quote": "A platform is a foundation of self-service APIs, tools, services...",
          "chapter": "Chapter 5: Platform Teams"
        },
        {
          "source_id": "chunk-456",
          "source_type": "article",
          "title": "What I Talk About When I Talk About Platforms",
          "author": "Martin Fowler",
          "readwise_url": "https://readwise.io/open/article/67890",
          "source_url": "https://martinfowler.com/articles/talk-about-platforms.html",
          "relevance_score": 0.92,
          "key_quote": "Platform engineering is about reducing cognitive load...",
          "published_date": "2024-03-15"
        },
        {
          "source_id": "chunk-789",
          "source_type": "highlight",
          "title": "Building Evolutionary Architectures",
          "author": "Neal Ford, Rebecca Parsons",
          "readwise_url": "https://readwise.io/open/highlight/11111",
          "relevance_score": 0.88,
          "key_quote": "Fitness functions enable teams to evolve their architecture..."
        }
      ],
      "source_count": {
        "books": 2,
        "articles": 3,
        "highlights": 5,
        "total": 10
      }
    }
  ]
}
```

---

### Story 6.2: Article Structure & Outline Generation

**Status:** Backlog

**Summary:** Generate detailed article outlines from selected blog ideas, creating a structured framework with sections, key points, and source references. The outline serves as a blueprint for article development, ensuring logical flow and comprehensive coverage.

**Key Features:**
- **Outline Generation:**
  - H2/H3 section structure with logical flow
  - Key points to cover in each section
  - Suggested word count per section
  - Source chunk references for each point
- **Outline Templates:**
  - **Thought Leadership:** Hook → Problem → Insight → Evidence → Call to Action
  - **Tutorial:** Overview → Prerequisites → Steps → Common Issues → Next Steps
  - **Synthesis:** Introduction → Theme 1 → Theme 2 → Theme 3 → Synthesis → Conclusion
  - **Opinion:** Thesis → Supporting Arguments → Counterarguments → Resolution
- **Source Integration:**
  - Map KB chunks to outline sections
  - Highlight quotable passages
  - Identify gaps needing additional research
- **Comprehensive Citation System (CRITICAL):**
  - Every outline point MUST have source attribution
  - **Per-Section Source Mapping:**
    - Primary sources (directly supporting the point)
    - Secondary sources (providing context/background)
    - Quotable passages with exact source reference
  - **Citation Metadata per reference:**
    - Full bibliographic info (author, title, date, URL)
    - Exact quote or paraphrase
    - Page/chapter reference (for books)
    - Readwise URL for one-click access
  - **Source Validation:**
    - Flag unsupported claims (no KB source found)
    - Highlight sections needing external research
    - Track source coverage per section (% of claims backed by KB)
  - **Source Bibliography:**
    - Auto-generate bibliography section
    - Group by source type (Books, Articles, Highlights)
    - Include full citation details
- **MCP Tool:** `generate_article_outline(idea_id, template, depth)`
- **Iterative Refinement:** Edit and regenerate outline sections

**Dependencies:**
- Story 6.1 (Blog Idea Extraction) - idea selection
- Story 2.1 (Knowledge Cards) - content for outline
- Story 2.7 (URL Link Storage) - source URLs for citations

**Technical Approach:**
- Template-based outline generation with Gemini
- Chunk-to-section mapping via semantic similarity
- Markdown output for VS Code editing
- Firestore storage of outlines
- Source validation via KB lookup

**Success Metrics:**
- Outlines cover >90% of relevant KB content
- Logical flow validated by user in >85% of cases
- Source references are accurate and useful
- **>95% of claims have KB source attribution**
- **100% of quotes traceable to original source**
- Generation time <45 seconds

**Business Value:**
- Clear roadmap for article writing
- Ensures no key points are missed
- Structured approach to content creation
- Foundation for collaborative editing

**Output Format (with full citation details):**
```markdown
# Article Outline: Why Platform Engineering Is Not About Tools

**Target:** 2,500-3,000 words | **Style:** Thought Leadership | **Audience:** Engineering Leaders
**Source Coverage:** 12 books, 8 articles, 23 highlights | **KB Coverage:** 94%

---

## 1. Introduction: The Tools Trap (300 words)
- Hook: "Every platform engineering conference is dominated by tool demos..."
- Problem statement: Tools-first thinking leads to platform failure
- Thesis: Successful platforms are built on culture and product thinking

### Sources for Section 1:
| Source | Type | Author | Key Quote | Link |
|--------|------|--------|-----------|------|
| Team Topologies (Ch. 5) | Book | Skelton & Pais | "Platform teams exist to enable..." | [Readwise](https://readwise.io/...) |
| Platform Engineering (2024) | Article | Fowler | "The tools trap is real..." | [Source](https://martinfowler.com/...) |

---

## 2. The Product Mindset Shift (500 words)
- Platform teams as product teams
- Developers as customers, not users
- Key insight: Measure outcomes, not outputs

### Quote to use:
> "A platform is a foundation of self-service APIs, tools, services, knowledge and
> support which are arranged as a compelling internal product."
> — **Team Topologies**, Matthew Skelton & Manuel Pais, p. 87
> [Open in Readwise](https://readwise.io/open/highlight/12345)

### Sources for Section 2:
| Source | Type | Author | Relevance | Link |
|--------|------|--------|-----------|------|
| Team Topologies | Book | Skelton & Pais | Primary | [Readwise](https://readwise.io/...) |
| The DevEx Framework | Article | Forsgren et al. | Secondary | [Source](https://queue.acm.org/...) |
| Accelerate | Book | Forsgren, Humble, Kim | Supporting | [Readwise](https://readwise.io/...) |

---

## 3. Culture Eats Tools for Breakfast (600 words)
### 3.1 Psychological Safety for Platform Adoption
- Golden paths require trust
- Failure tolerance enables experimentation

### 3.2 Team Topologies Alignment
- Stream-aligned teams consume, platform teams enable

### Sources for Section 3:
| Source | Type | Author | Key Quote | Link |
|--------|------|--------|-----------|------|
| Fearless Organization | Book | Amy Edmondson | "Psychological safety is..." | [Readwise](https://readwise.io/...) |
| Team Topologies | Book | Skelton & Pais | "Stream-aligned teams..." | [Readwise](https://readwise.io/...) |

... [continues with full outline]

---

## Identified Gaps (No KB Source Found)
- [ ] Need concrete metrics examples for Section 4 ⚠️ NO KB SOURCE
- [ ] Consider adding case study from own experience ⚠️ PERSONAL CONTENT NEEDED

---

## Full Bibliography

### Books (5 sources)
1. **Team Topologies** - Skelton, M. & Pais, M. (2019) - [Readwise](https://readwise.io/...)
2. **Accelerate** - Forsgren, N., Humble, J., Kim, G. (2018) - [Readwise](https://readwise.io/...)
3. **The Fearless Organization** - Edmondson, A. (2019) - [Readwise](https://readwise.io/...)
4. **Building Evolutionary Architectures** - Ford, N. et al. (2017) - [Readwise](https://readwise.io/...)
5. **A Philosophy of Software Design** - Ousterhout, J. (2018) - [Readwise](https://readwise.io/...)

### Articles (4 sources)
1. **What I Talk About When I Talk About Platforms** - Fowler, M. (2024) - [Source](https://martinfowler.com/...)
2. **The DevEx Framework** - Forsgren, N. et al. (2023) - [Source](https://queue.acm.org/...)
3. **Platform Engineering on Kubernetes** - Salatino, M. (2024) - [Source](https://www.infoq.com/...)
4. **Golden Paths** - Thoughtworks (2023) - [Source](https://www.thoughtworks.com/...)

### Highlights (12 passages used)
- See inline citations above
```

---

### Story 6.3: AI-Assisted Draft Generation

**Status:** Backlog

**Summary:** Generate article drafts from outlines, producing polished prose with proper KB references, quotations, and structured arguments. Drafts serve as starting points for human editing, not final outputs—emphasizing collaboration between AI and author.

**Key Features:**
- **Section-by-Section Generation:**
  - Generate one section at a time for focused editing
  - Or generate full draft for complete overview
  - Maintain consistent voice and tone throughout
- **Academic-Grade Citation System (CRITICAL):**
  - **Citation Formats Supported:**
    - Footnote-style: `[^1]` with full reference at bottom
    - Inline: `(Author, Year)` academic style
    - Hyperlink: `[quote](readwise-url)` for digital-first
    - None: Clean prose without visible citations (references appendix)
  - **Per-Citation Requirements:**
    - Author name(s)
    - Source title (book/article)
    - Publication year
    - Page number or chapter (for books)
    - Direct Readwise/source URL
    - Quote vs. paraphrase indicator
  - **Quote Handling:**
    - Exact quotes preserved verbatim from KB
    - Block quotes for passages >40 words
    - Attribution includes author + source + page
    - Readwise link for verification
  - **Paraphrase Tracking:**
    - Mark paraphrased content with source reference
    - Distinguish "inspired by" vs "based on"
    - Track confidence: direct KB match vs. inferred
  - **Citation Validation:**
    - Verify all citations match actual KB content
    - Flag hallucinated citations (no KB source)
    - Generate citation accuracy report
- **Voice & Style:**
  - Configurable tone: professional, conversational, academic
  - First-person vs. third-person option
  - Match existing blog voice (via example input)
- **Quality Controls:**
  - Avoid generic AI-sounding phrases
  - Ensure factual accuracy to source material
  - Flag sections needing human attention
  - **Zero tolerance for unsourced claims** (flag in output)
- **MCP Tool:** `generate_draft(outline_id, sections, voice, style, citation_format)`
- **Markdown Output:** Compatible with VS Code and Obsidian

**Dependencies:**
- Story 6.2 (Article Outline) - outline as blueprint
- Story 6.1 (KB Digest Engine) - synthesis capabilities
- Story 2.7 (URL Link Storage) - source URLs

**Technical Approach:**
- Gemini 2.0 Pro for long-form generation
- Section-aware context window management
- Voice matching via few-shot examples
- Citation format configurable (footnotes, inline, hyperlink, none)
- Citation validation pass before output

**Success Metrics:**
- >70% of draft content usable with minor edits
- **100% of citations verifiable against KB sources**
- **0% hallucinated references**
- **All quotes match original source verbatim**
- Consistent voice throughout article
- Generation time <90 seconds per 500-word section

**Business Value:**
- Accelerate writing from days to hours
- Focus human effort on refinement, not drafting
- Maintain authenticity with source-based content
- Professional quality starting point

**Draft Output Example (with full citation traceability):**
```markdown
# Why Platform Engineering Is Not About Tools

*Draft generated from outline-001 | Voice: Professional, First-person*
*Citation Format: Footnotes | Sources: 5 books, 4 articles, 12 highlights*
*Citation Accuracy: 100% verified against KB*

---

## Introduction: The Tools Trap

Walk into any platform engineering conference, and you'll be overwhelmed by tool
demonstrations. Kubernetes operators, GitOps pipelines, developer portals—the
technology showcase is impressive. But here's what those demos won't tell you:
most platform initiatives fail not because of tools, but despite them.[^1]

After analyzing dozens of platform engineering case studies in my knowledge base,
a clear pattern emerges. The organizations that succeed don't start with tools.
They start with a fundamental mindset shift: treating their internal platform as
a product, and their developers as customers.[^2]

> "A platform is a foundation of self-service APIs, tools, services, knowledge and
> support which are arranged as a compelling internal product."
> — Matthew Skelton & Manuel Pais[^3]

This article argues that successful platform engineering requires three things that
no tool can provide: product thinking, cultural alignment, and relentless focus on
developer experience. As Nicole Forsgren's research demonstrates, "what matters is
not which tools you use, but how you use them to enable flow."[^4]

---

## References

[^1]: Fowler, M. (2024). "What I Talk About When I Talk About Platforms."
      *martinfowler.com*. Retrieved from [Source](https://martinfowler.com/articles/talk-about-platforms.html).
      [Open in Readwise](https://readwise.io/open/article/67890)

[^2]: This insight synthesized from 12 articles in the Platform Engineering cluster.
      Primary sources: Fowler (2024), Skelton & Pais (2019), Salatino (2024).
      [View cluster](https://readwise.io/search?q=cluster:platform-engineering)

[^3]: Skelton, M. & Pais, M. (2019). *Team Topologies: Organizing Business and
      Technology Teams for Fast Flow*. IT Revolution Press, p. 87.
      ISBN: 978-1942788812. [Open in Readwise](https://readwise.io/bookreview/12345)

[^4]: Forsgren, N., Humble, J., & Kim, G. (2018). *Accelerate: The Science of
      Lean Software and DevOps*. IT Revolution Press, p. 142.
      [Open in Readwise](https://readwise.io/bookreview/23456)

---

## Citation Report

| Claim | Source Type | Verification | KB Match |
|-------|-------------|--------------|----------|
| "most initiatives fail..." | Article | ✅ Verified | 98% match |
| "product thinking mindset" | Book | ✅ Verified | 95% match |
| Block quote (Skelton) | Book | ✅ Exact | 100% verbatim |
| "what matters is not which tools" | Book | ✅ Verified | 97% match |

**Unsourced Claims:** 0
**Hallucinated References:** 0
**Total Citations:** 4
**KB Coverage:** 100%
```

---

### Story 6.4: Article Development Log (Blog Journal)

**Status:** Backlog

**Summary:** Maintain a persistent log of article development across sessions, tracking ideas, outlines, drafts, and revisions. The log enables multi-session article development, allowing users to pick up where they left off and maintain a history of content evolution.

**Key Features:**
- **Article Lifecycle Tracking:**
  - `idea` → `outlined` → `drafting` → `reviewing` → `published`
  - Timestamps for each state transition
  - Session logs with changes made
- **Multi-Session Support:**
  - Resume article development in any session
  - View diff between versions
  - Branching for alternative approaches
- **Development Notes:**
  - User annotations and TODOs
  - AI suggestions for improvement
  - Feedback incorporation tracking
- **MCP Tools:**
  - `list_articles(status)` - View articles in progress
  - `resume_article(article_id)` - Continue development
  - `save_article_state(article_id, content)` - Checkpoint progress
  - `get_article_history(article_id)` - View evolution
- **Firestore Persistence:** Full article state stored for continuity

**Dependencies:**
- Story 6.3 (Draft Generation) - draft content to track
- Story 6.2 (Outline Generation) - outline to track

**Technical Approach:**
- Firestore collection `blog_articles` with versioned content
- State machine for article lifecycle
- MCP tools for article management
- Markdown storage with frontmatter metadata

**Success Metrics:**
- 100% of article states preserved across sessions
- Resume functionality works seamlessly
- Version history accessible and accurate
- No data loss on session interruption

**Business Value:**
- Long-form content development over time
- Never lose progress on articles
- Track how ideas evolve
- Enables "article sprints" across multiple days

**Firestore Document Structure:**
```json
{
  "article_id": "article-20251217-platform-eng",
  "title": "Why Platform Engineering Is Not About Tools",
  "status": "drafting",
  "created_at": "2025-12-17T10:00:00Z",
  "updated_at": "2025-12-18T14:30:00Z",
  "idea": {
    "id": "idea-001",
    "generated_at": "2025-12-17T10:00:00Z"
  },
  "outline": {
    "version": 2,
    "content": "...",
    "generated_at": "2025-12-17T11:00:00Z"
  },
  "drafts": [
    {
      "version": 1,
      "content": "...",
      "generated_at": "2025-12-17T14:00:00Z",
      "word_count": 2847
    },
    {
      "version": 2,
      "content": "...",
      "generated_at": "2025-12-18T14:30:00Z",
      "word_count": 3102,
      "changes": "Expanded section 3, added case study"
    }
  ],
  "notes": [
    {"timestamp": "2025-12-17T15:00:00Z", "note": "Need to add metrics section"},
    {"timestamp": "2025-12-18T10:00:00Z", "note": "Consider contrarian angle for intro"}
  ],
  "source_clusters": ["cluster-28", "cluster-15"],
  "source_chunks": ["chunk-123", "chunk-456", "..."]
}
```

---

### Story 6.5: Article Series & Consolidation

**Status:** Backlog

**Summary:** Support multi-article series development and consolidation of related articles into comprehensive long-form content. Enable users to plan article sequences that build on each other, and later combine them into definitive guides or ebooks.

**Key Features:**
- **Series Planning:**
  - Define article series with common theme
  - Plan article sequence and dependencies
  - Track series completion status
  - Generate series overview/introduction
- **Article Linking:**
  - Cross-reference between series articles
  - "Previously in this series" links
  - "Coming next" teasers
  - Shared terminology and definitions
- **Consolidation Engine:**
  - Combine multiple articles into single long-form piece
  - Remove redundancy across articles
  - Add transitions and narrative flow
  - Generate unified table of contents
- **MCP Tools:**
  - `create_series(title, description, articles)` - Plan series
  - `consolidate_articles(article_ids, output_format)` - Merge articles
  - `get_series_status(series_id)` - Track progress

**Dependencies:**
- Story 6.4 (Article Development Log) - article tracking
- Story 6.3 (Draft Generation) - draft content

**Technical Approach:**
- Series metadata in Firestore `blog_series` collection
- Consolidation via Gemini long-context processing
- Redundancy detection via embedding similarity
- Markdown output with consistent formatting

**Success Metrics:**
- Series articles maintain consistent voice
- Consolidation removes >90% of redundancy
- Cross-references accurate and helpful
- Consolidated output is coherent and flows naturally

**Business Value:**
- Build toward major content pieces
- Repurpose blog content for ebooks/guides
- Systematic knowledge publication
- Content compounds over time

---

### Story 6.6: Obsidian Export & Publishing Workflow

**Status:** Backlog

**Summary:** Export finished articles to Obsidian vault with proper formatting, wikilinks, and metadata. Support the full workflow from draft completion to Obsidian publication, including frontmatter generation and bidirectional links to source KB items.

**Key Features:**
- **Obsidian-Compatible Export:**
  - Markdown with YAML frontmatter
  - Wikilinks to related notes (`[[note-name]]`)
  - Tags matching Obsidian conventions
  - Proper heading hierarchy
- **Frontmatter Generation:**
  - title, date, tags, status
  - Source KB references as links
  - Word count, reading time
  - Series information if applicable
- **Bidirectional Linking:**
  - Link from article to source KB items
  - Update source KB items with "Used in article" backlinks
  - Create Obsidian dataview compatible metadata
- **Export Options:**
  - Single file export
  - Export with all referenced notes
  - Export series as folder structure
- **VS Code Integration:**
  - Save directly to Obsidian vault path
  - Open in VS Code after export
  - Preview in Obsidian via URI scheme
- **MCP Tool:** `export_to_obsidian(article_id, vault_path, options)`

**Dependencies:**
- Story 6.4 (Article Development Log) - article content
- Obsidian vault path configuration

**Technical Approach:**
- Markdown transformation for Obsidian compatibility
- Frontmatter YAML generation
- Wikilink syntax conversion
- File system write to configured vault path

**Success Metrics:**
- Exported files render correctly in Obsidian
- Wikilinks resolve to existing notes
- Frontmatter parseable by Obsidian
- No manual formatting needed post-export

**Business Value:**
- Seamless publishing workflow
- Articles integrated into personal knowledge
- Bidirectional links enhance discoverability
- Content lives in user's own system

**Export Format:**
```markdown
---
title: "Why Platform Engineering Is Not About Tools"
date: 2025-12-18
status: published
tags:
  - platform-engineering
  - developer-experience
  - thought-leadership
word_count: 3102
reading_time: 12 min
series: "Platform Engineering Deep Dive"
series_part: 1
sources:
  - "[[Platform Engineering Cluster]]"
  - "[[Team Topologies Highlights]]"
  - "[[Developer Experience Notes]]"
created_via: kx-hub-blogging-engine
---

# Why Platform Engineering Is Not About Tools

Walk into any platform engineering conference, and you'll be overwhelmed by tool
demonstrations...

## Related Notes
- [[Platform Engineering Cluster]] - Source cluster for this article
- [[Developer Experience Metrics]] - Referenced in Section 4
- [[Team Topologies Book Notes]] - Key framework cited

## See Also
- [[Part 2 - Building Platform Teams]] (coming soon)
- [[Part 3 - Measuring Platform Success]] (planned)
```

---

### Story 6.7: Claude Code Integration for Article Editing

**Status:** Backlog

**Summary:** Enable seamless article editing workflow in VS Code with Claude Code assistance. Users can open generated drafts in VS Code, use Claude Code for iterative refinement, and sync changes back to the kx-hub article log.

**Key Features:**
- **VS Code Workflow:**
  - Export draft to VS Code workspace
  - Edit with Claude Code assistance
  - Real-time AI suggestions
  - Markdown preview
- **Claude Code Integration:**
  - Access KB context for fact-checking
  - Request section rewrites
  - Generate alternative phrasings
  - Expand or condense sections
- **Sync Back to kx-hub:**
  - Save edited content back to article log
  - Track changes between sessions
  - Preserve version history
- **MCP Bridge:**
  - Claude Code can query kx-hub for source material
  - Request additional KB context
  - Verify citations and quotes

**Dependencies:**
- Story 6.4 (Article Development Log) - article storage
- Claude Code installation
- VS Code workspace setup

**Technical Approach:**
- Export to `.md` file in configured workspace
- kx-hub MCP server provides KB context to Claude Code
- File watcher or manual sync for changes
- Git-based version tracking optional

**Success Metrics:**
- Drafts open in VS Code without formatting issues
- Claude Code can access KB for context
- Changes sync back to kx-hub reliably
- Editing workflow feels natural

**Business Value:**
- Best of both worlds: AI generation + IDE editing
- Familiar VS Code environment
- Claude Code for refinement assistance
- Professional writing workflow

---

## Epic 5 Summary

| Story | Description | Complexity |
|-------|-------------|------------|
| 5.1 | Blog Idea Extraction from Knowledge Base | Medium |
| 5.2 | Article Structure & Outline Generation | Medium |
| 5.3 | AI-Assisted Draft Generation | High |
| 5.4 | Article Development Log (Blog Journal) | Medium |
| 5.5 | Article Series & Consolidation | Medium |
| 5.6 | Obsidian Export & Publishing Workflow | Medium |
| 5.7 | Claude Code Integration for Article Editing | Low |

**Recommended Implementation Order:**
1. Story 6.1 (Blog Ideas) - foundation for content creation
2. Story 6.2 (Outlines) - structure before content
3. Story 6.3 (Draft Generation) - core capability
4. Story 6.4 (Article Log) - multi-session support
5. Story 6.6 (Obsidian Export) - publishing workflow
6. Story 6.5 (Series) + 5.7 (VS Code) - advanced features

**Cost Analysis:**
| Component | Monthly Cost |
|-----------|-------------|
| Gemini Pro (idea generation) | ~$0.10 |
| Gemini Pro (outline/draft) | ~$0.40 |
| Firestore (article storage) | ~$0.05 |
| Cloud Functions | ~$0.01 |
| **Total** | **~$0.56/month** |

---

## Future Epics (Beyond Epic 6)

See [PRD Section 8: Future Features & Backlog](./prd.md#8-future-features--backlog) for planned enhancements:

- **Epic 7:** Export & Distribution
  - GitHub export (Markdown + graph.json)
  - Static knowledge graph visualization
  - Public sharing options

- **Epic 8:** Advanced Integrations
  - DayOne Journal import
  - Multi-source integration (Pocket, Instapaper)
  - Mobile companion app

- **Epic 9:** Analytics & Insights
  - Reading habit analytics
  - Knowledge growth tracking
  - Cluster evolution visualization
  - Content production metrics

---

## Epic Summary

| Epic | Stories | Status | Completion |
|------|---------|--------|------------|
| Epic 1: Core Pipeline & KB Infrastructure | 8 | Complete | 8/8 Complete (100%) |
| Epic 2: Enhanced Knowledge Graph & Clustering | 7 | Complete | 7/7 Complete (100%) |
| Epic 3: Knowledge Graph Enhancement & Optimization | 10 | Active | 2/10 Complete (20%) |
| Epic 4: MCP Tool Consolidation | 7 | Ready | 0% |
| Epic 5: Knowledge Digest & Email Summaries | 6 | Planned | 0/6 (0%) |
| Epic 6: AI-Powered Blogging Engine | 7 | Planned | 0/7 (0%) |
| Epic 7: Export & Distribution (Future) | TBD | Backlog | 0% |
| Epic 8: Advanced Integrations (Future) | TBD | Backlog | 0% |
| Epic 9: Analytics & Insights (Future) | TBD | Backlog | 0% |

---

## Notes

- **Architecture:** Serverless Google Cloud (Cloud Functions, Workflows, Firestore, Vertex AI)
- **Cost Target:** <$5/month (Current: $1.40/month - **72% under budget**)
- **Success Criteria:** All PRD section 7 metrics met or exceeded
- **Next Milestone:** Complete Epic 3, then Epic 4 (MCP Tool Consolidation)
- **Epic 4:** Ready for implementation (tool consolidation approach decided)
