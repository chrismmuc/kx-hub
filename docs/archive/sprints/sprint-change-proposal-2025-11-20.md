# Sprint Change Proposal - URL Link Storage Enhancement

**Date:** 2025-11-20
**Project:** kx-hub - Personal AI Knowledge Base
**Change Scope:** Minor (Direct Adjustment)
**Proposed By:** Product Manager (PM Agent)
**Approved By:** Chris (2025-11-20)

---

## 1. Issue Summary

### Problem Statement

The current kx-hub system does not capture or store URL links from the Readwise API, despite this data being available in the raw JSON responses. This creates a gap in traceability, preventing users from easily navigating back to the original Readwise highlights or source articles from Claude Desktop MCP search results.

### Context

During usage of the MCP server with Claude Desktop, it was identified that search results lack clickable URLs back to Readwise or original sources. Investigation revealed:

1. Readwise API provides three URL fields:
   - `readwise_url`: Book review URL (always present)
   - `source_url`: Original source URL (nullable, often null for books)
   - Highlight-level `readwise_url`: Per-highlight URL for detailed view

2. Current pipeline captures raw JSON but does NOT extract or store URLs
3. Firestore `kb_items` schema lacks URL fields
4. MCP server cannot return URLs because they're not in the database

### Evidence

- **API Sample Data**: `tests/fixtures/sample-book.json` shows URLs available in raw JSON
- **Firestore Inspection**: Current documents lack any URL fields
- **User Need**: Ability to "open in Readwise" from Claude Desktop search results

---

## 2. Impact Analysis

### Epic Impact

**Epic 2: Enhanced Knowledge Graph & Clustering** - Minor additive impact

- **Action Required**: Add Story 2.7 after Story 2.6 (currently in review)
- **Epic Goal**: Unchanged - still focused on knowledge graph capabilities
- **Epic Completion**: Extends from 6 stories to 7 stories (14% scope increase)
- **Timeline Impact**: +2-3 days for implementation + backfill

**Epic 3 & Beyond**: No impact - this is foundational data that benefits all future features

### Story Impact

**Existing Stories**: No modifications needed - this is purely additive

**New Story Required**:
- **Story 2.7**: URL Link Storage & Backfill
  - Extend Firestore data model
  - Update pipeline functions (normalize + embed)
  - Enhance MCP server responses
  - Create backfill script for existing 825+ chunks

### Artifact Conflicts

#### PRD (docs/prd.md)
- **Section 5 - Data Model**: Minor clarification needed
- **Impact Level**: Low
- **Change**: Explicitly list URL fields in Firestore schema description

#### Architecture (docs/architecture.md + docs/architecture/chunk-schema.md)
- **Firestore Schema**: Moderate update needed
- **Pipeline Flow**: Minor notation update
- **MCP Server**: Documentation update for tool responses
- **Impact Level**: Moderate
- **Changes**:
  - Add 3 URL fields to `kb_items` schema
  - Update pipeline diagrams to show URL extraction
  - Document URL availability in MCP responses

#### Code Impact
- **Normalize Function** (`src/normalize/transformer.py`): Already extracts `readwise_url` to markdown frontmatter, needs to add `source_url` and `highlight_url`
- **Embed Function** (`functions/embed/main.py`): Add URL fields to Firestore document writes
- **MCP Server Tools** (`src/mcp_server/tools.py`): Include URLs in search result formatting
- **Backfill Script**: New file `src/scripts/backfill_urls.py`

### Technical Impact

**Cost**: Zero increase - uses existing Firestore data and API responses

**Performance**: Negligible - 3 additional string fields per document (~100 bytes)

**Breaking Changes**: None - purely additive

**Data Migration**: Backfill required for 825+ existing chunks (estimated <5 minutes)

---

## 3. Recommended Approach

### Selected Path: **Option 1 - Direct Adjustment**

Add Story 2.7 to Epic 2 and implement as straightforward pipeline enhancement with backfill script.

### Rationale

1. **Low Risk**: Additive changes only, no breaking changes to existing functionality
2. **High Value**: Closes data model gap, enables traceability, supports future features
3. **Natural Fit**: Aligns perfectly with Epic 2's focus on knowledge graph enhancements
4. **Quick Implementation**: 2-3 days of work, minimal complexity
5. **Maintains Momentum**: No need to pause or replan, direct implementation path

### Effort Estimate

- **Development**: 1-2 days
  - Update pipeline functions: 4 hours
  - Update MCP server: 2 hours
  - Create backfill script: 2 hours
  - Testing: 2 hours
- **Backfill Execution**: 5 minutes (one-time)
- **Documentation**: 2 hours

**Total**: 2-3 days (12-16 hours)

### Risk Assessment

