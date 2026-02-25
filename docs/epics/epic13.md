# Epic 12: Auto-Snippets from Reader

**Goal:** Automatically extract key passages from unread Reader documents tagged `kx-auto`, so they become searchable in the KB without manual highlighting.

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

**Solution:** Tag unread articles with `kx-auto` in Reader. A nightly job fetches the full text and uses Gemini Flash to extract 3-7 key passages as "auto-snippets". These flow through the existing pipeline (embed, store, knowledge cards) and become searchable immediately.

**Example:**
- User saves "How Netflix Reinvented HR" in Reader
- Tags it `kx-auto` (one tap in Reader app)
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
│   &tag=kx-auto                                   │
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
│ Prompt: "Extract {N} key passages from this article.    │
│   (N calculated dynamically: max(2, min(15, words/800)))│
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
│ 4. WRITE BACK TO READWISE (v2 API)                      │
├─────────────────────────────────────────────────────────┤
│ POST /api/v2/highlights/                                │
│   For each snippet:                                     │
│     - text: the key passage                             │
│     - note: LLM-generated context (why it matters)      │
│     - title, author, source_url from Reader metadata    │
│     - highlighted_at: current timestamp                 │
│                                                         │
│ → Snippets appear as highlights in Reader (auto-sync)   │
│ → Remove kx-auto tag from Reader document        │
│ → Add kx-processed tag (audit trail)                    │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ 5. POST-PROCESSING (EXISTING PIPELINE)                  │
├─────────────────────────────────────────────────────────┤
│ → Knowledge Card generation (existing pipeline)         │
│ → Relationship extraction (existing pipeline)           │
│ → Problem matching (existing pipeline)                  │
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
| Reader API (fetch) | $0 | Included in Readwise subscription |
| Snippet extraction (Gemini Flash) | ~$0.01 | Single LLM call, open-ended count |
| Readwise v2 API (write highlights) | $0 | Included in Readwise subscription |
| Embeddings (~10 snippets avg) | ~$0.001 | Vertex AI embedding |
| Knowledge Cards (~10 snippets) | ~$0.04 | Gemini Flash per snippet |
| Firestore writes | ~$0.00001 | Negligible |
| **Total per article** | **~$0.05** | |

At 10 articles/week: **~$2.00/month**

---

## Stories

### Story 13.1: Reader API Client

**Goal:** Fetch documents tagged `kx-auto` with full text content.

**New file:** `src/ingest/reader_client.py`

**Tasks:**
1. [ ] **Reader API v3 client** with auth (reuse existing Readwise API key)
2. [ ] `fetch_tagged_documents(tag="kx-auto")` — list documents with tag
3. [ ] Extract full text from Reader API response (`html_content` field)
4. [ ] HTML → clean text conversion (strip nav, ads, boilerplate) using BeautifulSoup
5. [ ] Extract metadata: title, author, source_url, word_count, reading_time
6. [ ] Store raw response in GCS (same pattern as Readwise ingest)
7. [ ] Rate limiting and retry logic (20 req/min base, 50 req/min for list)
8. [ ] Unit tests with mocked API responses

**Reader API v3 Endpoints:**
- `GET /api/v3/list/?tag=kx-auto&category=article` — list tagged documents
- Response includes `html_content` field with full article HTML

**Acceptance Criteria:**
- Fetches all documents with `kx-auto` tag
- Extracts clean text from HTML content
- Extracts word_count (calculate if not provided by API)
- Raw JSON stored in GCS for audit trail
- Handles pagination, rate limiting, empty results
- Tests pass with mocked API

---

### Story 13.2: LLM Snippet Extraction

**Goal:** Extract key passages from articles using a single LLM call with open-ended count and full-article coverage.

**File:** `src/knowledge_cards/snippet_extractor.py`

**Status:** ✅ Done (simplified 2026-02-25)

**History:** Originally implemented as a 3-stage pipeline (extract candidates → KB enrichment → LLM judge). Simplified to a single-stage approach after testing revealed:
- Long articles (21K+ words) had poor coverage in later sections due to LLM attention degradation
- The KB enrichment and judge stages added complexity without proportional value
- Multiple references to the same topic are actually valuable (no need to deduplicate)

**Current Design:**
- Single LLM call with open-ended extraction (no fixed snippet count)
- Enhanced prompt: "Distribute proportionally across the ENTIRE article"
- LLM decides how many snippets based on article content and length
- Retry logic (2 attempts) for JSON parse errors
- Overflow threshold for extremely long articles (model context window limit)

**Snippet Schema:**
```python
@dataclass
class ExtractedSnippet:
    text: str           # The key passage (2-4 sentences, must be direct quote)
    context: str        # Why this passage matters (1 sentence)
    position: str       # "intro" | "middle" | "conclusion"
```

**Verified Results (21K-word article):**
- 18 snippets extracted (vs 15 with old capped pipeline)
- 18/18 verbatim quotes verified against source text
- Coverage: 0.7% to 99.1% of article (all quintiles represented)

