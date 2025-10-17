# Project Brief: Personal KI-Knowledge Base

## Executive Summary

**Personal KI-Knowledge Base** is an automated knowledge management system that transforms daily reading highlights and articles from Readwise/Reader into actionable insights. The system uses OpenAI embeddings and semantic analysis to surface novel connections between notes, generate knowledge cards with summaries, deliver weekly digests highlighting creative cross-cluster links, **and provides on-demand query-driven retrieval to surface relevant articles, highlights, and book sections when working on specific problems**.

**Primary Problem:** Knowledge workers collect hundreds of highlights and articles but lack automated tools to discover non-obvious connections, synthesize insights, surface counterintuitive relationships across their growing knowledge base, **and quickly retrieve relevant knowledge when facing current challenges or questions**.

**Target Market:** Individual knowledge workers and researchers using Readwise/Reader who want to leverage AI for automated insight generation, connection discovery, **and intelligent knowledge retrieval**.

**Key Value Proposition:** Fully automated serverless pipeline that transforms raw reading data into curated weekly insights with creative cross-connections, **plus instant semantic search to find relevant knowledge on-demand**, requiring zero manual curation while staying within AWS free-tier and pay-per-use cost models.

---

## Problem Statement

Knowledge workers face three interconnected challenges:

1. **Lost Knowledge**: Despite collecting hundreds of articles, highlights, and notes through Readwise/Reader, this knowledge remains siloed and underutilized. Users rarely revisit old content, leading to forgotten insights and repeated discoveries.

2. **Hidden Connections**: Non-obvious relationships between ideas across different domains, authors, or time periods remain invisible without manual curation. Counterintuitive links and creative connections that could spark new insights go undiscovered.

3. **Retrieval Paralysis**: When working on a specific problem or question, users struggle to quickly find relevant articles, book sections, or highlights from their knowledge base. Manual searching is time-consuming and often fails to surface the most semantically relevant content, even when it exists in their collection.

**Impact**: Time wasted re-reading or re-searching for previously captured knowledge, missed opportunities for creative insight synthesis, and underutilization of personal knowledge investment. The average knowledge worker spends 30-40% of their time searching for information they've already encountered.

**Why Existing Solutions Fall Short**:
- Basic note-taking tools (Obsidian, Notion) require manual linking and tagging
- Search is keyword-based, missing semantic relationships
- No automated connection discovery or insight synthesis
- No proactive surfacing of relevant content based on current context

**Urgency**: As knowledge bases grow larger (many users have 1000+ items), the problem compounds exponentially. The gap between potential value and actual utility widens daily.

---

## Proposed Solution

**Personal KI-Knowledge Base** is a fully automated, serverless AWS pipeline that transforms passive reading collections into an active, queryable knowledge system with three core capabilities:

**1. Automated Insight Generation (Push Model)**
- Daily ingestion of new Readwise/Reader content via API
- OpenAI embeddings enable semantic understanding of all content
- Automated clustering (K-Means) identifies thematic groupings
- Weekly digests surface new additions, resurfaced connections, and synthesized insights
- Knowledge cards provide TL;DR summaries and key takeaways for each item

**2. Creative Connection Discovery (Proactive Model)**
- Hybrid similarity scoring combines embeddings with tag/author heuristics
- Contrastive pairing surfaces counterintuitive connections: items with low topical overlap but high semantic similarity
- Cross-cluster novelty detection highlights unexpected relationships
- Graph visualization (exported to Obsidian) makes connection networks explorable

**3. On-Demand Knowledge Retrieval (Pull Model)**
- Natural language query interface: describe your current problem or question
- Semantic search using query embeddings matched against knowledge base
- Returns ranked list of most relevant articles, highlights, and book sections
- Context-aware: shows not just titles but specific passages and key takeaways
- Fast retrieval from DynamoDB + S3 without vector database costs (MVP)

