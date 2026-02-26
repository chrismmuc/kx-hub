# Backlog - kx-hub

**Project:** kx-hub - Personal AI Knowledge Base (Google Cloud + Vertex AI)

**Last Updated:** 2026-02-26

This document contains planned but not-yet-implemented stories and epics.

---

## Open Stories from Epic 3: Knowledge Graph Enhancement & Optimization

### Story 3.6: Email Digest for Reading Recommendations

**Status:** Backlog (subsumed by Epic 9)

**Summary:** Implement a scheduled email digest that sends personalized reading recommendations to the user on a configurable schedule (weekly/daily). Extends Story 3.5's recommendation engine with email delivery via SendGrid, allowing users to receive curated article suggestions without actively querying Claude.

**Key Features:**
- **Scheduled Delivery:** Cloud Scheduler triggers weekly (default: Monday 8am) or daily
- **Email Template:** HTML email with recommendation cards, "why recommended" explanations
- **SendGrid Integration:** Transactional email delivery via SendGrid API
- **Digest Configuration:** Firestore config for schedule, recipient, preferences

**Dependencies:**
- Story 3.5 (Reading Recommendations) - provides recommendation engine
- SendGrid account and API key

**Business Value:**
- Passive knowledge discovery (recommendations come to you)
- Stay informed without active querying
- Weekly digest promotes consistent learning habits

---

### Story 3.9: Optimize Reading Recommendations Performance

**Status:** Backlog (low priority — async system works fine)

**Summary:** Reduce reading recommendations response time from ~5 minutes to <30 seconds by implementing batch LLM calls for depth scoring instead of sequential per-candidate calls.

**Technical Approach:**
1. Replace sequential `score_content_depth()` calls with batch version
2. Send multiple items per LLM call (Gemini supports this)
3. Cache results in Firestore `recommendation_cache` collection

**Estimated Effort:** 4-6 hours

---

## Epic 5: Knowledge Digest & Email Summaries

**Goal:** Build an AI-powered knowledge digest system that regularly summarizes content from the Knowledge Base and Reader Inbox, delivering comprehensive email summaries with key insights, actionable takeaways, and one-click Reader integration.

**Business Value:** Enables users to stay informed about their accumulated knowledge without manually reviewing every article.

**Dependencies:** Epic 3 (Story 3.5 - Reading Recommendations, Story 3.6 - Email Digest infrastructure)

**Status:** Planned — overlaps significantly with Epic 9

### Stories:
- Story 5.1: Knowledge Base Digest Engine
- Story 5.2: Reader Inbox Summarization
- Story 5.3: Weekly Knowledge Email Digest
- Story 5.4: On-Demand Digest Generation via MCP
- Story 5.5: Digest Personalization & Preferences
- Story 5.6: Digest Analytics & Feedback Loop

---

## Removed Stories (for reference)

The following were removed during the 2026-02-26 cleanup:

| Story | Reason |
|-------|--------|
| 1.9 (Reading Progress) | Low value — `last_highlighted_at` is sufficient for recency |
| 2.3, 2.4, 2.5 (Clustering) | Clustering deprecated in Epic 4.4, replaced by source-based organization |
| 3.2, 3.3 (Reclustering/Graph Regen) | Depend on deprecated clustering |
| 3.7 (Save to Reader) | Completed via Epic 12 |
| 3.10 (Cards-Only Search + N+1 Fix) | Completed — search_kb uses cards-only default, N+1 batch reads fixed |
| Epic 4 (Tool Consolidation) | Completed — tools already at 14 |
| Epic 6 (Blogging Engine) | Superseded by `article-synthesis` Claude Code skill + Epic 10 problems |
