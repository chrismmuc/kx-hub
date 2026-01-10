# Epic 10: Guided Problem Definition (Feynman Method)

**Goal:** Replace unguided article idea generation with a problem-first approach based on Richard Feynman's "12 Favorite Problems" method. Users define their top problems with hypotheses, and the system analyzes KB content against these problems - with special emphasis on source relationships (extends/supports/contradicts).

**Business Value:**
- Transforms passive knowledge collection into active problem-solving
- Ideas become focused and personally relevant instead of generic
- Source relationships (especially contradictions) become the foundation for unique insights
- Closes the loop: Define Problem → Read → Highlight → Test Hypothesis → Write

**Dependencies:** Epic 4 (Source Relationships), Epic 6 (Article Ideas - will be replaced)

**Status:** Planned

---

## The Feynman Method

> "You have to keep a dozen of your favorite problems constantly present in your mind, although by and large they will lay in a dormant state. Every time you hear or read a new trick or a new result, test it against each of your twelve problems to see whether it helps."
> — Richard Feynman

### Why This Matters

| Current Approach (Unguided) | New Approach (Problem-First) |
|----------------------------|------------------------------|
| Find clusters → Extract takeaways → Generate thesis | Define problem → Search KB → Test hypothesis → Generate thesis |
| No direction, generic results | Focused, personally relevant |
| Ignores what user cares about | Starts with user's top questions |
| Relationships are secondary | Contradictions are gold |

### Core Principle

**No ideas without problem context.** Every article idea must answer one of your defined problems.

---

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. USER DEFINES TOP PROBLEMS                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Problem: "How can engineering teams ship faster without        │    │
│  │           sacrificing quality?"                                 │    │
│  │  Hypothesis: "Feature flags + trunk-based dev + observability"  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  2. SEMANTIC SEARCH KB                                                  │
│     Find chunks/sources relevant to the problem                         │
│     → "deployment", "quality", "velocity", "feature flags"              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3. EXPAND VIA CONNECTIONS (The Key Innovation!)                        │
│                                                                         │
│  For each relevant source, fetch ALL relationships:                     │
│                                                                         │
│  Accelerate ───extends───→ Continuous Delivery                          │
│      │                                                                  │
│      └──contradicts──→ "Move Fast and Break Things" (Article)           │
│                                                                         │
│  Team Topologies ───supports───→ Accelerate                             │
│                                                                         │
│  → Build evidence network with relationship types                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  4. AI ANALYSIS WITH HYPOTHESIS TESTING                                 │
│                                                                         │
│  PROBLEM: {problem}                                                     │
│  HYPOTHESIS: {hypothesis}                                               │
│                                                                         │
│  SUPPORTING EVIDENCE:                                                   │
│  ├── Accelerate: "Elite teams deploy 208x more frequently"              │
│  │   └── extends: Continuous Delivery (adds deployment metrics)         │
│  └── Team Topologies: "Stream-aligned teams reduce handoffs"            │
│       └── supports: Accelerate (confirms team structure impact)         │
│                                                                         │
│  CONTRADICTING EVIDENCE: ⚡ (Most interesting!)                          │
│  └── "Move Fast and Break Things": "Speed requires accepting bugs"      │
│       └── contradicts: Accelerate (different philosophy)                │
│                                                                         │
│  AI OUTPUT:                                                             │
│  - Hypothesis status: PARTIALLY SUPPORTED                               │
│  - Key tension: Speed vs. Quality tradeoff                              │
│  - Unique angle: The contradiction reveals the real question            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  5. ARTICLE IDEA WITH EVIDENCE CHAIN                                    │
│                                                                         │
│  Title: "Feature Flags Don't Guarantee Quality - Here's What Does"      │
│  Thesis: "Feature flags reduce deployment risk by 60%, but only when    │
│           combined with observability. Without monitoring, you're       │
│           just hiding bugs faster."                                     │
│                                                                         │
│  Evidence:                                                              │
│  ├── SUPPORTS: Accelerate (Chapter 4) + Team Topologies                 │
│  ├── CONTRADICTS: "Move Fast" article (shows failure mode)              │
│  └── EXTENDS: Adds observability requirement (my unique insight)        │
│                                                                         │
│  Strength: 0.92 (high due to contradiction = interesting tension)       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Schema