**Core Differentiators:**
- **Zero manual curation required**: Fully automated pipeline from ingestion to insight
- **Multi-modal value delivery**: Both proactive weekly insights AND reactive query-driven retrieval
- **Cost-conscious design**: Serverless pay-per-use architecture targeting AWS free-tier sustainability
- **Obsidian integration**: Exports to familiar PKM tool with graph visualization

**Why This Succeeds:**
- Embeddings provide semantic understanding beyond keyword matching
- Hybrid scoring and contrastive pairing go beyond simple clustering
- Integration with existing workflows (Readwise → System → Obsidian) reduces friction
- Automated daily processing ensures knowledge base stays current without user effort

---

## Target Users

### Primary User Segment: Active Knowledge Workers

**Demographic/Firmographic Profile:**
- Individual contributors in knowledge-intensive fields (researchers, writers, consultants, product managers, engineers)
- Ages 25-50, tech-savvy, comfortable with CLI/API tools
- Already invested in "tools for thought" ecosystem (using Readwise/Reader, likely Obsidian or Roam)
- Heavy readers: capturing 10-100+ highlights/articles per week
- Budget-conscious: prefer open-source or pay-per-use over fixed SaaS subscriptions

**Current Behaviors and Workflows:**
- Read articles, books, and papers using Reader or Readwise-integrated sources
- Save highlights and annotations manually
- Periodically export to Obsidian or other PKM tools
- Manually tag and link notes (when they have time)
- Occasionally search through old notes when working on specific problems
- Feel guilty about the growing "unprocessed" pile of captured content

**Specific Needs and Pain Points:**
- "I capture everything but rarely revisit anything"
- "I know I read something relevant to this problem 6 months ago but can't find it"
- "Manual linking is too time-consuming and I fall behind"
- "I want to discover connections I wouldn't think of myself"
- "I need actionable insights, not just another pile of unread notes"
- "I don't want to pay $50/month for yet another SaaS tool"

**Goals They're Trying to Achieve:**
- Build a "second brain" that actively helps them think, not just stores information
- Reduce time spent searching for previously-captured knowledge
- Discover non-obvious connections between ideas across domains
- Get value from their reading investment without manual curation effort
- Stay within budget while leveraging modern AI capabilities

---

## Goals & Success Metrics

### Business Objectives

- **Deliver automated value from reading investment**: Transform passive collection into active knowledge system with measurable engagement (weekly digest open rate >60%, query usage >3x/week)
- **Maintain cost sustainability**: Keep monthly operational costs within AWS free-tier limits ($0-5/month) for typical usage (100 items/week, 20 queries/week)
- **Achieve technical validation**: Prove serverless architecture scales to 10,000+ items without requiring vector database migration
- **Build foundation for future monetization**: Validate user demand and usage patterns to inform potential SaaS offering or open-source community

### User Success Metrics

- **Knowledge retrieval effectiveness**: Users find relevant content in <30 seconds when querying for specific topics/problems
- **Connection discovery value**: Users report 2+ "surprising but useful" connections per weekly digest
- **Workflow integration**: Obsidian sync completes successfully >95% of the time, users reference exported knowledge cards
- **Time savings**: Users report 30%+ reduction in time spent searching for previously-captured knowledge
- **Engagement consistency**: Users engage with system (via query or digest review) 3+ times per week

### Key Performance Indicators (KPIs)

- **Precision@10 for similarity**: ≥80% of top-10 similar items rated as "relevant" by user (semantic quality)
- **Processing latency**: 100% of new items processed and indexed within 24 hours of ingestion
- **Query response time**: <2 seconds for semantic search queries (P95)
- **Cost per 1000 items processed**: <$1.50 including embeddings, compute, and storage
- **GitHub export success rate**: ≥98% successful commits without conflicts or data loss
- **Email digest deliverability**: ≥95% inbox delivery rate (not spam)
- **False positive rate for connections**: <20% of suggested connections rated as "irrelevant" (quality threshold)

---

## MVP Scope

### Core Features (Must Have)

