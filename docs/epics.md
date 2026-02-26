# Epics - kx-hub

**Last Updated:** 2026-02-26

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
| 1.8 | **Highlighted-At Fix** - Store actual reading time (`last_highlighted_at`) instead of ingestion time for accurate "recently read" queries | ✅ Done |

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

**Status:** Complete (Recommendations superseded by Epic 11)

| Story | Description | Status |
|-------|-------------|--------|
| 3.1 | **Cloud Run Deployment** - Deploy MCP server to Cloud Run with SSE transport for remote access | ✅ Done |
| 3.1.1 | **OAuth 2.1 Authentication** - Secure authentication for Claude Mobile/Web with token refresh | ✅ Done |
| 3.4 | **Source Relationships** - Discover and store relationships between sources (moved to Epic 4) | ✅ Done |
| 3.5 | **Reading Recommendations** - AI-powered article recommendations via Tavily search based on interests | ✅ Done |

*Note: Story 3.5 recommendations are tag/source-based ("more of the same"). Epic 11 replaces this with problem-driven recommendations.*

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

| 4.6 | **Source Connections in Search Results** - Surface cross-source relationships directly in `search_kb` results (2 efficient Firestore `IN` queries) | ✅ Done |

**Key Changes:**
- Clusters replaced by Sources (books, articles) as first-class entities
- Explicit typed relationships (`extends`, `supports`, `contradicts`)
- 18 MCP tools (down from 22, removed cluster tools)
- Automatic relationship extraction in daily pipeline
- Search results include `connections` section showing how sources relate

See [epic4.md](epic4.md) for full details.

---

## Epic 6: AI-Powered Blogging Engine ~~🚧~~ ✅ Superseded

**Goal:** Transform KB content into polished blog articles with AI assistance.

**Status:** Superseded — replaced by `article-synthesis` Claude Code skill + Epic 10 (Feynman Problems). The skill handles the full workflow: problem analysis → evidence gathering → article drafting → Obsidian export.

---

## Epic 7: Async MCP Interface ✅

**Goal:** Replace long-running synchronous MCP tools with async job pattern to prevent client timeouts.

**Status:** Complete (Infrastructure reused by Epic 11)

| Story | Description | Status |
|-------|-------------|--------|
| 7.1 | **Async Recommendations** - `recommendations`, `recommendations_history` via Cloud Tasks | ✅ Done |
| 7.2 | **Simplified Interface** - Config-based defaults, optional `topic` override | ✅ Done |
| 7.3 | **Async Article Ideas** - Apply pattern to article ideas if needed | Optional |

*Note: Async infrastructure (Cloud Tasks, job polling) is preserved. Epic 11 changes query generation and filtering to be problem-driven.*

See [epics/epic7.md](epics/epic7.md) for full details.

---

## Epic 9: Recent Knowledge Connections & Daily Digest

**Goal:** Zeige bei neuen Chunks automatisch die Verbindungen zu existierenden Sources. Täglicher Email-Digest mit neuen Learnings und deren Cross-Source Relationships.

**Status:** Planned

| Story | Description | Status |
|-------|-------------|--------|
| 9.1 | **Extend get_recent** - Add `include_connections` parameter with grouped relationships | Planned |
| 9.2 | **MCP Server Integration** - Update tool schema and handler | Planned |
| 9.3 | **Daily Email Digest** - Scheduled email with new chunks and connections | Planned |
| 9.4 | **Natural Language Summary** - LLM-generated fließtext summary (optional) | Planned |

See [epics/epic9.md](epics/epic9.md) for full details.

---

## Epic 10: Guided Problem Definition (Feynman Method) ✅

**Goal:** Replace unguided idea generation with problem-first approach based on Feynman's "12 Favorite Problems". Users define top problems, evidence is automatically matched from KB - with emphasis on source relationships (especially contradictions). Claude generates article ideas from evidence.

