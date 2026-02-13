# Epic 12: Auto-Snippets from Reader

**Goal:** Automatically extract key passages from unread Reader documents tagged `kx-auto-ingest`, so they become searchable in the KB without manual highlighting.

**Business Value:**
- Articles tagged in Reader get automatically distilled into searchable snippets
- No manual highlighting needed for articles user wants to "capture but not read fully"
- LLM suggests the most relevant passages, not just random excerpts
- Snippets flow into existing search, knowledge cards, and problem matching

**Dependencies:**
- Epic 1 (Core Pipeline - embedding, Firestore storage)
- Epic 2 (Knowledge Cards - generated for snippets too)
- Epic 4 (Source Relationships - auto-discovered for new sources)

**Status:** Planned

---

## Problem Statement

Current pipeline only ingests **user-made highlights** from Readwise Export API. This requires the user to:
1. Open an article in Reader
2. Read it
3. Manually highlight key passages
4. Wait for daily sync

**Problem:** Many interesting articles get saved but never read/highlighted. They sit in Reader forever, their knowledge inaccessible to the KB.

**Solution:** Tag unread articles with `kx-auto-ingest` in Reader. A nightly job fetches the full text and uses Gemini Flash to extract 3-7 key passages as "auto-snippets". These flow through the existing pipeline (embed, store, knowledge cards) and become searchable immediately.

**Example:**
- User saves "How Netflix Reinvented HR" in Reader
- Tags it `kx-auto-ingest` (one tap in Reader app)
- Nightly: System fetches full text, LLM extracts key passages
- Next day: `search_kb("Netflix culture")` finds the auto-snippets
- Problem matching: Auto-matched to "Wie baue ich eine starke Team-Kultur?"

---

## Architecture

### Flow

```
┌─────────────────────────────────────────────────────────┐
│ 1. READER API FETCH                                     │
├─────────────────────────────────────────────────────────┤
│ GET /api/v3/list/                                       │
│   ?category=article                                     │
│   &tag=kx-auto-ingest                                   │
│                                                         │
│ For each document:                                      │
│   → Fetch full HTML content via document endpoint       │
│   → Convert HTML → clean text                           │
│   → Store raw JSON in GCS (audit trail)                 │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ 2. LLM SNIPPET EXTRACTION                               │
├─────────────────────────────────────────────────────────┤
│ Gemini Flash reads full text                            │
│                                                         │
│ Prompt: "Extract 3-7 key passages from this article.    │
│   Each passage should be:                               │
│   - A direct quote or close paraphrase (2-4 sentences)  │
│   - Self-contained (understandable without context)     │
│   - The most insightful/actionable parts                │
│   - Diverse (cover different aspects of the article)"   │
│                                                         │
│ Output: JSON array of snippets with:                    │
│   - text: the passage                                   │
│   - context: why this passage matters (1 sentence)      │
│   - position: rough location (intro/middle/conclusion)  │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ 3. NORMALIZE & EMBED                                     │
├─────────────────────────────────────────────────────────┤
│ Transform snippets → Markdown (same format as highlights)│
│                                                         │
│ Frontmatter:                                            │
│   source_type: auto-snippet                             │
│   reader_doc_id: <id>                                   │
│   title, author, url from Reader metadata               │
│   tags: from Reader + ["auto-snippet"]                  │
│                                                         │
│ Content: snippet text + LLM context                     │
│                                                         │
│ → Embed via Vertex AI (768-dim, same as all kb_items)   │
│ → Store in Firestore kb_items collection                │
│ → Create/update source in sources collection            │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ 4. POST-PROCESSING                                       │
├─────────────────────────────────────────────────────────┤
│ → Knowledge Card generation (existing pipeline)         │
│ → Relationship extraction (existing pipeline)           │
│ → Problem matching (existing pipeline)                  │
│                                                         │
│ → Remove kx-auto-ingest tag from Reader document        │
│ → Add kx-processed tag (audit trail)                    │
└─────────────────────────────────────────────────────────┘
```