### Problems Collection (NEW)

```
problems/
  {problem_id}:
    # Core definition
    problem: "How can engineering teams ship faster without sacrificing quality?"
    hypothesis: "Feature flags + trunk-based development + observability"

    # Status tracking
    status: "active" | "resolved" | "archived"
    resolution: null | "confirmed" | "refuted" | "refined"
    resolution_notes: "Hypothesis was partially correct, but..."

    # Linked evidence (auto-updated)
    evidence: {
      supporting: [
        {
          source_id: "accelerate",
          chunk_ids: ["chunk_123", "chunk_456"],
          relationship_context: "extends continuous-delivery",
          relevance_score: 0.89
        }
      ],
      contradicting: [
        {
          source_id: "move-fast-article",
          chunk_ids: ["chunk_789"],
          relationship_context: "contradicts accelerate",
          relevance_score: 0.76
        }
      ],
      extending: [
        {
          source_id: "team-topologies",
          chunk_ids: ["chunk_abc"],
          relationship_context: "supports accelerate",
          relevance_score: 0.82
        }
      ]
    }

    # Generated insights (from AI analysis)
    insights: [
      {
        generated_at: timestamp,
        insight: "Die Spannung zwischen Accelerate und 'Move Fast' zeigt...",
        new_sources_analyzed: ["source_xyz"]
      }
    ]

    # Metadata
    tags: ["engineering", "productivity", "devops"]
    created_at: timestamp
    updated_at: timestamp
    last_analyzed_at: timestamp
```

### Article Ideas Collection (MODIFIED)

```
article_ideas/
  {idea_id}:
    # Link to problem (NEW - required)
    problem_id: "prob_001"

    # The idea
    title: "Feature Flags Don't Guarantee Quality"
    thesis: "Feature flags reduce deployment risk, but only with observability"
    unique_angle: "The contradiction between Accelerate and 'Move Fast' reveals..."

    # Evidence chain with relationships (ENHANCED)
    evidence: {
      supporting: [
        {
          source_id: "accelerate",
          chunk_id: "chunk_123",
          quote: "Elite teams deploy 208x more frequently...",
          relationship: {
            type: "extends",
            target_source: "continuous-delivery",
            context: "adds deployment frequency metrics"
          }
        }
      ],
      contradicting: [
        {
          source_id: "move-fast-article",
          chunk_id: "chunk_789",
          quote: "Speed requires accepting some bugs will reach production",
          relationship: {
            type: "contradicts",
            target_source: "accelerate",
            context: "fundamentally different philosophy on quality"
          }
        }
      ],
      extending: [
        {
          source_id: "team-topologies",
          chunk_id: "chunk_abc",
          quote: "Stream-aligned teams reduce cognitive load...",
          relationship: {
            type: "supports",
            target_source: "accelerate",
            context: "confirms team structure impact"
          }
        }
      ]
    }

    # Hypothesis test result (NEW)
    hypothesis_status: "partially_supported" | "supported" | "refuted" | "inconclusive"
    hypothesis_analysis: "The hypothesis is correct for teams with observability, but..."

    # Strength calculation (MODIFIED - contradictions boost score)
    strength: 0.92
    strength_breakdown: {
      contradiction_bonus: 0.4,    # Contradictions = interesting!
      supporting_evidence: 0.25,
      extending_evidence: 0.15,
      relationship_depth: 0.12    # Multi-hop relationships
    }

    # Rest stays the same
    medium_scores: {...}
    status: "suggested" | "accepted" | "rejected" | "converted"
    suggested_at: timestamp
```

---

## Story 10.1: Problems Collection & CRUD

**Status:** Planned

**Summary:** Create the problems collection and basic CRUD operations for defining and managing top problems.

### MCP Tool: `add_problem`

```python
add_problem(
    problem: str,           # The question/problem statement
    hypothesis: str = None, # Optional initial hypothesis
    tags: list = None       # Optional tags for categorization
) -> {
    "problem_id": "prob_001",
    "problem": "How can engineering teams ship faster...",
    "hypothesis": "Feature flags + trunk-based development",
    "status": "active",
    "created_at": "2026-01-10T..."
}
```