**Status:** Complete (Stories 10.1-10.4)

| Story | Description | Status |
|-------|-------------|--------|
| 10.1 | **Problems Tool** - Single `problems` tool with actions: add, list, analyze, archive | ✅ Done |
| 10.2 | **Pipeline Integration** - Auto-match new chunks to problems after ingest | ✅ Done |
| 10.3 | **Cleanup Legacy** - Remove suggest_article_ideas, deleted article_ideas.py | ✅ Done |
| 10.4 | **Epic 6 Integration** - Update blogging workflow to use problems-based approach | ✅ Done |
| 10.5 | **Infographic Generation** - Gemini 3 Pro Image ($0.13-$0.24/image) | Optional |

**Key Changes:**
- 1 new tool (`problems`) replaces 4 tools (suggest_article_ideas, list_ideas, accept_idea, reject_idea)
- Evidence auto-matched via pipeline (efficient: only new chunks × active problems)
- Contradictions highlighted as most valuable for article angles
- Claude generates ideas in conversation, not stored

See [epics/epic10.md](epics/epic10.md) for full details.

---

## Epic 11: Problem-Driven Recommendations ✅

**Goal:** Transform recommendations from "more of the same" to "what helps me grow" - aligned with Feynman problems and enhanced with knowledge graph connections.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 11.1 | **Problem-Based Query Generation** - Replace tag-based queries with problem-based queries (translated to EN) | ✅ Done |
| 11.2 | **Graph-Enhanced Filtering** - Use knowledge graph to boost relevant recommendations (extends, contradicts) | ✅ Done |
| 11.3 | **Updated MCP Tool Interface** - Add `problems` and `mode` parameters, graph context in output | ✅ Done |
| 11.4 | **Evidence Deduplication** - Don't recommend content already in problem's evidence | ✅ Done |

**Key Features:**
- Two modes: `deepen` (more on topics with evidence) vs `explore` (fill knowledge gaps)
- Graph connections: "This EXTENDS your reading of Culture Map"
- Token-efficient: ~80 tokens/recommendation (vs ~500 current)

See [epics/epic11.md](epics/epic11.md) for full details.

---

## Epic 12: Automated Weekly Recommendations to Readwise ✅

**Goal:** Batch weekly recommendations execution (Thursday night → Friday) with automatic Readwise Reader inbox integration, strict result filtering, and AI-source tagging.

**Status:** Complete

| Story | Description | Status |
|-------|-------------|--------|
| 12.1 | **Cloud Scheduler Setup** - Schedule weekly batch job at Friday 04:00 UTC (customizable via config) | ✅ Done |
| 12.2 | **Batch Recommendations Function** - Cloud Function executes `recommendations()` with balanced mode, max 3 results, high recency filter | ✅ Done |
| 12.3 | **Readwise Reader Integration** - Implement `POST /api/v3/save/` to add recommendations to Reader inbox (advance Story 3.7) | ✅ Done |
| 12.4 | **Auto-Tagging** - Automatically tag saved articles with `ai-recommended` + source name + topic tags | ✅ Done |
| 12.5 | **Deduplication Check** - Skip articles already in Reader library (query `/api/v3/list/` before saving) | ✅ Done |
| 12.6 | **Batch Job Tracking** - Store batch execution metadata (timestamp, result count, success/failure) in Firestore `batch_jobs` collection | ✅ Done |
| 12.7 | **Error Handling & Alerts** - Retry logic, Slack notifications on failure, detailed logging | ✅ Done |

**Key Features:**
- Strict filtering: Max 3 results per batch
- Balanced search mode with emphasis on recency (< 7 days)
- Automatic inbox organization via "ai-recommended" tag
- Zero-duplicate guarantee (check Reader library first)
- Weekly digest: Saves execution report to Firestore

**Integration Points:**
- Extends Epic 11 (Problem-Driven Recommendations)
- Completes Story 3.7 (Save to Reader)
- Uses Cloud Scheduler + Cloud Functions
- Firestore for job tracking
- Readwise Reader API (new)

