# Epic 11: Problem-Driven Recommendations

**Goal:** Transform reading recommendations from "more of the same" (based on reading history) to "what helps me grow" (aligned with Feynman problems). Integrate knowledge graph relationships for enhanced context.

**Business Value:**
- Recommendations directly address user's explicit learning goals (problems)
- Two modes: "deepen" (go deeper on topics with evidence) vs "explore" (fill knowledge gaps)
- Graph connections surface relationships to existing knowledge
- More relevant recommendations → higher engagement

**Dependencies:**
- Epic 7 (Async Recommendations infrastructure)
- Epic 10 (Feynman Problems)
- Epic 4 (Knowledge Graph)

**Status:** Planned

---

## Problem Statement

Current recommendations (Epic 3.5 / Epic 7) are based on:
- Recent read themes (tags from last 14 days)
- Top sources (by chunk count)
- Knowledge card takeaways

**Problems:**
1. Recommends "more of the same" instead of what user *wants* to learn
2. No connection to explicit problems/goals
3. Ignores knowledge graph relationships
4. Can't distinguish between "deepen existing knowledge" vs "explore new areas"

**Example:**
- User has Problem: "Wie führe ich über kulturelle Grenzen?"
- User has Evidence: "The Culture Map" by Erin Meyer
- Current system: Recommends random tech articles based on tags
- New system: Recommends "Beyond The Culture Map" (EXTENDS existing evidence)

---

## Architecture

### Input/Output Design (Token-Efficient)

**Input Parameters:**
```python
recommendations(
    problems: Optional[List[str]] = None,  # Filter to specific problem_ids
    mode: str = "balanced",                 # "deepen" | "explore" | "balanced"
    limit: int = 5
)
```

**Output (Compact):**
```json
{
  "mode": "balanced",
  "recommendations": [
    {
      "title": "Beyond The Culture Map",
      "url": "https://...",
      "problem": "Wie führe ich über kulturelle Grenzen?",
      "problem_id": "prob_5b0f74d5b79b",
      "type": "deepen",
      "evidence_count": 3,
      "why": "Builds on: Erin Meyer",
      "graph": {
        "relation": "extends",
        "connects_to": "The Culture Map",
        "author_in_kb": true
      }
    }
  ],
  "stats": {
    "problems_queried": 12,
    "candidates": 47,
    "filtered": 42
  }
}
```

**Token Budget:** ~80 tokens per recommendation (vs ~500 currently)

### Flow

```
┌─────────────────────────────────────────────────────────┐
│ 1. PROBLEM SELECTION                                    │
├─────────────────────────────────────────────────────────┤
│ if problems: use those                                  │
│ else: get all active problems                           │
│                                                         │
│ Sort by evidence_count:                                 │
│   deepen  → high evidence first                         │
│   explore → low evidence first                          │
│   balanced → interleaved                                │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ 2. QUERY GENERATION (per Problem)                       │
├─────────────────────────────────────────────────────────┤
│ Translate problem to English (for Tavily)               │
│                                                         │
│ deepen queries:                                         │
│   "{problem_en} {evidence_keywords} deep dive"          │
│   "{problem_en} advanced techniques"                    │
│                                                         │
│ explore queries:                                        │
│   "{problem_en} getting started guide"                  │
│   "{problem_en} different perspectives"                 │
│   "{problem_en} contrarian view"                        │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ 3. TAVILY SEARCH                                        │
├─────────────────────────────────────────────────────────┤
│ Execute queries via Tavily API                          │
│ Collect candidate URLs with metadata                    │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ 4. GRAPH-ENHANCED FILTERING                             │
├─────────────────────────────────────────────────────────┤
│ For each candidate:                                     │
│   • Check: Already in problem's evidence? → Skip        │
│   • Check: Author/Source in KB? → Get relationships     │
│   • Check: Relates to evidence sources?                 │
│     - extends → boost for deepen mode                   │
│     - contradicts → boost for explore mode              │
│     - supports → moderate boost                         │
│   • LLM depth scoring (existing)                        │
│   • KB deduplication (existing)                         │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ 5. RANKING & OUTPUT                                     │
├─────────────────────────────────────────────────────────┤
│ Rank by: problem_relevance + graph_bonus + depth        │
│ Assign type: "deepen" or "explore"                      │
│ Generate compact output                                 │
└─────────────────────────────────────────────────────────┘
```

### Mode Definitions

| Mode | Problem Selection | Query Style | Graph Preference |
|------|-------------------|-------------|------------------|
| **deepen** | High evidence first | Advanced, deep dive | `extends`, `supports` |
| **explore** | Low evidence first | Getting started, contrarian | `contradicts`, new sources |
| **balanced** | Interleaved | Mixed | All relationship types |

---

## Stories

### Story 11.1: Problem-Based Query Generation

**Goal:** Replace tag/source-based queries with problem-based queries.