**Overall Risk: Low**

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| source_url often null | High | Low | Handle gracefully, mark as nullable field |
| Backfill script failure | Low | Medium | Test with small batch first, idempotent design |
| MCP breaking changes | Very Low | Low | Additive changes only, backward compatible |

### Timeline Impact

- Epic 2 extends by 2-3 days
- No impact to Epic 3 or future work
- Acceptable tradeoff for data completeness

---

## 4. Detailed Change Proposals

### Change 1: Add Story 2.7 to Epic 2

**File**: `docs/epics.md`
**Location**: After Story 2.6 (line ~375), before Epic 3
**Action**: INSERT

**Content**:
```markdown
### Story 2.7: URL Link Storage & Backfill

**Status:** Drafted

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
```

---

### Change 2: Update Sprint Status Tracking

**File**: `docs/sprint-status.yaml`
**Location**: After Story 2-6 (line ~93), before Epic 3 section
**Action**: INSERT

**Content**:
```yaml
  2-7-url-link-storage:
    status: backlog
    story_file: docs/stories/2.7-url-link-storage.md
    notes: "Capture URL links from Readwise API, extend data model, backfill existing chunks"
```

---

### Change 3: Update PRD Data Model

**File**: `docs/prd.md`
**Section**: Section 5 - Data Model (line ~42)
**Action**: REPLACE

**OLD**:
```markdown
**Firestore `kb_items`**: Document ID = item_id, fields: title, url, tags, authors, created_at, updated_at, cluster_id[], similar_ids[], scores[].
```

**NEW**:
```markdown
**Firestore `kb_items`**: Document ID = item_id, fields: title, readwise_url, source_url, highlight_url, tags, authors, created_at, updated_at, cluster_id[], similar_ids[], scores[], knowledge_card {summary, takeaways}.
```

**Rationale**: Explicitly clarifies URL field names and includes knowledge_card (already implemented in Story 2.1)

---

### Change 4: Update Firestore Schema Documentation

**File**: `docs/architecture/chunk-schema.md`
**Section**: Field Specifications table (after line ~82)
**Action**: INSERT

**Content**:
```markdown
| `readwise_url` | string | ✅ | Readwise book review URL |
| `source_url` | string | ❌ | Original source URL (nullable - many books lack this) |
| `highlight_url` | string | ❌ | Readwise highlight-specific URL (optional for traceability) |
```

**Also Update**: Index Requirements section to include:
```
5. URL Search (Optional)
   Fields: (readwise_url)
   Purpose: Fast lookup by Readwise URL for deduplication or updates
```

---

### Change 5: Update Architecture Pipeline Flow

**File**: `docs/architecture.md`
**Section**: Batch Processing Pipeline description (line ~28-32)
**Action**: REPLACE

**OLD**:
```markdown
2) Normalize → **Cloud Storage (markdown)** (+ Frontmatter)
3) Embed & Store (Vertex AI `gemini-embedding-001`) → **Firestore kb_items** (with embeddings)
```

**NEW**:
```markdown
2) Normalize → **Cloud Storage (markdown)** (+ Frontmatter with URLs)
3) Embed & Store (Vertex AI `gemini-embedding-001`) → **Firestore kb_items** (with embeddings + URLs)
```

**Rationale**: Clarifies URL extraction happens during normalize, storage during embed

---

### Change 6: Document MCP URL Fields

