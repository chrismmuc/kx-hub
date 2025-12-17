# PRD (V4) – Personal AI Knowledge Base (Google Cloud + Vertex AI)

## 1. Goal & Value Proposition
- **Goal**: Daily processing of Readwise/Reader highlights/articles, automatic **semantic processing**, **clustering/linking**, **TL;DR cards**, **idea synthesis**, **on-demand query retrieval**, export to **GitHub → Obsidian**, plus a **weekly email digest** with AI-powered recommendations and **intelligent reading synthesis**.
- **Non-Goals (V1)**: Team multi-user, Web UI (CLI/API only).

## 2. Core Use Cases
1. Daily ingest of new articles/highlights via API.
2. Semantic similarity & clustering.
3. Knowledge Cards (short TL;DR + takeaways).
4. Idea synthesis per cluster/topic.
5. Export (Markdown + graph.json) → GitHub → Obsidian Sync.
6. Email digest (new items, resurfacings, synthesis of the week).
7. **Query-Driven Retrieval**: Natural Language Query → semantic search → ranked results with relevant articles/highlights/book sections.
8. **Conversational Knowledge Access**: Claude Desktop integration via Model Context Protocol (MCP) server for natural language queries without context switching.
9. **AI-Powered Reading Recommendations**: Tavily-powered discovery of relevant articles with quality filtering, recency scoring, and diversity optimization.
10. **Intelligent Reading Synthesis**: Cross-article synthesis, knowledge amplification detection, novel insight identification, and automated highlighting.
11. Manual trigger for test runs.

## 3. Architectural Guidelines
- Simple & extensible, **Serverless (Google Cloud)**, **Pay-per-Use**.
- **Unified AI Platform**: Use of **Vertex AI** for all AI tasks (Embeddings, Generative Models, Vector Search).
- Configurable via repo (`/config/settings.yml`).
- Delta processing (only new/changed items).
- Secure (Google Secret Manager, IAM Least-Privilege, private repo).

## 4. Data Flows

### Batch Processing Pipeline (daily)
1) Ingest (Readwise/Reader APIs) → **Cloud Storage (raw)**
2) Normalize → **Cloud Storage (markdown)** (+ Frontmatter)
3) Embed & Store (Vertex AI `gemini-embedding-001`) → **Firestore kb_items** (with embeddings)
4) Knowledge Cards (Vertex AI `Gemini 2.5 Flash`) → **Firestore kb_items.knowledge_card** field
5) Cluster & Link → **Firestore links** + **Cloud Storage graph.json**
6) Export → **GitHub** (Commit/PR)
7) Weekly Digest → **SendGrid Email**

### On-Demand Query Flow (User-initiated)
8) User Query (CLI/API or **Claude Desktop via MCP**) → **Cloud Function Query Handler** or **MCP Server**
9) Query Embedding (Vertex AI `gemini-embedding-001`) → **Firestore Vector Search**
10) Ranked Results → **Return**: Articles/highlights with context + Knowledge Cards

## 5. Data Model (Brief)
**Firestore `kb_items`**: Document ID = item_id, fields: title, readwise_url, source_url, highlight_url, tags, authors, created_at, updated_at, cluster_id[], similar_ids[], scores[], knowledge_card {summary, takeaways}.
**Firestore `kb_clusters`**: Document ID = cluster_id, fields: label, members[], parent_cluster?, related_clusters[], label_version.
**Cloud Storage**: `/raw/*.json`, `/markdown/notes/{id}.md`, `/cards/{id}.md`, `/graphs/graph.json`.

## 6. Configuration

### `/config/settings.yml` – Vertex AI & App Configuration

```yaml
vertex_ai:
  project_id: "your-gcp-project-id"
  location: "europe-west4"
  embeddings_model: "gemini-embedding-001"
  generative_model: "gemini-2.5-flash-001"

readwise:
  api_key_secret: "/kx-hub/readwise/api-key" # Path in Google Secret Manager
  sync_interval_hours: 24

github:
  repo: "user/obsidian-vault"
  branch: "main"
  commit_author: "kx-hub-bot"

email:
  provider: "sendgrid"
  api_key_secret: "/kx-hub/sendgrid/api-key"
  from: "noreply@kx-hub.example.com"
  digest_schedule: "0 9 * * MON"  # Mondays 9am
```

### Estimated Monthly Costs
- **Embeddings & Vector Search**: ~$3.10 (Vertex AI)
- **Generative Models**: ~$1.50 (Vertex AI Gemini 2.5 Flash)
- **Cloud Functions, Storage, Firestore**: ~$0.50
- **Total**: **~$5.10/month**
✅ **Goal: ~$5/month achieved. Complexity and maintenance effort are drastically reduced compared to the V2 architecture.**

