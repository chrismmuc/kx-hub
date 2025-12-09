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

## Future Epics (Beyond Current Scope)

See [PRD Section 8: Future Features & Backlog](./prd.md#8-future-features--backlog) for planned enhancements:

- **Epic 4:** Export & Distribution
  - GitHub export (Markdown + graph.json)
  - Obsidian vault sync
  - Weekly email digest

- **Epic 5:** Advanced Features
  - DayOne Journal import
  - Current article recommendations
  - Multi-source integration

- **Epic 6:** MCP Server Enhancements
  - Cluster-based browsing tools
  - Knowledge card search and display
  - Advanced query templates

---

## Epic Summary

| Epic | Stories | Status | Completion |
|------|---------|--------|------------|
| Epic 1: Core Pipeline & KB Infrastructure | 8 | Complete | 8/8 Complete (100%) |
| Epic 2: Enhanced Knowledge Graph & Clustering | 7 | Complete | 7/7 Complete (100%) |
| Epic 3: Knowledge Graph Enhancement & Optimization | 7 | Active | 2/7 Complete (29%) |
| Epic 4: Export & Distribution (Future) | TBD | Planned | 0% |
| Epic 5: Advanced Features (Future) | TBD | Backlog | 0% |
| Epic 6: MCP Server Enhancements (Future) | TBD | Backlog | 0% |

---

## Notes

- **Architecture:** Serverless Google Cloud (Cloud Functions, Workflows, Firestore, Vertex AI)
- **Cost Target:** <$5/month (Current: $1.40/month - **72% under budget**)
- **Success Criteria:** All PRD section 7 metrics met or exceeded
- **Next Milestone:** Complete Story 1.7 (MCP Server) to enable conversational knowledge access
