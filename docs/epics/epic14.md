# Epic 14: Evidence-Aware Query Generation

**Goal:** Replace static template-based Tavily queries with LLM-generated, evidence-aware search queries that target actual knowledge gaps.

**Business Value:** The recommendation system is only as good as its search queries. Today, queries like `"How do I maintain my relationship with small children? practical guide insights"` are too generic — Tavily returns top-10 listicles. With 12 active Feynman problems (several with 36–56 evidence items already), the system should know *what you've already read* and search for what's missing.

**Dependencies:** Epic 11 (Problem-Driven Recommendations), Epic 13 (Auto-Snippets)

**Status:** In Progress

---

## Problem Statement

### Current Approach (Template-Based)

```python
# Problem: "Wie pflegen wir als Paar unsere Beziehung mit zwei kleinen Kindern?"
# → translated: "How do we maintain our relationship as a couple with two small children?"
# → template: "{problem} advanced techniques expert insights"
# → query: "How do we maintain our relationship as a couple with two small children? advanced techniques expert insights"
```

**What Tavily returns:** Generic relationship advice, "Top 10 tips for couples with kids", articles the user may have already read.

**Root cause:** The query ignores that the user already has 48 evidence items on this problem — including Gottman's "7 Secrets of Happy Marriage", "The Whole-Brain Child", "Bindung Ohne Burnout". A generic template cannot know this.

### Evidence from Real Problems

| Problem | Evidence Items | Current Query Quality |
|---------|---------------|----------------------|
| Wie pflegen wir als Paar... | 48 | ❌ Generic relationship advice |
| Veränderungen in großen Org... | 56 | ❌ Generic change management |
| Als Vater präsent bleiben | 36 | ❌ Generic parenting tips |
| Karriere langfristig positionieren | 22 | ❌ Generic career advice |
| Kulturelle Grenzen führen | 16 | ❌ Already-read Culture Map topics |

---

## Solution: LLM-Generated Gap-Targeted Queries

### Core Idea

Give the LLM context about what the user **already knows**, and ask it to generate queries for what's **missing**.

```
Input to LLM:
  Problem: "How do we maintain our relationship as a couple with two small children?"

  Already read (existing evidence):
    - Die 7 Geheimnisse der glücklichen Ehe (Gottman)
    - Bindung Ohne Burnout (Szalavitz)
    - The Whole-Brain Child (Siegel)
    - Verbindung Ehe und Komplexität
    - ... (top 5 by recency)

  Mode: deepen

  Generate 2 precise Tavily search queries that:
  - Target gaps NOT covered by existing evidence
  - Are specific enough to avoid generic top-10 lists
  - Use search-optimized keywords (not natural language questions)

Output:
  → "couples therapy communication repair attempts Gottman beyond"
  → "parenting stress relationship satisfaction longitudinal study"
```

**vs. current:**
```
  → "How do we maintain our relationship... advanced techniques expert insights"  ❌ generic
```

### Mode-Specific Prompting

| Mode | Prompt Instruction |
|------|--------------------|
| `deepen` | "Target advanced/niche aspects not in existing evidence. Assume user knows the basics." |
| `explore` | "Target adjacent fields and contrarian perspectives the user hasn't encountered." |
| `balanced` | "Mix: one gap-filling query, one perspective-expanding query." |

---

## Story 14.1: LLM Query Generation

**Status:** In Progress

### Implementation

New function `generate_evidence_queries()` in `recommendation_problems.py`:

```python
def generate_evidence_queries(
    problem_en: str,
    evidence_sources: List[Dict[str, Any]],
    mode: str,
    n_queries: int = 2,
) -> List[str]:
    """
    Use LLM to generate evidence-aware search queries.

    Falls back to template queries on any error.
    Cost: ~150-200 tokens (Gemini Flash) = ~$0.00003 per problem per job.
    """
```

### Prompt Design

```
You are generating web search queries for a research tool (Tavily).

RESEARCH PROBLEM: "{problem}"

WHAT THE USER ALREADY KNOWS (do not search for these topics again):
{evidence_summary}

Generate exactly {n} search queries that:
1. Target GAPS not covered by existing evidence
2. Explore specific sub-topics, niche angles, or adjacent fields
3. Are optimized for web search (keywords, not questions — max 8 words each)
4. Will find substantial articles, NOT top-10 listicles or beginner guides

Mode: {mode_instruction}

Return one query per line. No explanations, no numbering.
```

### Integration into `generate_problem_queries()`

```python
# Try LLM-generated queries first, fall back to templates
if evidence_count > 0:
    llm_queries = generate_evidence_queries(
        problem_en=problem_en,
        evidence_sources=problem.get("evidence", [])[:5],
        mode=effective_mode,
        n_queries=queries_per_problem,
    )
    if llm_queries:
        # Use LLM queries
        ...
    else:
        # Fallback to templates
        ...
else:
    # No evidence → templates are fine (nothing to avoid yet)
    ...
```

**Key decision:** LLM queries only when `evidence_count > 0`. For new problems with no evidence, templates are appropriate.

### Tasks

1. [ ] Implement `generate_evidence_queries()` with Gemini Flash
2. [ ] Integrate into `generate_problem_queries()` with template fallback
3. [ ] Add `query_method: "llm" | "template"` field to query dict for observability
4. [ ] Tests: mock LLM, verify fallback behavior, verify query dict structure

---

## Story 14.2: Evidence Summary for Prompt

**Status:** In Progress

### Problem

Passing raw evidence objects to the LLM is token-wasteful. Need a compact summary.

### Evidence Summary Format

```python
def build_evidence_summary(evidence: List[Dict], max_items: int = 5) -> str:
    """
    Build compact evidence summary for LLM prompt.

    Example output:
    - Die 7 Geheimnisse der glücklichen Ehe (Gottman) — couples communication, repair attempts
    - The Whole-Brain Child (Siegel) — child development, emotional regulation
    - Bindung Ohne Burnout (Szalavitz) — attachment theory, parental burnout
    """
```

**Input:** `problem["evidence"]` list (chunk references with source_title, author, takeaways)
**Output:** Compact string, max ~200 tokens

### Tasks

1. [ ] Implement `build_evidence_summary()` using source_title + author + first takeaway
2. [ ] Cap at 5 evidence items (most recent first)
3. [ ] Handle missing fields gracefully (title-only fallback)

---

## Non-Goals

- No new MCP tools or Firestore collections
- No caching of LLM-generated queries (run fresh each job — weekly frequency)
- No A/B testing infrastructure (observe via `query_method` field in logs)

---

## Cost Analysis

| Scenario | Tokens | Cost |
|----------|--------|------|
| 1 problem, 2 queries | ~250 tokens | $0.00004 |
| 12 problems, 2 queries each | ~3,000 tokens | $0.0005 |
| Weekly batch job (12 problems) | ~3,000 tokens | **$0.03/year** |

Negligible. Gemini Flash at $0.15/1M tokens.

---

## Success Metrics

- [ ] Queries contain specific terms from evidence context (not just generic suffixes)
- [ ] Zero regressions in test suite (template fallback works)
- [ ] `query_method: "llm"` logged for problems with evidence
- [ ] Subjective: Weekly recommendations feel more targeted (less generic)

---

## Implementation Notes

- `generate_evidence_queries()` lives in `recommendation_problems.py` (alongside `generate_problem_queries()`)
- Uses same `get_client(model="gemini-flash")` pattern as `translate_to_english()`
- `GenerationConfig(temperature=0.3, max_output_tokens=200)` — low temp for deterministic search queries
- Parse LLM output: split by newline, strip, filter empty lines, cap at `n_queries`