**File**: `docs/mcp-server-usage.md` (create if doesn't exist) OR add to `docs/architecture.md` MCP section
**Section**: New section "URL Fields in Search Results"
**Action**: INSERT

**Content**:
```markdown
### URL Fields in Search Results

All MCP search tools now return URL fields for traceability:

- `readwise_url`: Link to book review in Readwise (always present)
- `source_url`: Link to original source (may be null for some books)
- `highlight_url`: Link to specific highlight in Readwise (optional)

**Example Response:**
```json
{
  "chunk_id": "41094950-chunk-003",
  "title": "Geschwister Als Team",
  "author": "Nicola Schmidt",
  "readwise_url": "https://readwise.io/bookreview/41094950",
  "source_url": null,
  "highlight_url": "https://readwise.io/open/727604197",
  "content": "..."
}
```

**Usage in Claude Desktop:**
Users can click URLs to open highlights in Readwise web interface for annotation, sharing, or further exploration.
```

---

## 5. Implementation Handoff

### Change Scope Classification: **Minor**

This change can be implemented directly by the development team without backlog reorganization or fundamental replanning.

### Handoff Recipients

**Primary**: Development Team (Dev Agent)
- Implement Story 2.7 following standard story workflow
- Execute backfill script after deployment

**Supporting**: Scrum Master (SM Agent)
- Create Story 2.7 draft using create-story workflow
- Track story through sprint-status.yaml
- Coordinate with Dev Agent for implementation

### Implementation Steps

1. **SM Agent**: Run `create-story` workflow to generate Story 2.7 draft
2. **SM Agent**: Update sprint-status.yaml to mark Story 2.7 as "drafted"
3. **SM Agent**: Run `story-context` workflow to prepare technical context
4. **Dev Agent**: Implement Story 2.7 following acceptance criteria
5. **Dev Agent**: Execute backfill script to populate existing chunks
6. **Dev Agent**: Mark story complete, update sprint-status.yaml to "done"

### Success Criteria

**Implementation Complete When**:
- [ ] All 6 documentation changes applied (epics.md, sprint-status.yaml, prd.md, architecture.md, chunk-schema.md, mcp-server-usage.md)
- [ ] Pipeline functions extract and store URLs (normalize + embed)
- [ ] MCP server returns URLs in search results
- [ ] Backfill script successfully updates 825+ existing chunks
- [ ] All tests pass (unit tests for URL extraction and storage)
- [ ] Zero cost increase verified
- [ ] Story 2.7 marked "done" in sprint-status.yaml

---

## 6. Deliverables Summary

### Artifacts Modified
1. docs/epics.md (Story 2.7 added)
2. docs/sprint-status.yaml (Story 2.7 tracked)
3. docs/prd.md (Data model clarified)
4. docs/architecture.md (Pipeline flow updated)
5. docs/architecture/chunk-schema.md (Schema extended)
6. docs/mcp-server-usage.md (URL fields documented)

### Code Changes Required
1. src/normalize/transformer.py (Extract URLs from raw JSON)
2. functions/embed/main.py (Store URLs in Firestore)
3. src/mcp_server/tools.py (Include URLs in responses)
4. src/scripts/backfill_urls.py (New: Backfill script)
5. tests/* (Unit tests for URL handling)

### One-Time Operations
1. Execute backfill script: `python3 -m src.scripts.backfill_urls`
2. Verify backfill completion: Check Firestore documents have URL fields

---

## 7. Approval & Next Steps

### Approval Status

- [x] **User Approval**: Approved by Chris (2025-11-20)
- [ ] **Technical Review**: Not Required (Minor scope)
- [ ] **Stakeholder Sign-off**: Not Required (Internal enhancement)

### Upon Approval

**Immediate Actions**:
1. Apply all 6 documentation changes to project files
2. Hand off to SM Agent to create Story 2.7
3. SM Agent creates story context and marks ready for development
4. Dev Agent implements Story 2.7

**Expected Timeline**:
- Documentation updates: Immediate (1 hour)
- Story creation: 30 minutes
- Development + backfill: 2-3 days
- Total: 3-4 days to completion

---

## Appendix: Checklist Status

### Section 1: Trigger and Context ✅
- [x] 1.1 - Triggering story identified (Proactive enhancement during usage)
- [x] 1.2 - Core problem defined (URLs not captured from Readwise API)
- [x] 1.3 - Evidence gathered (API sample data, Firestore inspection)

### Section 2: Epic Impact ✅
- [x] 2.1 - Current epic evaluated (Epic 2 - minor additive impact)
- [x] 2.2 - Epic changes determined (Add Story 2.7)
- [x] 2.3 - Future epics reviewed (No impact)
- [x] 2.4 - New epics assessed (None needed)
- [x] 2.5 - Epic priorities considered (No resequencing needed)

### Section 3: Artifact Conflicts ✅
- [x] 3.1 - PRD conflicts checked (Minor clarification needed)
- [x] 3.2 - Architecture reviewed (Moderate updates needed)
- [x] 3.3 - UI/UX examined (N/A - no UI)
- [x] 3.4 - Other artifacts considered (Tests, documentation)

### Section 4: Path Forward ✅
- [x] 4.1 - Direct Adjustment evaluated (VIABLE - recommended)
- [x] 4.2 - Rollback evaluated (NOT VIABLE)
- [x] 4.3 - MVP Review evaluated (NOT VIABLE)
- [x] 4.4 - Path selected (Direct Adjustment with rationale)

### Section 5: Proposal Components ✅
- [x] 5.1 - Issue summary created
- [x] 5.2 - Epic/artifact impacts documented
- [x] 5.3 - Recommended path presented with rationale
- [x] 5.4 - MVP impact and action plan defined
- [x] 5.5 - Agent handoff plan established

### Section 6: Final Review ✅
- [x] 6.1 - Checklist completion verified
- [x] 6.2 - Proposal accuracy confirmed
- [ ] 6.3 - User approval pending
- [ ] 6.4 - Next steps confirmation pending

---

**End of Sprint Change Proposal**