**Acceptance Criteria:**
- Extracts meaningful snippets from various article types
- Snippets are direct quotes (verifiable against source text)
- Full article coverage (intro through conclusion)
- Output validates against schema
- Handles short and long articles gracefully
- Cost per article: ~$0.01 (single Gemini Flash call)

---

### Story 13.3: Write Back to Readwise & Pipeline Integration

**Goal:** Write extracted snippets as Readwise highlights (appear in Reader), then flow through existing pipeline.

**New file:** `src/ingest/readwise_writer.py`
**Changes to:** `src/ingest/main.py`, `src/normalize/transformer.py`

**Tasks:**
1. [ ] **Readwise v2 API client** for creating highlights
2. [ ] `create_highlights(snippets, document_metadata)` → writes to Readwise v2 API
3. [ ] Map snippet fields to Readwise highlight format:
   - `text`: snippet.text (the key passage)
   - `note`: snippet.context (why it matters)
   - `title`, `author`, `source_url`: from Reader metadata
   - `highlighted_at`: current timestamp
4. [ ] Batch highlight creation (max 100 per request per API docs)
5. [ ] Rate limiting: 240 req/min for v2 API (much higher than Reader v3)
6. [ ] Error handling: retry logic, partial success tracking
7. [ ] After successful write: snippets auto-sync to Reader (no additional API call needed)
8. [ ] Transform snippets into same markdown format as highlights for internal storage
9. [ ] Add `source_type: auto-snippet` to frontmatter
10. [ ] Embed snippets via existing embedding function
11. [ ] Store in `kb_items` with snippet-specific metadata
12. [ ] Trigger existing post-processing (knowledge cards, relationships, problem matching)
13. [ ] Integration tests with mocked Readwise v2 API

**Key Design:**
- Snippets written to **Readwise v2 API** as highlights with notes
- Auto-sync to Reader (user sees them as inline highlights)
- Also stored in kx-hub `kb_items` for search/KB features
- No new MCP tools needed - searchable via `search_kb`

**Acceptance Criteria:**
- Snippets appear as highlights in Reader app (with notes in margin)
- Auto-snippets appear in `search_kb` results
- Source created with `source_type: "auto-snippet"`
- Knowledge cards generated for snippets
- Problem matching works for new snippets
- Existing pipeline not affected
- User can edit/delete highlights in Reader UI

---

### Story 13.4: Nightly Trigger & Tag Management

**Goal:** Automated nightly execution with Reader tag lifecycle.

**Changes to:** `terraform/auto_snippets.tf`, `src/ingest/auto_snippets_main.py`

**Tasks:**
1. [ ] Cloud Scheduler job (nightly, e.g., 2:00 AM UTC)
2. [ ] Cloud Function entry point for auto-snippet pipeline
3. [ ] After successful Readwise write: remove `kx-auto` tag via Reader v3 API
4. [ ] After successful Readwise write: add `kx-processed` tag via Reader v3 API
5. [ ] Idempotency: skip documents already processed (check `kb_items` by `reader_doc_id`)
6. [ ] Error handling: don't remove tag if snippet extraction or Readwise write fails
7. [ ] Terraform config for scheduler + function
8. [ ] Monitoring: log processed count, snippet count, errors, costs per article

**API Usage:**
- **Reader v3**: `PATCH /api/v3/update/{doc_id}` for tag management (rate: 50 req/min)
- **Readwise v2**: Highlights already created in Story 13.3

**Acceptance Criteria:**
- Runs nightly without manual intervention
- Processed documents get `kx-processed` tag, lose `kx-auto` tag
- Failed documents retain `kx-auto` tag for retry next night
- Duplicate processing prevented (idempotent)
- User sees highlights in Reader app immediately after processing
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
| Snippets per article | 2-15 (dynamic, based on length) |
| Snippet quality (manual review) | >80% useful |
| Pipeline reliability | >99% success rate |
| Cost per article | < $0.03 |
| End-to-end latency | < 2 min per article |

---

## Open Questions

1. **Tag naming:** `kx-auto` oder kürzer? (z.B. `kx-ai`, `kx-auto`)
2. **Snippet language:** Articles können EN oder DE sein. Snippets in Originalsprache behalten?
3. **Existing highlights:** Wenn ein Artikel sowohl Highlights als auch Auto-Snippets hat, beide behalten?
4. **Reader categories:** Nur `article` oder auch `book`, `pdf`, `email`?

---

## Summary

| Story | Description | Status |
|-------|-------------|--------|
| 13.1 | Reader API Client (v3 - fetch documents) | ✅ Done |
| 13.2 | Snippet Extraction (single-stage, open-ended count) | ✅ Done (simplified 2026-02-25) |
| 13.3 | Write Back to Readwise (v2 API) + Pipeline Integration | ✅ Done |
| 13.4 | Nightly Trigger & Tag Management | ✅ Done |