### Data Model

Auto-snippets are stored as regular `kb_items` with additional metadata:

```python
# Firestore: kb_items/{chunk_id}
{
    "chunk_id": "auto_snippet_abc123_1",
    "content": "The best thing you can do for employees...",  # snippet text
    "embedding": [0.1, 0.2, ...],           # 768-dim vector
    "source_id": "src_netflix_hr",
    "source_type": "auto-snippet",          # distinguishes from highlights
    "reader_doc_id": "01abc123",            # Reader document ID
    "title": "How Netflix Reinvented HR",
    "author": "Patty McCord",
    "source_url": "https://hbr.org/...",
    "tags": ["management", "culture", "auto-snippet"],
    "created_at": "2026-02-14T...",
    "snippet_metadata": {
        "position": "middle",               # intro/middle/conclusion
        "context": "Core insight about...",  # LLM-generated context
        "extraction_model": "gemini-2.0-flash"
    }
}
```

### Cost Estimate

| Operation | Cost per Article | Notes |
|-----------|-----------------|-------|
| Reader API | $0 | Included in Readwise subscription |
| Gemini Flash (extract snippets) | ~$0.003 | ~2K input tokens + 500 output |
| Embeddings (5 snippets) | ~$0.0005 | Vertex AI embedding |
| Knowledge Cards (5 snippets) | ~$0.02 | Gemini Flash per snippet |
| Firestore writes | ~$0.00001 | Negligible |
| **Total per article** | **~$0.025** | |

At 10 articles/week: **~$1/month**

---

## Stories

### Story 12.1: Reader API Client

**Goal:** Fetch documents tagged `kx-auto-ingest` with full text content.

**New file:** `src/ingest/reader_client.py`

**Tasks:**
1. [ ] Reader API client with auth (reuse existing Readwise API key)
2. [ ] `fetch_tagged_documents(tag="kx-auto-ingest")` — list documents with tag
3. [ ] `fetch_document_content(doc_id)` — get full HTML/text content
4. [ ] HTML → clean text conversion (strip nav, ads, boilerplate)
5. [ ] Store raw response in GCS (same pattern as Readwise ingest)
6. [ ] Rate limiting and retry logic (same pattern as existing ingest)
7. [ ] Unit tests with mocked API responses

**Reader API Endpoints:**
- `GET /api/v3/list/?tag=kx-auto-ingest` — list tagged documents
- Document content available via `html_content` field or separate endpoint

**Acceptance Criteria:**
- Fetches all documents with `kx-auto-ingest` tag
- Extracts clean text from HTML content
- Raw JSON stored in GCS for audit trail
- Handles pagination, rate limiting, empty results
- Tests pass with mocked API

---

### Story 12.2: LLM Snippet Extraction

**Goal:** Use Gemini Flash to extract 3-7 key passages from article full text.

**New file:** `src/knowledge_cards/snippet_extractor.py`

**Tasks:**
1. [ ] Snippet extraction prompt (extract key passages as JSON)
2. [ ] `extract_snippets(full_text, title, author)` → list of snippets
3. [ ] JSON schema validation for LLM output
4. [ ] Configurable snippet count (default: 3-7, based on article length)
5. [ ] Handle edge cases: short articles (<500 words), very long articles (>10K words)
6. [ ] Reuse existing `src/llm/` abstraction for Gemini Flash calls
7. [ ] Unit tests with sample articles

**Snippet Schema:**
```python
@dataclass
class ExtractedSnippet:
    text: str           # The key passage (2-4 sentences)
    context: str        # Why this passage matters (1 sentence)
    position: str       # "intro" | "middle" | "conclusion"
```