**Changes:**
- New file: `recommendation_problems.py`
- Translate problems to English using Gemini Flash
- Generate mode-appropriate queries per problem
- Cache translations (problems don't change often)

**Tasks:**
1. [ ] Create `recommendation_problems.py` with query generation
2. [ ] Add `translate_to_english()` using Gemini Flash
3. [ ] Implement `generate_problem_queries(problems, mode)`
4. [ ] Add query templates for deepen/explore modes
5. [ ] Unit tests

**Acceptance Criteria:**
- German problem → English query transformation works
- Deepen mode generates "advanced/deep dive" queries
- Explore mode generates "getting started/contrarian" queries

---

### Story 11.2: Graph-Enhanced Filtering

**Goal:** Use knowledge graph to enhance recommendation relevance.

**Changes:**
- Extend `recommendation_filter.py`
- Add graph lookup for candidate recommendations
- Score based on relationships to evidence sources

**Tasks:**
1. [ ] Add `get_graph_context(url, author, problem_evidence)` function
2. [ ] Check if author/source exists in KB
3. [ ] Find relationships to problem's evidence sources
4. [ ] Calculate graph_bonus based on relationship types
5. [ ] Add `graph` field to recommendation output
6. [ ] Unit tests

**Graph Bonus Logic:**
```python
graph_bonus = 0.0
if relation == "extends" and mode == "deepen":
    graph_bonus = 0.3
elif relation == "contradicts" and mode == "explore":
    graph_bonus = 0.3
elif relation == "supports":
    graph_bonus = 0.15
elif author_in_kb:
    graph_bonus = 0.1
```

**Acceptance Criteria:**
- Recommendations show graph connections when found
- Deepen mode boosts "extends" relationships
- Explore mode boosts "contradicts" relationships

---

### Story 11.3: Updated MCP Tool Interface

**Goal:** Update `recommendations` tool with problem-driven parameters.

**Changes:**
- Modify `recommendations()` in `tools.py`
- Add `problems` and `mode` parameters
- Update output format for token efficiency
- Keep backwards compatibility (no params = balanced, all problems)

**New Interface:**
```python
@tool
def recommendations(
    job_id: str = None,           # For polling (existing)
    problems: List[str] = None,   # NEW: Filter to specific problem_ids
    mode: str = "balanced",       # NEW: "deepen" | "explore" | "balanced"
    limit: int = 5                # Existing
) -> Dict[str, Any]:
    """Get reading recommendations aligned with your Feynman problems."""
```

**Tasks:**
1. [ ] Update tool signature and docstring
2. [ ] Modify `_get_reading_recommendations()` to use problem-based queries
3. [ ] Update output format (compact, with graph context)
4. [ ] Update `recommendations_history()` to show problem associations
5. [ ] Update server.py tool definition
6. [ ] Integration tests

**Acceptance Criteria:**
- `recommendations()` works without parameters (backwards compatible)
- `recommendations(problems=["prob_123"])` filters correctly
- `recommendations(mode="deepen")` changes query and ranking behavior
- Output is token-efficient (~80 tokens/recommendation)

---

### Story 11.4: Evidence Deduplication

**Goal:** Don't recommend content already in problem's evidence.

**Tasks:**
1. [ ] Before Tavily search, collect all evidence URLs per problem
2. [ ] Filter out candidates matching existing evidence URLs
3. [ ] Filter out candidates with high embedding similarity to evidence
4. [ ] Track "already_evidence" in filtered_out stats

**Acceptance Criteria:**
- Content already matched as evidence is not recommended
- Stats show how many candidates were filtered as duplicates

---

## Migration Plan

1. **Phase 1 (Story 11.1-11.2):** Build new query generation and filtering
2. **Phase 2 (Story 11.3):** Update MCP tool, keep old logic as fallback
3. **Phase 3 (Story 11.4):** Add evidence deduplication
4. **Phase 4:** Remove old tag/source-based query generation

**Backwards Compatibility:**
- `recommendations()` without params continues to work
- Falls back to balanced mode with all active problems
- `topic` parameter deprecated (use `problems` instead)

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Recommendations per problem | 0 (no connection) | 3-5 |
| Graph connections shown | 0% | >30% |
| Token cost per recommendation | ~500 | ~80 |
| User relevance (subjective) | Low | High |

---

## Open Questions

1. **Translation caching:** Store English translations in problem document?
2. **Problem prioritization:** Should frequently-accessed problems get more recommendations?
3. **Cross-problem recommendations:** What if one article helps multiple problems?

---

## Summary

| Story | Description | Status |
|-------|-------------|--------|
| 11.1 | Problem-Based Query Generation | Planned |
| 11.2 | Graph-Enhanced Filtering | Planned |
| 11.3 | Updated MCP Tool Interface | Planned |
| 11.4 | Evidence Deduplication | Planned |