- **Daily Automated Ingestion**: Scheduled Lambda pulls new/updated items from Readwise and Reader APIs, stores raw JSON in S3, triggers processing pipeline
  - *Rationale: Foundation for everything; delta processing keeps costs low*

- **Semantic Embedding & Indexing**: OpenAI embedding generation for all content, stored in S3 (parquet/ndjson) with metadata in DynamoDB
  - *Rationale: Enables both similarity detection and query-driven retrieval*

- **Hybrid Similarity Scoring**: Cosine similarity on embeddings combined with tag/author heuristics to identify related items
  - *Rationale: Brainstorming session validated this approach balances quality and cost*

- **Clustering & Creative Connection Discovery**: K-Means clustering with contrastive pairing logic to surface low-overlap/high-similarity connections
  - *Rationale: Core differentiator - goes beyond simple similarity to find counterintuitive links*

- **Knowledge Card Generation**: Automated TL;DR summaries and key takeaways for each item using source-aware prompts (Reader vs Readwise)
  - *Rationale: Makes digest actionable; users get value without reading full articles*

- **Query-Driven Retrieval (CLI/API)**: Command-line or API endpoint to submit natural language queries, returns ranked relevant items with highlights and context
  - *Rationale: Critical "pull" model complements "push" digest; enables just-in-time knowledge access*

- **GitHub Export & Obsidian Sync**: Automated export of markdown files, knowledge cards, and graph.json to GitHub repository for Obsidian integration
  - *Rationale: Integrates with existing PKM workflows; graph visualization adds explorability*

- **Weekly Email Digest (SES)**: Automated email with new items, resurfaced connections, and synthesized insights
  - *Rationale: Push notification ensures users engage; weekly cadence balances value and noise*

- **Manual Pipeline Trigger**: Lambda function URL or CLI command to trigger full pipeline run for testing and prompt tuning
  - *Rationale: Essential for development and user experimentation*

### Out of Scope for MVP

- Multi-user support or team collaboration features
- Web-based UI (MVP is CLI/API only; web UI is Phase 2)
- Bedrock or on-premise deployment (OpenAI + AWS only)
- Real-time processing (<1 hour latency)
- Mobile applications
- Vector database (FAISS, Pinecone, etc.) - using brute-force cosine similarity for corpora <50k items
- Custom prompt templates UI (prompts are config-file based)
- Interactive feedback loop (thumbs up/down on connections)
- Notion or other PKM integrations beyond Obsidian
- Browser extension or reading app integration

### MVP Success Criteria

The MVP is successful if:
1. A single user can deploy the system to their AWS account using CDK/SAM with <30 minutes setup
2. Daily ingestion processes 100 items/day reliably without manual intervention
3. Query interface returns relevant results in <2 seconds for 80%+ of queries
4. Weekly digest consistently highlights 3-5 valuable connections or insights
5. GitHub export syncs successfully to Obsidian without data loss
6. Total monthly AWS costs remain <$5 for typical usage (500 items/month, 20 queries/week)

---

## Post-MVP Vision

### Phase 2 Features

**User Interface & Accessibility**
- Web-based dashboard for query interface, connection browsing, and configuration management
- Visual graph explorer for interactive connection discovery (D3.js/Cytoscape)
- Mobile-responsive design for on-the-go knowledge retrieval

**Enhanced Intelligence**
- Interactive feedback loop: thumbs up/down on connections trains personalized relevance models
- LLM-generated analogies and narrative storytelling for creative insights
- Automated cluster labeling with hierarchical topic detection (HDBSCAN)
- Cross-cluster novelty alerts for emerging themes

**Expanded Integrations**
- Notion, Roam Research, and Logseq export options
- Browser extension for direct highlight capture from any webpage
- Slack/Discord bot for team knowledge sharing
- Zapier/Make.com webhooks for custom workflow automation

### Long-term Vision (1-2 years)