## 7. Success Criteria
- **Precision**: ≥80% meaningful "similar" suggestions.
- **Coverage**: 100% of new items processed ≤ 24h.
- **Query Response Time**: <1s for semantic search (P95).
- **Query Relevance**: ≥80% of top-10 results rated as "relevant".
- **Cost Control**: Monthly costs <$10 for typical usage.
- **GitHub Export**: ≥98% successful commits without conflicts.
- **Email Deliverability**: ≥95% inbox delivery (not spam).

## 8. Epics Overview

See [epics.md](./epics.md) for detailed breakdown of all epics and stories.

| Epic | Description | Status |
|------|-------------|--------|
| **Epic 1** | Core Batch Processing Pipeline & KB Infrastructure | Complete |
| **Epic 2** | Enhanced Knowledge Graph & Clustering | Complete |
| **Epic 3** | Knowledge Graph Enhancement & Optimization | Active |
| **Epic 4** | Knowledge Digest & Email Summaries | Planned |
| **Epic 5** | AI-Powered Blogging Engine | Planned |
| **Epic 6** | User Experience & Discoverability | Decision Pending |

### Epic 4: Knowledge Digest & Email Summaries

**Goal:** Build an AI-powered knowledge digest system that regularly summarizes content from the Knowledge Base and Reader Inbox, delivering comprehensive email summaries with key insights, actionable takeaways, and one-click Reader integration.

**Key Capabilities:**
- **KB Digest Engine**: Rich summaries (~half DIN A4 page) with key aspects bullets and detailed narrative
- **Reader Inbox Summarization**: Summarize unread articles to help decide what deserves deep reading
- **Weekly Email Digest**: Scheduled delivery combining KB synthesis and inbox summaries
- **On-Demand MCP Tools**: Generate digests interactively via Claude Desktop
- **Personalization**: Configurable preferences for content, schedule, and focus areas
- **Analytics & Feedback**: Track engagement and continuously improve summary quality

**Stories:**
| Story | Description |
|-------|-------------|
| 4.1 | Knowledge Base Digest Engine |
| 4.2 | Reader Inbox Summarization |
| 4.3 | Weekly Knowledge Email Digest |
| 4.4 | On-Demand Digest Generation via MCP |
| 4.5 | Digest Personalization & Preferences |
| 4.6 | Digest Analytics & Feedback Loop |

### Epic 5: AI-Powered Blogging Engine

**Goal:** Build an intelligent blogging assistant that transforms Knowledge Base content into polished blog articles. The engine helps identify core ideas, generates article structures, creates drafts with proper referencing, and supports iterative article development—enabling a workflow from knowledge synthesis to published content in Obsidian.

**Key Capabilities:**
- **Blog Idea Extraction**: Identify article-worthy topics from KB clusters
- **Outline Generation**: Create structured article frameworks with source references
- **AI-Assisted Drafting**: Generate polished prose with citations and consistent voice
- **Article Development Log**: Track progress across multiple sessions (idea → published)
- **Series & Consolidation**: Plan article sequences and combine into long-form content
- **Obsidian Export**: Publish to Obsidian vault with wikilinks and frontmatter
- **Claude Code Integration**: Seamless VS Code editing workflow with AI assistance

**Stories:**
| Story | Description |
|-------|-------------|
| 5.1 | Blog Idea Extraction from Knowledge Base |
| 5.2 | Article Structure & Outline Generation |
| 5.3 | AI-Assisted Draft Generation |
| 5.4 | Article Development Log (Blog Journal) |
| 5.5 | Article Series & Consolidation |
| 5.6 | Obsidian Export & Publishing Workflow |
| 5.7 | Claude Code Integration for Article Editing |

### Epic 6: User Experience & Discoverability

**Goal:** Address system complexity by improving tool discoverability and reducing cognitive load. The system has grown to 30+ MCP tools, creating a "Too Many Tools" problem where users cannot easily discover or remember available capabilities.

**Decision Required:** Three options under evaluation:

| Option | Approach | Effort | Pros | Cons |
|--------|----------|--------|------|------|
| **A** | Minimal Web Interface | 8-12 days | Visual navigation, mobile-friendly | Additional infra, auth complexity |
| **B** | Obsidian Plugin | 12-18 days | Native integration, no new infra | Limited to Obsidian users |
| **C** | Focused MCP + Workflow Tools | 6-10 days | No new UI, leverages Claude | Still requires tool knowledge |

**Recommendation:** Option C (Focused MCP with Workflow Tools) - Consolidate 30+ tools into 5-7 workflow-oriented mega-tools with built-in discovery (`what_can_i_do()`, `explore_knowledge()`, `weekly_ritual()`, `start_blog()`).

See [epics.md](./epics.md) for full details and comparison matrix.

## 9. Future Features & Backlog
See [future-features.md](./future-features.md) for additional feature ideas:
- **DayOne Journal Import**: Local file upload integration for personal journal entries
- **Export & Distribution**: GitHub export, Obsidian vault sync
- **Analytics & Insights**: Reading habit analytics, knowledge growth tracking