**Examples:**
```
# With hypothesis
add_problem(
    problem="How can I maintain deep focus in an open office?",
    hypothesis="Noise-canceling headphones + time-blocking + visual signals"
)

# Without hypothesis (exploratory)
add_problem(
    problem="What makes some books stick while others are forgotten?",
    tags=["learning", "reading"]
)
```

### MCP Tool: `list_problems`

```python
list_problems(
    status: str = "active",  # "active" | "resolved" | "archived" | "all"
    include_evidence_count: bool = True
) -> {
    "problems": [
        {
            "problem_id": "prob_001",
            "problem": "How can engineering teams ship faster...",
            "hypothesis": "Feature flags + trunk-based development",
            "status": "active",
            "evidence_count": {
                "supporting": 5,
                "contradicting": 2,
                "extending": 3
            },
            "last_analyzed_at": "2026-01-09T...",
            "ideas_generated": 2
        }
    ]
}
```

### MCP Tool: `update_problem`

```python
update_problem(
    problem_id: str,
    problem: str = None,      # Update problem statement
    hypothesis: str = None,   # Update/add hypothesis
    status: str = None,       # Change status
    resolution_notes: str = None  # Notes when resolving
) -> {
    "problem_id": "prob_001",
    "updated_fields": ["hypothesis", "status"],
    "status": "resolved"
}
```

### MCP Tool: `archive_problem`

```python
archive_problem(
    problem_id: str,
    resolution: str = None,  # "confirmed" | "refuted" | "refined" | "irrelevant"
    notes: str = None
) -> {
    "problem_id": "prob_001",
    "status": "archived",
    "resolution": "refined",
    "notes": "Original hypothesis was too narrow..."
}
```

### Tasks

1. [ ] Create `problems` Firestore collection with schema
2. [ ] Implement `add_problem` MCP tool
3. [ ] Implement `list_problems` MCP tool
4. [ ] Implement `update_problem` MCP tool
5. [ ] Implement `archive_problem` MCP tool
6. [ ] Add validation (problem not empty, valid status transitions)
7. [ ] Write tests for CRUD operations

### Success Metrics

- Problems can be created, listed, updated, archived
- Evidence counts are accurately tracked
- Status transitions are validated
- Response time < 500ms for all operations

---

## Story 10.2: Problem-KB Matching with Relationships

**Status:** Planned

**Summary:** Semantic search to find relevant KB content for a problem, then expand via source relationships to build a complete evidence network.

### Algorithm

```
1. SEMANTIC SEARCH
   - Embed problem + hypothesis
   - Vector search against chunks
   - Return top N relevant chunks with scores

2. EXTRACT SOURCES
   - Get unique source_ids from matching chunks
   - Fetch source metadata (title, author, chunk_count)

3. EXPAND VIA RELATIONSHIPS (Key Innovation!)
   For each source:
   - Fetch all relationships (extends, supports, contradicts)
   - Add related sources to evidence pool
   - Track relationship type and context

4. CATEGORIZE EVIDENCE
   - Supporting: Sources that align with hypothesis
   - Contradicting: Sources that challenge hypothesis (GOLD!)
   - Extending: Sources that add new dimensions

5. RANK BY RELEVANCE + RELATIONSHIP VALUE
   - Direct semantic match: base score
   - Has contradiction: +0.3 bonus
   - Part of relationship chain: +0.1 bonus
```

### MCP Tool: `analyze_problem`