Transform from personal tool into **intelligent research assistant**:
- Conversational interface: "Show me everything I've read about distributed systems performance" → synthesized summary with sources
- Proactive suggestions: "You're reading about consensus algorithms - here are 3 related items from your knowledge base you might have forgotten"
- Research synthesis: Given a topic or question, generate literature review style reports from your personal knowledge base
- Multi-modal knowledge: Support for PDFs, videos (with transcripts), podcasts, and meeting notes
- Collaborative knowledge bases for research teams or study groups

**Monetization Evolution:**
- Open-source core with managed hosting option ($10-20/month)
- Team/enterprise plans with shared knowledge bases and collaboration features
- API access for developers building knowledge-powered applications

### Expansion Opportunities

**Vertical Specializations:**
- Academic research version with citation management and paper recommendation
- Product management version with feature idea synthesis and market insight extraction
- Technical documentation search for engineering teams

**Platform Evolution:**
- Hybrid vector database option (FAISS on ECS) for users with >50k items
- Multi-cloud support (GCP, Azure) for users with existing infrastructure
- On-premise/self-hosted deployment for privacy-sensitive organizations

**Ecosystem Partnerships:**
- Native Readwise integration as premium add-on feature
- Obsidian plugin for bidirectional sync and inline queries
- Academic partnership for knowledge graph research and user studies

---

## Technical Considerations

### Platform Requirements

**Target Platforms:** AWS Cloud (Serverless)
- Lambda functions for all compute
- API Gateway for query endpoint (REST API)
- EventBridge for scheduled triggers
- Step Functions for pipeline orchestration

**Browser/OS Support:** N/A (MVP is CLI/API only, no web UI)

**Performance Requirements:**
- Query response time: <2 seconds (P95)
- Batch processing: Complete within 24 hours for 100 items/day
- Email digest delivery: Within 5 minutes of scheduled time

### Technology Preferences