**Prompt Strategy:**
- Instruct LLM to find the most insightful/actionable passages
- Require diversity (don't cluster snippets from one section)
- Self-contained: each snippet understandable without the full article
- Short articles (< 1000 words): 3 snippets
- Medium articles (1000-5000 words): 5 snippets
- Long articles (> 5000 words): 7 snippets

**Acceptance Criteria:**
- Extracts meaningful snippets from various article types
- Output validates against schema
- Handles short and long articles gracefully
- Cost per article < $0.01 (Gemini Flash)

---

### Story 12.3: Pipeline Integration

**Goal:** Feed extracted snippets through existing normalize → embed → Firestore pipeline.

**Changes to:** `src/ingest/main.py`, `src/normalize/transformer.py`

**Tasks:**
1. [ ] Transform snippets into same markdown format as highlights
2. [ ] Add `source_type: auto-snippet` to frontmatter
3. [ ] Create/update source document in `sources` collection
4. [ ] Embed snippets via existing embedding function
5. [ ] Store in `kb_items` with snippet-specific metadata
6. [ ] Trigger existing post-processing (knowledge cards, relationships, problem matching)
7. [ ] Integration tests with Firestore emulator

**Key Decision:** Snippets become regular `kb_items`. No new collection, no new MCP tools. They're searchable via `search_kb` immediately.

**Acceptance Criteria:**
- Auto-snippets appear in `search_kb` results
- Source created with `source_type: "auto-snippet"`
- Knowledge cards generated for snippets
- Problem matching works for new snippets
- Existing pipeline not affected

---

### Story 12.4: Nightly Trigger & Tag Management

**Goal:** Automated nightly execution with Reader tag lifecycle.

**Changes to:** `terraform/`, `src/ingest/main.py`

**Tasks:**
1. [ ] Cloud Scheduler job (nightly, e.g., 2:00 AM UTC)
2. [ ] Cloud Function entry point for auto-snippet pipeline
3. [ ] After successful processing: remove `kx-auto-ingest` tag via Reader API
4. [ ] After successful processing: add `kx-processed` tag via Reader API
5. [ ] Idempotency: skip documents already processed (by `reader_doc_id`)
6. [ ] Error handling: don't remove tag if processing fails
7. [ ] Terraform config for scheduler + function
8. [ ] Monitoring: log processed count, errors, costs

**Reader API Tag Management:**
- `PATCH /api/v3/update/{doc_id}` — update tags

**Acceptance Criteria:**
- Runs nightly without manual intervention
- Processed documents get `kx-processed` tag, lose `kx-auto-ingest` tag
- Failed documents retain `kx-auto-ingest` tag for retry
- Duplicate processing prevented
- Terraform manages all infrastructure

---

## Migration Plan

1. **Phase 1 (Stories 12.1-12.2):** Build Reader client + snippet extractor, test locally
2. **Phase 2 (Story 12.3):** Integrate with pipeline, verify snippets in Firestore
3. **Phase 3 (Story 12.4):** Deploy nightly trigger, tag management
4. **Phase 4:** Monitor for 1 week, adjust snippet extraction prompt if needed

**Rollback:** Remove Cloud Scheduler trigger. Snippets already in Firestore remain (harmless, searchable).

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Articles processed per night | 0-20 (depends on tagging) |
| Snippets per article | 3-7 |
| Snippet quality (manual review) | >80% useful |
| Pipeline reliability | >99% success rate |
| Cost per article | < $0.03 |
| End-to-end latency | < 2 min per article |

---

## Open Questions

1. **Tag naming:** `kx-auto-ingest` oder kürzer? (z.B. `kx-ai`, `kx-auto`)
2. **Snippet language:** Articles können EN oder DE sein. Snippets in Originalsprache behalten?
3. **Existing highlights:** Wenn ein Artikel sowohl Highlights als auch Auto-Snippets hat, beide behalten?
4. **Reader categories:** Nur `article` oder auch `book`, `pdf`, `email`?

---

## Summary

| Story | Description | Status |
|-------|-------------|--------|
| 12.1 | Reader API Client | Planned |
| 12.2 | LLM Snippet Extraction | Planned |
| 12.3 | Pipeline Integration | Planned |
| 12.4 | Nightly Trigger & Tag Management | Planned |