```python
analyze_problem(
    problem_id: str,
    max_sources: int = 10,
    include_relationships: bool = True,  # Expand via connections
    min_relevance: float = 0.5
) -> {
    "problem_id": "prob_001",
    "problem": "How can engineering teams ship faster...",
    "hypothesis": "Feature flags + trunk-based development",

    "evidence": {
        "supporting": [
            {
                "source_id": "accelerate",
                "source_title": "Accelerate",
                "author": "Forsgren, Humble, Kim",
                "relevance_score": 0.89,
                "chunks": [
                    {
                        "chunk_id": "chunk_123",
                        "quote": "Elite performers deploy 208x more frequently...",
                        "takeaway": "High deployment frequency correlates with stability"
                    }
                ],
                "relationships": [
                    {
                        "type": "extends",
                        "target_source": "continuous-delivery",
                        "context": "Adds empirical metrics to CD principles"
                    }
                ]
            }
        ],
        "contradicting": [
            {
                "source_id": "move-fast-article",
                "source_title": "Move Fast and Break Things",
                "relevance_score": 0.76,
                "chunks": [...],
                "relationships": [
                    {
                        "type": "contradicts",
                        "target_source": "accelerate",
                        "context": "Argues speed requires accepting bugs"
                    }
                ],
                "contradiction_insight": "This challenges the 'no tradeoff' claim in Accelerate"
            }
        ],
        "extending": [...]
    },

    "relationship_graph": {
        "nodes": ["accelerate", "continuous-delivery", "team-topologies", "move-fast"],
        "edges": [
            {"from": "accelerate", "to": "continuous-delivery", "type": "extends"},
            {"from": "team-topologies", "to": "accelerate", "type": "supports"},
            {"from": "move-fast", "to": "accelerate", "type": "contradicts"}
        ]
    },

    "summary": {
        "total_sources": 4,
        "supporting_count": 2,
        "contradicting_count": 1,
        "extending_count": 1,
        "has_interesting_tensions": true,
        "recommendation": "Strong foundation for article - contradiction provides unique angle"
    },

    "analyzed_at": "2026-01-10T..."
}
```

### Relationship Expansion Logic

```python
def expand_via_relationships(source_ids: list, db) -> dict:
    """
    For each source, fetch relationships and categorize.
    Contradictions are most valuable for article ideas.
    """
    evidence = {"supporting": [], "contradicting": [], "extending": []}

    for source_id in source_ids:
        # Get all relationships for this source
        relationships = db.collection("source_relationships") \
            .where("source_id", "==", source_id).get()

        for rel in relationships:
            related_source = get_source(rel.target_source_id)

            if rel.relationship_type == "contradicts":
                # GOLD - contradictions are most interesting
                evidence["contradicting"].append({
                    "source": related_source,
                    "relationship": rel,
                    "value_score": 0.9  # High value
                })
            elif rel.relationship_type == "extends":
                evidence["extending"].append({
                    "source": related_source,
                    "relationship": rel,
                    "value_score": 0.7
                })
            elif rel.relationship_type == "supports":
                evidence["supporting"].append({
                    "source": related_source,
                    "relationship": rel,
                    "value_score": 0.5
                })

    return evidence
```

### Tasks

1. [ ] Implement semantic search for problem text
2. [ ] Build relationship expansion logic
3. [ ] Implement evidence categorization (supporting/contradicting/extending)
4. [ ] Create relationship graph structure
5. [ ] Implement `analyze_problem` MCP tool
6. [ ] Add caching for repeated analyses
7. [ ] Update problem document with evidence links
8. [ ] Write tests with mock relationships

### Success Metrics

- Semantic search returns relevant chunks (>70% precision)
- Relationships are correctly expanded and categorized
- Contradictions are prominently surfaced
- Analysis completes in < 10 seconds
- Evidence is persisted to problem document

---

## Story 10.3: Problem-Based Idea Generation (Replaces 6.1)

**Status:** Planned

**Summary:** Replace unguided `suggest_article_ideas` with problem-first generation. Every idea must link to a problem and include the evidence chain with relationships.

### Key Changes from Story 6.1

| Aspect | Old (6.1) | New (10.3) |
|--------|-----------|------------|
| Input | Cluster detection | Problem ID |
| Direction | Bottom-up (find clusters) | Top-down (test hypothesis) |
| Relationships | Secondary | Central (especially contradictions) |
| Output | Generic thesis | Hypothesis test + evidence chain |
| Strength | Source count based | Contradiction-boosted |

### MCP Tool: `suggest_article_ideas` (REWRITTEN)

