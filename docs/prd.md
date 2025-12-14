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
| **Epic 4** | Intelligent Reading Synthesis & Automated Curation | Planned |

### Epic 4: Intelligent Reading Synthesis & Automated Curation

**Goal:** Build an AI-powered reading assistant that synthesizes insights across multiple articles, automatically extracts key passages, identifies knowledge amplification vs. novel insights, and integrates seamlessly with Readwise Reader.

**Key Capabilities:**
- **Cross-Article Synthesis**: Multi-document summarization across article cohorts
- **Knowledge Amplification Detection**: Identify when new articles reinforce existing KB concepts
- **Novel Insight Identification**: Detect genuinely new ideas not present in KB
- **Automatic Key Passage Highlighting**: AI-powered extraction of key insights before/after reading
- **Readwise Reader Integration**: Inject synthesis + signals as document notes in Reader
- **Synthesis Storage**: Store syntheses as first-class knowledge artifacts

**Stories:**
| Story | Description |
|-------|-------------|
| 4.1 | Cross-Article Synthesis Engine |
| 4.2 | Knowledge Amplification Detection |
| 4.3 | Novel Insight Identification |
| 4.4 | Automatic Key Passage Highlighting |
| 4.5 | Readwise Reader Notes Integration |
| 4.6 | Synthesis Storage & Cluster Enrichment |
| 4.7 | Reader-Tagged Synthesis Documents |

## 9. Future Features & Backlog
See [future-features.md](./future-features.md) for additional feature ideas:
- **DayOne Journal Import**: Local file upload integration for personal journal entries
- **Export & Distribution**: GitHub export, Obsidian vault sync
- **Analytics & Insights**: Reading habit analytics, knowledge growth tracking