**Config Storage** (Firestore `config/batch_recommendations`):
```json
{
  "enabled": true,
  "schedule": "0 22 * * 4",  # Thursday 22:00 UTC
  "mode": "balanced",
  "max_results": 3,
  "recency_days": 7,
  "auto_tags": ["ai-recommended"],
  "readwise_api_enabled": true,
  "notification_slack": "#ai-recs"
}
```

**Cost Impact:**
- Cloud Scheduler: ~$0 (included in free tier)
- Cloud Function (weekly): ~$0.50/month
- Readwise API calls: Included in paid plan

**Success Metrics:**
- 100% scheduled execution (no missed runs)
- 0% duplicate articles in Reader inbox
- <5 minute execution time per batch
- 100% automatic tagging rate

See [epics/epic12.md](epics/epic12.md) for full implementation details.

---

## Epic 13: Auto-Snippets from Reader ✅

**Goal:** Automatically extract key passages from unread Reader documents tagged `kx-auto` via LLM, store as searchable kb_items.

**Status:** Complete (simplified 2026-02-25)

| Story | Description | Status |
|-------|-------------|--------|
| 13.1 | **Reader API Client** - Fetch docs tagged `kx-auto` with full text from Reader API v3 | ✅ Done |
| 13.2 | **Snippet Extraction** - Single-stage LLM extraction with open-ended count and full-article coverage | ✅ Done (simplified) |
| 13.3 | **Write Back to Readwise & Pipeline Integration** - Readwise v2 highlight writer, direct snippet embedding to Firestore kb_items, full orchestration (extract → Readwise → embed → problem match) | ✅ Done |
| 13.4 | **Nightly Trigger & Tag Management** - Cloud Scheduler, remove tag after processing | ✅ Done |

**Key Design:** No new MCP tools or collections. Snippets are regular `kb_items` with `source_type: "auto-snippet"`, searchable via existing `search_kb`.

**2026-02-25 Simplification:** Removed the 3-stage pipeline (extract candidates → KB enrichment → LLM judge) in favor of a single LLM call. The old pipeline missed later sections of long articles due to LLM attention degradation, and the KB enrichment/judge stages added complexity without proportional value. Changes:
- Removed 15-snippet cap — LLM decides how many to extract based on article content
- Removed Stage 1.5 (KB novelty scoring via embeddings) and Stage 2 (LLM judge with composite scoring)
- Enhanced prompt with "distribute proportionally across the ENTIRE article" instruction
- Net result: -929 lines of code, better coverage (verified: 18/18 verbatim quotes spanning 0.7%-99.1% of a 21K-word article)

See [epics/epic13.md](epics/epic13.md) for full details.

---

## Epic 14: Evidence-Aware Query Generation

**Goal:** Replace static template queries with LLM-generated, evidence-aware Tavily search queries that target knowledge gaps instead of re-discovering what the user already knows.

**Status:** Done

| Task | Description | Status |
|------|-------------|--------|
| 1 | `_build_evidence_summary()` — compact evidence context for LLM prompt | ✅ |
| 2 | `generate_evidence_queries()` — Gemini Flash query generation with fallback | ✅ |
| 3 | Integrate into `generate_problem_queries()`, add `query_method` field | ✅ |
| 4 | Tests: mock LLM, fallback, query_method, evidence summary | ✅ |

**Key Design:** No new infra or MCP tools. Modifies `generate_problem_queries()` in `recommendation_problems.py` — LLM path when evidence exists, template fallback on error. ~$0.03/year cost.

See [epics/epic14.md](epics/epic14.md) for full details.

---

## Backlog

See [backlog.md](backlog.md) for remaining ideas:
- Story 3.6/Epic 5: Email digest for recommendations/knowledge
- Story 3.9: Recommendation performance optimization (low priority)
