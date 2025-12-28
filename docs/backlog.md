# Backlog - kx-hub

**Project:** kx-hub - Personal AI Knowledge Base (Google Cloud + Vertex AI)

**Last Updated:** 2025-12-28

This document contains planned but not-yet-implemented stories and epics.

---

## Open Stories from Epic 2: Enhanced Knowledge Graph & Clustering

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

## Open Stories from Epic 3: Knowledge Graph Enhancement & Optimization

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
- Graph regenerated for >=1% changes (~1-2 times/week)
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

**Summary:** Enable users to save recommended articles directly to their Readwise Reader library via MCP tool, creating a seamless "discover -> save -> read -> highlight" workflow. Recommendations from Story 3.5 can be sent to Reader with one command, closing the loop between discovery and consumption.

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
- Complete workflow: Discover -> Save -> Read -> Highlight -> Back to KB
- Reduces friction between recommendation and consumption
- Articles saved to Reader get highlighted and return to kx-hub
- Creates virtuous knowledge cycle

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

**Status:** Planned

*Full epic details available in previous version of epics.md*

---

## Epic 5: Knowledge Digest & Email Summaries

**Goal:** Build an AI-powered knowledge digest system that regularly summarizes content from the Knowledge Base and Reader Inbox, delivering comprehensive email summaries with key insights, actionable takeaways, and one-click Reader integration.

**Business Value:** Enables users to stay informed about their accumulated knowledge without manually reviewing every article. Combines the power of AI synthesis with email delivery for passive knowledge consumption.

**Dependencies:** Epic 3 (Story 3.5 - Reading Recommendations, Story 3.6 - Email Digest infrastructure)

**Status:** Planned

### Stories:
- Story 5.1: Knowledge Base Digest Engine
- Story 5.2: Reader Inbox Summarization
- Story 5.3: Weekly Knowledge Email Digest
- Story 5.4: On-Demand Digest Generation via MCP
- Story 5.5: Digest Personalization & Preferences
- Story 5.6: Digest Analytics & Feedback Loop

*Full story details available in previous version of epics.md*

---

## Epic 6: AI-Powered Blogging Engine

**Goal:** Build an intelligent blogging assistant that transforms Knowledge Base content into polished blog articles. The engine helps identify core ideas, generates article structures, creates drafts with proper referencing, and supports iterative article development.

**Business Value:** Enables workflow from knowledge synthesis to published content in Obsidian.

**Dependencies:** Epic 2 (Knowledge Cards, Clustering)

**Status:** Planned

### Stories:
- Story 6.1: Blog Idea Extraction from Knowledge Base
- Story 6.2: Article Structure & Outline Generation
- Story 6.3: AI-Assisted Draft Generation
- Story 6.4: Article Development Log (Blog Journal)
- Story 6.5: Article Series & Consolidation
- Story 6.6: Obsidian Export & Publishing Workflow
- Story 6.7: Claude Code Integration for Article Editing

*Full story details available in previous version of epics.md*

---

## Future Epics (Beyond Epic 6)

- **Epic 7:** Export & Distribution
- **Epic 8:** Advanced Integrations
- **Epic 9:** Analytics & Insights

See PRD for details.