```python
suggest_article_ideas(
    # NEW: Problem-first approach
    problem_id: str = None,      # Generate ideas for specific problem

    # OR: Analyze all active problems
    all_problems: bool = False,  # Generate ideas for all active problems

    # Filters
    min_evidence: int = 2,       # Minimum sources in evidence
    require_contradiction: bool = False,  # Only ideas with tensions

    # Output
    limit: int = 3,              # Ideas per problem
    save: bool = True            # Persist to Firestore
) -> {
    "ideas": [
        {
            "idea_id": "idea_001",
            "problem_id": "prob_001",
            "problem": "How can engineering teams ship faster...",

            # Hypothesis test result
            "hypothesis_status": "partially_supported",
            "hypothesis_analysis": "The hypothesis holds for teams with strong observability, but fails without monitoring infrastructure.",

            # The article idea
            "title": "Feature Flags Are Not Enough: The Missing Piece in Deployment Speed",
            "thesis": "Feature flags reduce deployment risk by 60%, but only when combined with observability. Without monitoring, you're just hiding bugs faster.",
            "unique_angle": "The contradiction between Accelerate's 'no tradeoff' claim and the 'Move Fast' philosophy reveals that the real variable is observability maturity.",

            # Evidence chain with relationships
            "evidence": {
                "supporting": [
                    {
                        "source_title": "Accelerate",
                        "author": "Forsgren et al.",
                        "quote": "Elite performers deploy 208x more frequently with 7x lower change failure rate",
                        "relationship": {
                            "type": "extends",
                            "target": "Continuous Delivery",
                            "insight": "Adds empirical validation to CD principles"
                        }
                    }
                ],
                "contradicting": [
                    {
                        "source_title": "Move Fast and Break Things",
                        "quote": "Speed requires accepting that some bugs will reach production",
                        "relationship": {
                            "type": "contradicts",
                            "target": "Accelerate",
                            "insight": "Fundamentally different philosophy - accepts tradeoff that Accelerate denies"
                        },
                        "why_interesting": "This tension is the heart of the article"
                    }
                ],
                "extending": [...]
            },

            # Strength with breakdown
            "strength": 0.92,
            "strength_breakdown": {
                "contradiction_bonus": 0.40,  # Has interesting tension
                "supporting_evidence": 0.25,  # 2 supporting sources
                "extending_evidence": 0.15,   # 1 extending source
                "relationship_depth": 0.12    # Multi-hop connections
            },

            # Best formats
            "medium_scores": {
                "linkedin_article": 0.9,  # Tension = good for discussion
                "blog": 0.85,
                "substack": 0.8
            },

            "suggested_at": "2026-01-10T..."
        }
    ],

    "summary": {
        "problems_analyzed": 1,
        "ideas_generated": 3,
        "ideas_with_contradictions": 2,
        "strongest_idea": "idea_001"
    }
}
```

### Prompt Template (Problem-First)

```python
PROBLEM_BASED_THESIS_PROMPT = """
You are analyzing a user's knowledge base to generate article ideas.

THE USER'S PROBLEM:
{problem}

THE USER'S HYPOTHESIS:
{hypothesis}

EVIDENCE FROM THEIR KNOWLEDGE BASE:

## Supporting Evidence (aligns with hypothesis):
{supporting_evidence}

## Contradicting Evidence (challenges hypothesis): ⚡
{contradicting_evidence}

## Extending Evidence (adds new dimensions):
{extending_evidence}

SOURCE RELATIONSHIPS:
{relationship_graph}

---

YOUR TASK:

1. HYPOTHESIS TEST: Does the evidence support, refute, or partially support the hypothesis?
   - Be specific about what parts are supported/refuted
   - Contradictions are GOLD - they reveal where the interesting story is

2. IDENTIFY THE TENSION: What's the most interesting conflict in the evidence?
   - Contradictions between sources are the best article angles
   - "Source A says X, but Source B says Y" = compelling narrative

3. GENERATE THESIS: Create a concrete, testable claim that:
   - Addresses the user's problem
   - Incorporates the tension from contradicting evidence
   - Goes beyond the original hypothesis (adds nuance from contradictions)

   FORBIDDEN: Vague phrases like "balance is key", "it depends", "holistic approach"
   REQUIRED: Specific claim that can be verified (YES/NO answer possible)

4. UNIQUE ANGLE: Why can only THIS user write this article?
   - What unusual combination of sources do they have?
   - What contradiction have they noticed that others miss?

Respond with JSON:
{
    "hypothesis_status": "supported" | "partially_supported" | "refuted" | "inconclusive",
    "hypothesis_analysis": "The hypothesis is [status] because...",
    "key_tension": "The conflict between [Source A] and [Source B] about [topic]...",
    "title": "Punchy, specific title that hints at the tension",
    "thesis": "Concrete claim with specific details from the evidence",
    "unique_angle": "What makes this user's perspective unique"
}
"""
```

