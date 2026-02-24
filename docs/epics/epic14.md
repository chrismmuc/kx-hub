# Epic 14: Evidence-Aware Query Generation

**Goal:** Replace static template queries with LLM-generated, evidence-aware Tavily search queries that target knowledge gaps instead of re-discovering what the user already knows.

**Value:** The recommendation system's quality is bottlenecked by query quality. With 12 active problems (many with 16–56 evidence items), the system has enough context to search *smarter* — but today's templates ignore it entirely.

**Dependencies:** Epic 11 (Problem-Driven Recommendations)

**Status:** Planned

---

## Problem

### Current: Template-Based Queries

`generate_problem_queries()` in `recommendation_problems.py:249` builds queries like:

```
"{problem_en} advanced techniques expert insights"
"{problem_en} deep dive comprehensive guide"
```

For deepen mode, `get_evidence_keywords()` (line 176) appends keywords extracted from source titles — but these are just word fragments (>4 chars from title splits), not semantic understanding.

**Result:** Tavily returns generic "Top 10 tips" articles and topics the user has already read extensively.

| Problem | Evidence | Query Quality |
|---------|----------|---------------|
| Wie pflegen wir als Paar... | 48 | Generic relationship advice |
| Veränderungen in großen Org... | 56 | Generic change management |
| Als Vater präsent bleiben | 36 | Generic parenting tips |

### Target: LLM-Generated Gap Queries

Give the LLM the problem + what the user already knows → generate queries for what's *missing*.

```
Input:
  Problem: "How do we maintain our relationship as a couple with two small children?"
  Already read: Gottman (couples communication), Siegel (child development), Szalavitz (attachment)
  Mode: deepen

Output:
  → "couples relationship repair rituals postpartum longitudinal research"
  → "parenting division labor egalitarian marriage satisfaction study"
```

---

## Implementation

### What changes

**New function:** `generate_evidence_queries()` — uses Gemini Flash to generate gap-targeted queries.

**Modified function:** `generate_problem_queries()` — tries LLM queries first when `evidence_count > 0`, falls back to templates on error or when no evidence exists.

**Replaced:** `get_evidence_keywords()` becomes unused (templates + keyword-appending are the fallback path, but the LLM path generates complete queries). Keep it for the template fallback.

**New field in query dict:** `query_method: "llm" | "template"` for observability.

### New function: `generate_evidence_queries()`

Location: `recommendation_problems.py`, next to `translate_to_english()`.

```python
def generate_evidence_queries(
    problem_en: str,
    evidence: List[Dict[str, Any]],
    mode: str,
    n_queries: int = 2,
) -> List[str]:
    """
    Use LLM to generate evidence-aware search queries.
    Returns list of query strings, or empty list on failure (triggers template fallback).
    """
```

**Prompt constraints:**
- Include problem text (English, already translated upstream)
- Include compact evidence summary: up to 5 items, format `"- {source_title} ({author}) — {first_takeaway}"`
- Mode instruction: deepen → "advanced/niche, assume user knows basics"; explore → "adjacent fields, contrarian views"; balanced → "one gap-filling, one perspective-expanding"
- Output format: one query per line, no numbering, max 8 words each
- `GenerationConfig(temperature=0.3, max_output_tokens=200)`

**Evidence summary** is built inline (a small helper `_build_evidence_summary()`), not a separate story. It extracts from `evidence[i]`: `source_title`, `author`, first entry of `takeaways` if available. Cap at 5 items, most recent first. ~100-150 tokens.

### Modified: `generate_problem_queries()`

```python
# In the per-problem loop (line 327), before template generation:
if evidence_count > 0:
    llm_queries = generate_evidence_queries(
        problem_en=problem_en,
        evidence=problem.get("evidence", []),
        mode=effective_mode,
        n_queries=queries_per_problem,
    )
    if llm_queries:
        for q in llm_queries:
            queries.append({
                "query": q,
                "problem_id": problem_id,
                "problem_text": problem_text,
                "problem_en": problem_en,
                "mode": effective_mode,
                "evidence_count": evidence_count,
                "query_method": "llm",
            })
        continue  # skip template generation for this problem

# Existing template code stays as fallback (add "query_method": "template")
```

**Key decisions:**
- LLM queries only when `evidence_count > 0`. New problems with no evidence get templates (nothing to avoid yet).
- On LLM failure → seamless fallback to existing template path, no error surfaced to user.
- `BALANCED_TEMPLATES` stays but is only used as fallback. In the LLM path, balanced mode instructs the LLM to mix gap-filling + perspective-expanding.

---

## Tasks

1. [ ] Implement `_build_evidence_summary(evidence, max_items=5) -> str`
2. [ ] Implement `generate_evidence_queries()` with Gemini Flash + fallback to `[]`
3. [ ] Modify `generate_problem_queries()` to try LLM first, add `query_method` field
4. [ ] Tests: mock LLM responses, verify fallback on error, verify `query_method` field, verify evidence summary formatting

---

## Non-Goals

- No new MCP tools or Firestore collections
- No query caching (weekly frequency, negligible cost)
- No A/B testing (observe via `query_method` in logs)
- No removal of template constants (they remain as fallback)

## Cost

~3,000 tokens per weekly batch (12 problems × ~250 tokens each) = **~$0.03/year** with Gemini Flash.

## Success Criteria

- `query_method: "llm"` logged for problems with evidence
- Queries reference specific gaps (not just `"{problem} advanced techniques"`)
- Zero test regressions — template fallback works identically to today