**Embeddings:**
- **Provider:** OpenAI (required - Anthropic doesn't offer embeddings)
- **Model:** text-embedding-3-small (1536 dimensions, $0.02/M tokens)
- **Rationale:** 5x cheaper than previous generation, proven quality for semantic search
- **Fallback:** text-embedding-3-large if precision insufficient

**Text Generation (Multi-Provider Strategy):**
- **Summaries:** Anthropic Claude Haiku 4.5 ($1/$5/M tokens)
  - High-volume task, cost-sensitive
  - 2x faster than Sonnet, sufficient intelligence
  - Fallback: OpenAI GPT-5-mini ($0.25/$2/M tokens)

- **Creative Synthesis:** Anthropic Claude Sonnet 4.5 ($3/$15/M tokens)
  - Best reasoning for contrastive pairing and non-obvious connections
  - Weekly usage keeps costs reasonable
  - Fallback: OpenAI GPT-5 ($1.25/$10/M tokens)

- **Query Understanding:** OpenAI GPT-5-mini ($0.25/$2/M tokens)
  - User-facing, speed critical
  - Very fast, cost-effective
  - Fallback: GPT-5-nano ($0.05/$0.40/M tokens) for unlimited queries

**Backend:** Python 3.11+
- Lambda runtime
- boto3 for AWS SDK
- Libraries: pandas (parquet), numpy (cosine), scikit-learn (clustering)

**Database:**
- DynamoDB for metadata, links, and item records
- S3 for embeddings (parquet), markdown, knowledge cards, graph data
- No vector database for MVP (<50k items, brute-force cosine sufficient)

**Hosting/Infrastructure:** AWS Serverless Pay-Per-Use
- Estimated cost: $2.29/month (optimized: $1.16/month with caching/batching)
- Target: Stay within $5/month for typical usage

### Architecture Considerations

**Repository Structure:** Monorepo
- `/src` - Lambda function code
- `/config` - settings.yml for AI providers and system config
- `/docs` - PRD, architecture, brainstorming
- `/infra` - AWS CDK/SAM infrastructure as code
- `/tests` - Unit and integration tests

**Service Architecture:** Serverless Functions within Monorepo
- Step Functions orchestrates daily batch pipeline
- API Gateway + Lambda for synchronous query endpoint
- EventBridge triggers for scheduled tasks
- SES for email delivery

**Integration Requirements:**
- **Readwise API:** Daily delta sync for new highlights
- **Reader API:** Daily delta sync for new articles
- **OpenAI API:** Embeddings + text generation (GPT-5 family)
- **Anthropic API:** Text generation (Claude 4.5 family)
- **GitHub API:** Automated markdown export via commits
- **Obsidian:** Passive consumer (syncs from GitHub repo)

**Security/Compliance:**
- AWS Secrets Manager for all API keys (OpenAI, Anthropic, Readwise, GitHub)
- IAM least-privilege roles per Lambda
- Private GitHub repository
- No PII collection beyond user's own reading data
- Encryption at rest (S3, DynamoDB) and in transit (TLS)

**AI Provider Abstraction:**
- Factory pattern for provider selection based on config
- Graceful fallback if primary provider fails
- Cost optimization via prompt caching (90% savings) and batch API (50% discount)
- Model tiering for queries (nano/mini/standard based on complexity)

---

## Constraints & Assumptions

### Constraints

**Budget:** $0-5 per month for operational costs (AWS + AI APIs)
- Target: Self-sustainable within AWS free tier + minimal AI costs
- Stretch: <$10/month with heavy usage (500+ items/month, 100+ queries/month)
- No upfront capital investment for infrastructure

**Timeline:** MVP in 4-6 weeks
- Week 1-2: Infrastructure setup (CDK, Lambda scaffolding, DynamoDB schema)
- Week 3-4: Core pipeline (ingest → embeddings → clustering → summaries)
- Week 5: Query endpoint + GitHub export + email digest
- Week 6: Testing, prompt tuning, documentation

**Resources:** Solo developer (you), part-time availability
- No dedicated DevOps or infrastructure team
- Reliance on managed services to minimize operational overhead
- AI agents (like me) for development assistance

**Technical:**
- Must use serverless architecture (no always-on servers/containers)
- Cannot use paid vector databases (Pinecone, Weaviate, etc.) for MVP
- Limited to AWS services available in selected region
- Readwise/Reader API rate limits (unknown - need to check docs)
- OpenAI/Anthropic API rate limits (tier-dependent)

### Key Assumptions

**User Behavior & Usage:**
- User captures 10-100 highlights/articles per week via Readwise/Reader
- User queries knowledge base 3-5 times per week on average
- User reviews weekly email digest (not daily)
- User already has Obsidian setup and uses GitHub sync

**Technical Feasibility:**
- Brute-force cosine similarity performs adequately for <50,000 items
- Lambda cold starts don't significantly impact user experience for async pipeline
- Query endpoint Lambda can complete similarity search in <2s (may need warming)
- OpenAI text-embedding-3-small provides sufficient quality for similarity detection
- Claude Haiku 4.5 generates adequate summaries despite being smaller model

**AI Model Performance:**
- Claude Sonnet 4.5 superior for creative connections vs GPT-5 (needs validation)
- GPT-5-mini fast enough for real-time query understanding
- Source-aware prompts improve summary quality regardless of model choice
- Contrastive pairing (low overlap + high similarity) yields interesting insights

**Cost Assumptions:**
- 500 items/month = ~1M tokens for embeddings ≈ $0.02
- 500 summaries/month = ~500K input, 250K output ≈ $1.75 with Haiku 4.5
- 20 queries/week = 80K tokens/month ≈ $0.10 with GPT-5-mini
- Prompt caching achieves 50-70% savings on repetitive prompts
- Batch API achieves 50% savings on non-time-sensitive tasks

**Integration Assumptions:**
- Readwise/Reader APIs remain stable and accessible
- GitHub API allows automated commits without user interaction
- Obsidian successfully syncs from GitHub without conflicts
- AWS SES delivers emails without spam filtering issues (may need domain verification)

**Scope Assumptions:**
- Single-user deployment sufficient for MVP validation
- CLI/API acceptable for early users (no web UI needed initially)
- English-only content (no i18n/translation required)
- Text-only processing (no image/PDF extraction in MVP)

---

## Risks & Open Questions

### Key Risks

**API Rate Limiting & Throttling (HIGH IMPACT)**
- **Risk:** Readwise/Reader/OpenAI/Anthropic may throttle requests during batch processing spikes
- **Impact:** Pipeline delays, failed processing, incomplete data
- **Mitigation:** Implement exponential backoff, chunking, queue-based processing with SQS buffer (as identified in brainstorming session)

**Cost Overruns (MEDIUM IMPACT)**
- **Risk:** Actual usage exceeds "typical" estimates (500 items/month); unexpected token consumption from long articles
- **Impact:** Monthly costs exceed $5 target, approaching $20-50 if unchecked
- **Mitigation:** CloudWatch cost alarms, daily cost tracking, automatic throttling after threshold, token limits per summary

**Query Latency (MEDIUM IMPACT)**
- **Risk:** Brute-force cosine similarity doesn't scale as expected; Lambda cold starts add 2-5s latency
- **Impact:** Query response time >5s, poor user experience
- **Mitigation:** Lambda warming strategies, DynamoDB query optimization, early migration to FAISS if needed, caching frequent queries

**AI Model Quality Issues (MEDIUM IMPACT)**
- **Risk:** Claude Haiku 4.5 summaries lack depth; Sonnet 4.5 doesn't find creative connections as expected
- **Impact:** Low-quality insights, user disengagement, wasted AI costs
- **Mitigation:** A/B testing between providers, iterative prompt engineering, user feedback mechanism, fallback models

**GitHub Sync Conflicts (LOW-MEDIUM IMPACT)**
- **Risk:** Automated commits conflict with manual Obsidian edits; merge conflicts break sync
- **Impact:** Data loss, export failures, broken Obsidian integration
- **Mitigation:** Separate "kx-hub-generated" directory, conflict detection before commit, pull before push, user notifications

**Email Deliverability (LOW IMPACT)**
- **Risk:** SES emails land in spam; domain reputation issues
- **Impact:** Users miss weekly digests
- **Mitigation:** Domain verification (SPF/DKIM), warm-up period, allow users to whitelist sender, provide alternative RSS/webhook delivery

**Embedding Model Lock-In (LOW IMPACT)**
- **Risk:** Switching from OpenAI embeddings requires re-embedding entire corpus
- **Impact:** Migration cost ~$0.50 for 10k items, downtime during re-processing
- **Mitigation:** Accept OpenAI lock-in for MVP; embeddings are cheapest component; design for one-time migration if needed

### Open Questions

**Readwise/Reader API Capabilities:**
- What are the actual rate limits? (need to check API docs)
- Does API support delta/incremental sync or full-corpus pulls?
- How are deleted items handled?
- Is there webhook support for real-time ingestion?

**Query Interface Design:**
- CLI-only sufficient for MVP, or does minimal web UI add critical value?
- What's the preferred query response format? (JSON, markdown, interactive?)
- Should query history be persisted for analytics?
- Is conversational follow-up needed ("show me more like the 3rd result")?

**Similarity Scoring Calibration:**
- What cosine threshold defines "similar" vs "not similar"? (0.7? 0.8?)
- How to balance tag-based heuristics vs pure embedding similarity?
- Should similarity decay over time (older items less relevant)?
- How many similar items per note is optimal? (top 5? top 10?)

**Creative Connection Definition:**
- What makes a connection "counterintuitive" vs "random noise"?
- Is low tag overlap + high cosine sufficient, or need additional signals?
- Should cross-cluster connections be weighted higher?
- How to avoid surfacing trivial connections?

**Email Digest Content:**
- Weekly vs daily cadence for typical user?
- How many items/insights per digest? (too many = overwhelming, too few = not valuable)
- Should digest be personalized based on user's query history?
- Plain text, HTML, or markdown format?

**Performance Benchmarks:**
- At what corpus size does brute-force similarity become unacceptable?
- What's acceptable cold start latency for query endpoint? (1s? 3s?)
- Should Lambda be pre-warmed via scheduled pings?

**Multi-Provider Strategy:**
- Start with single provider for simplicity, or implement multi-provider from day 1?
- Should users explicitly choose provider, or system auto-selects based on cost/performance?
- How to handle provider API failures? (retry same provider, or immediately fallback?)

### Areas Needing Further Research

**Readwise/Reader API Documentation:**
- Detailed API rate limits and pagination
- Webhook support for incremental updates
- Data export formats and metadata availability
- Authentication and token management

**Obsidian Sync Behavior:**
- How does Obsidian handle external file changes?
- Can we trigger manual sync vs waiting for automatic sync?
- Conflict resolution strategies in Obsidian
- Graph view compatibility with generated graph.json

**Clustering Algorithm Selection:**
- K-Means vs HDBSCAN for topic discovery
- Optimal number of clusters (dynamic or fixed?)
- Should clusters be hierarchical or flat?
- Cluster stability over time (re-clustering frequency)

**Prompt Engineering for Contrastive Pairing:**
- What prompt structure best elicits counterintuitive connections from Sonnet 4.5?
- Should we provide examples of "good" vs "bad" connections in prompt?
- Does few-shot prompting improve connection quality?
- How to instruct model to explain *why* connection is interesting?

**Cost Monitoring & Optimization:**
- Real-time cost tracking per Lambda invocation
- Anomaly detection for unexpected cost spikes
- Optimal batch sizes for cost vs latency tradeoff
- When to trigger automatic throttling?

---

## Appendices

### A. Research Summary

**Brainstorming Session (Morphological Analysis)**

Conducted focused ideation session (~30 minutes) using What If Scenarios, First Principles Thinking, and Morphological Analysis. Key findings:

**Selected Architecture Decisions:**
1. **Retrieve & Preprocess:** EventBridge/SQS buffering before Markdown normalization (reliability over simplicity)
2. **Summaries:** Source-aware prompts tailored to Reader vs Readwise content (quality over uniformity)
3. **Similarity Detection:** Hybrid scoring blending cosine embeddings with tag/author heuristics (accuracy over pure ML)
4. **Creative Connections:** Contrastive pairing of low-overlap yet high-similarity notes (novelty over obviousness)

**Resilience Insights:**
- Volume spike (10x ingestion) primarily threatens brute-force similarity compute; serverless components remain stable
- OpenAI throttling requires retries/chunking; throughput slows but pipeline completes eventually
- GitHub export failures shouldn't block knowledge retention; canonical state must stay in AWS (S3/DynamoDB)

**AI Model Research (October 2025)**

Comprehensive analysis of latest OpenAI and Anthropic models:

**Key Finding:** Anthropic does NOT offer embedding models - they recommend Voyage AI partner. For multi-provider strategy, must use OpenAI (or Voyage AI) for embeddings, can choose between providers for text generation.

**Current Models:**
- OpenAI: GPT-5 (Aug 2025), GPT-5-mini, GPT-5-nano, text-embedding-3-small/large
- Anthropic: Claude Sonnet 4.5 (Sep 2025), Claude Haiku 4.5 (Oct 2025 - just released!), Claude Opus 4.1

**Cost-Performance Analysis:**
- Recommended configuration: OpenAI embeddings ($0.02/M) + Anthropic Haiku for summaries ($1/$5/M) + Sonnet for synthesis ($3/$15/M) + OpenAI mini for queries ($0.25/$2/M)
- Estimated monthly cost: $2.29 (optimized: $1.16 with caching/batching)
- Well within $5/month target

Full analysis available in: `docs/ai-model-analysis.md`

### B. Stakeholder Input

**Primary Stakeholder:** You (solo developer/user)

**Requirements Gathered:**
- Missing use case identified during brief creation: query-driven retrieval for finding relevant knowledge when working on specific problems
- Desire for multi-provider AI support to compare performance and optimize costs
- Strong preference for cost-conscious architecture (<$5/month operational costs)
- Emphasis on automated pipeline requiring zero manual curation
- Integration with existing workflow (Readwise/Reader → System → Obsidian)

### C. References

**Existing Documentation:**
- `docs/brainstorming-session-results.md` - Architecture decisions and resilience analysis
- `docs/prd.md` (V2) - Product requirements with query retrieval and multi-provider support
- `docs/architecture.md` - Updated system architecture with query endpoint and AI abstraction layer
- `docs/ai-model-analysis.md` - Comprehensive model comparison and recommendations

**External Resources:**
- OpenAI API Pricing (October 2025): platform.openai.com/docs/pricing
- Anthropic Pricing (October 2025): anthropic.com/pricing
- AWS Serverless Architecture Patterns
- Readwise API Documentation (to be reviewed)
- Reader API Documentation (to be reviewed)

**Technical References:**
- Hybrid similarity scoring approaches (cosine + heuristics)
- Contrastive learning for knowledge discovery
- Morphological analysis for architecture decision-making
- K-Means vs HDBSCAN clustering for topic detection

---

## Next Steps

### Immediate Actions

1. **Review and Approve Project Brief**
   - Validate all sections align with your vision
   - Identify any gaps or misalignments
   - Confirm technical assumptions and constraints

2. **Research Readwise/Reader API Documentation**
   - Confirm rate limits and pagination support
   - Verify delta/incremental sync capabilities
   - Check webhook availability for real-time updates
   - Document authentication requirements

3. **Set Up AWS Account & IAM**
   - Create dedicated AWS account (or use existing with billing alerts)
   - Set up IAM user with programmatic access
   - Configure CloudWatch billing alarms ($1, $5, $10 thresholds)
   - Establish Secrets Manager for API keys

4. **Obtain API Keys**
   - OpenAI API key (create account, verify billing)
   - Anthropic API key (create account, verify billing)
   - Readwise API token
   - GitHub personal access token (repo scope)

5. **Generate PRD from Brief**
   - Use this brief as input for comprehensive PRD creation
   - Detail functional and non-functional requirements
   - Define epics and user stories for implementation
   - Establish acceptance criteria for each story

6. **Initialize Project Repository**
   - Create GitHub repository (private)
   - Set up monorepo structure (/src, /infra, /config, /docs, /tests)
   - Add .gitignore (exclude secrets, local config)
   - Create initial README with project overview

7. **Proof of Concept: Query Embeddings**
   - Quick Python script to test OpenAI text-embedding-3-small
   - Embed 10 sample articles/highlights
   - Compute cosine similarity
   - Validate quality and response time
   - Measure actual token consumption vs estimates

### PM Handoff

This Project Brief provides the comprehensive context for the **Personal KI-Knowledge Base** project.

**For PRD Development:**
Review this brief thoroughly, particularly:
- Section 6 (MVP Scope) - forms the basis for functional requirements
- Section 8 (Technical Considerations) - informs technical assumptions and architecture requirements
- Section 10 (Risks & Open Questions) - should be addressed in PRD planning

**Key Decisions to Carry Forward:**
1. Query-driven retrieval is now a core MVP feature (Use Case #7)
2. Multi-provider AI support (OpenAI + Anthropic) for cost optimization and performance comparison
3. Target: <$5/month operational costs with typical usage (500 items/month, 20 queries/week)
4. Timeline: 4-6 weeks for MVP delivery
5. CLI/API first, no web UI for MVP

**Next Command:**
Start PRD generation mode using this brief as input, working section-by-section collaboratively with the user to create detailed requirements, epics, and user stories with acceptance criteria.