### Strength Calculation (Contradiction-Boosted)

```python
def calculate_idea_strength(evidence: dict) -> tuple[float, dict]:
    """
    Calculate idea strength with bonus for contradictions.
    Contradictions = interesting tensions = better articles.
    """
    breakdown = {}
    score = 0.0

    # CONTRADICTIONS ARE GOLD (highest weight)
    if evidence.get("contradicting"):
        contradiction_count = len(evidence["contradicting"])
        breakdown["contradiction_bonus"] = min(contradiction_count * 0.2, 0.4)
        score += breakdown["contradiction_bonus"]
    else:
        breakdown["contradiction_bonus"] = 0.0

    # Supporting evidence
    supporting_count = len(evidence.get("supporting", []))
    breakdown["supporting_evidence"] = min(supporting_count * 0.1, 0.25)
    score += breakdown["supporting_evidence"]

    # Extending evidence
    extending_count = len(evidence.get("extending", []))
    breakdown["extending_evidence"] = min(extending_count * 0.1, 0.15)
    score += breakdown["extending_evidence"]

    # Relationship depth (multi-hop connections)
    if has_relationship_chains(evidence):
        breakdown["relationship_depth"] = 0.12
        score += 0.12
    else:
        breakdown["relationship_depth"] = 0.0

    # Source diversity bonus
    unique_sources = count_unique_sources(evidence)
    if unique_sources >= 3:
        breakdown["source_diversity"] = 0.08
        score += 0.08

    return min(score, 1.0), breakdown
```

### Tasks

1. [ ] Rewrite `suggest_article_ideas` to require problem_id or all_problems flag
2. [ ] Implement problem-based thesis prompt
3. [ ] Add hypothesis testing logic
4. [ ] Integrate relationship data into evidence structure
5. [ ] Implement contradiction-boosted strength calculation
6. [ ] Update article_ideas schema with problem_id and evidence chain
7. [ ] Remove old cluster-based idea generation code
8. [ ] Update `list_ideas` to show problem context
9. [ ] Write tests for problem-based generation
10. [ ] Migrate existing ideas (add problem_id where possible)

### Success Metrics

- Every generated idea links to a problem
- Ideas with contradictions have higher strength scores
- Thesis statements are specific and testable (no vague language)
- Evidence chain includes relationship context
- Generation time < 15 seconds per problem

---

## Story 10.4: Auto-Connect New Highlights to Problems

**Status:** Planned (Optional - Pipeline Integration)

**Summary:** When new highlights are ingested, automatically test them against active problems and notify if relevant evidence is found.

### Trigger Points

1. **Daily Pipeline**: After new chunks are embedded
2. **Manual**: User can trigger re-analysis

### Algorithm

```
For each new chunk:
  For each active problem:
    1. Semantic similarity check (chunk embedding vs problem embedding)
    2. If similarity > threshold:
       - Add to problem's evidence
       - Determine category (supporting/contradicting/extending)
       - Generate insight if contradiction found
       - Queue notification
```

### MCP Tool: `refresh_problem_evidence`

```python
refresh_problem_evidence(
    problem_id: str = None,  # Specific problem, or all if None
    since_days: int = 7      # Only check recent chunks
) -> {
    "problems_updated": 2,
    "new_evidence_found": [
        {
            "problem_id": "prob_001",
            "new_supporting": 1,
            "new_contradicting": 1,
            "new_extending": 0,
            "highlight": "Found contradiction with existing hypothesis!"
        }
    ]
}
```

### Tasks

1. [ ] Add problem embedding storage (for efficient comparison)
2. [ ] Implement chunk-to-problem relevance check
3. [ ] Add evidence categorization for new chunks
4. [ ] Create `refresh_problem_evidence` MCP tool
5. [ ] Optional: Pipeline integration for auto-refresh
6. [ ] Optional: Notification system for new evidence

