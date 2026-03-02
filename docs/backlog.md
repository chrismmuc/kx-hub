# Backlog - kx-hub

**Project:** kx-hub - Personal AI Knowledge Base (Google Cloud + Vertex AI)

**Last Updated:** 2026-02-26

This document contains planned but not-yet-implemented stories and epics.

---

## Open Stories from Epic 3: Knowledge Graph Enhancement & Optimization

### ~~Story 3.6: Email Digest~~ → Superseded by Epic 9

Email als Delivery-Kanal ersetzt durch Obsidian + Readwise Reader (Epic 9).

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

## ~~Epic 5: Knowledge Digest & Email Summaries~~ → Superseded by Epic 9

Vollständig ersetzt durch Epic 9 (Weekly Knowledge Summary). Email-Delivery durch Obsidian + Reader ersetzt. LLM-Synthese statt strukturierter Digests.

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