### Success Metrics

- New relevant evidence is detected within 24h of ingestion
- False positive rate < 20%
- Contradictions are correctly identified
- Problem evidence stays up-to-date

---

## Story 10.5: Problem Dashboard & Insights

**Status:** Planned

**Summary:** Provide overview of all problems with evidence status, stale detection, and AI-generated insights.

### MCP Tool: `get_problem_dashboard`

```python
get_problem_dashboard() -> {
    "active_problems": 5,
    "problems": [
        {
            "problem_id": "prob_001",
            "problem": "How can engineering teams...",
            "status": "active",
            "health": "strong",  # strong | needs_evidence | stale
            "evidence_summary": {
                "supporting": 3,
                "contradicting": 1,
                "extending": 2
            },
            "last_new_evidence": "2026-01-08",
            "ideas_generated": 2,
            "ideas_accepted": 1,
            "recommendation": "Ready for article - strong contradiction found"
        }
    ],
    "insights": [
        {
            "type": "new_contradiction",
            "problem_id": "prob_001",
            "message": "New source 'Scaling Teams' contradicts your hypothesis about feature flags"
        },
        {
            "type": "stale_problem",
            "problem_id": "prob_003",
            "message": "No new evidence in 30 days - consider refining hypothesis"
        }
    ],
    "suggested_actions": [
        "Generate ideas for prob_001 (strong evidence)",
        "Add hypothesis to prob_002 (currently exploratory)",
        "Archive or refine prob_003 (stale)"
    ]
}
```

### Tasks

1. [ ] Implement problem health calculation
2. [ ] Add staleness detection (no new evidence in N days)
3. [ ] Create insight generation logic
4. [ ] Implement `get_problem_dashboard` MCP tool
5. [ ] Add suggested actions based on problem state

### Success Metrics

- Dashboard provides actionable overview
- Stale problems are correctly identified
- Health scores are meaningful
- Response time < 2 seconds

---

## Migration Plan

### Phase 1: Add Problems Infrastructure (Story 10.1)
- Create problems collection
- Implement CRUD tools
- No breaking changes to existing flow

### Phase 2: Add Analysis (Story 10.2)
- Implement problem-KB matching
- Add relationship expansion
- Existing idea generation still works

### Phase 3: Replace Idea Generation (Story 10.3)
- Rewrite `suggest_article_ideas`
- Deprecate unguided mode
- Migrate existing ideas where possible

### Phase 4: Optional Enhancements (Stories 10.4, 10.5)
- Auto-connect pipeline integration
- Dashboard and insights

### Deprecation Notice

After Story 10.3 is complete:
- `suggest_article_ideas()` without `problem_id` will show deprecation warning
- After 30 days: require `problem_id` or `all_problems=True`
- Old cluster-based logic will be removed

---

## Summary

| Story | Description | Priority | Effort |
|-------|-------------|----------|--------|
| 10.1 | Problems Collection & CRUD | High | 3-4h |
| 10.2 | Problem-KB Matching with Relationships | High | 6-8h |
| 10.3 | Problem-Based Idea Generation | High | 8-10h |
| 10.4 | Auto-Connect New Highlights | Medium | 4-6h |
| 10.5 | Problem Dashboard & Insights | Medium | 3-4h |

**Total Estimated Effort:** 24-32 hours

**Key Deliverables:**
- `problems` Firestore collection
- 6-8 new/modified MCP tools
- Problem-first idea generation (replaces Story 6.1)
- Relationship-centric evidence analysis
- Contradiction-boosted strength scoring

---

## Open Questions

1. **Problem Limit**: Should there be a max number of active problems (like Feynman's 12)?
2. **Sharing**: Could problems be shared/templated for common use cases?
3. **Problem Hierarchy**: Support for sub-problems or problem trees?
4. **External Input**: Allow adding evidence manually (not just from KB)?
5. **Hypothesis Evolution**: Track how hypothesis changes over time?

---

*This epic replaces Story 6.1 from Epic 6. See [epic6.md](epic6.md) for remaining blogging engine stories (6.2-6.7).*
