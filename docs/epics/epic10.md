# Epic 10: Guided Problem Definition (Feynman Method)

**Goal:** Replace unguided article idea generation with a problem-first approach based on Richard Feynman's "12 Favorite Problems" method. Users define their top problems, and the system automatically matches KB evidence against them - with emphasis on source relationships (especially contradictions).

**Business Value:**
- Transforms passive knowledge collection into active problem-solving
- Evidence is automatically matched to problems as new highlights are ingested
- Contradictions between sources surface the most interesting article angles
- Claude generates article ideas based on rich evidence context

**Dependencies:** Epic 4 (Source Relationships)

**Replaces:** Epic 6 Story 6.1 (Blog Idea Extraction)

**Status:** Planned

---

## The Feynman Method

> "You have to keep a dozen of your favorite problems constantly present in your mind, although by and large they will lay in a dormant state. Every time you hear or read a new trick or a new result, test it against each of your twelve problems to see whether it helps."
> — Richard Feynman

### Core Principle

Define your important questions. As you read and highlight, the system automatically connects relevant evidence to your problems. When ready, Claude helps you turn the evidence into article ideas.

---

## Architecture

### Single MCP Tool

```python
problems(
    action: str,        # "add" | "list" | "analyze" | "archive"
    problem: str = None,
    description: str = None,
    problem_id: str = None
)
```

| Action | Description |
|--------|-------------|
| `add` | Create new problem with optional description |
| `list` | Show all active problems with evidence counts |
| `analyze` | Get evidence + connections for a problem (or all) |
| `archive` | Archive a resolved/inactive problem |

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. USER DEFINES PROBLEM                                                │
│                                                                         │
│  problems(action="add",                                                 │
│           problem="Why do feature flags fail?",                         │
│           description="Teams adopt them but still have issues...")      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  2. DAILY INGEST: NEW CHUNKS MATCHED TO PROBLEMS                        │
│                                                                         │
│  For each new chunk:                                                    │
│    Compare chunk.embedding ↔ problem.embedding                          │
│    If similarity > 0.7 → Add as evidence                                │
│    Check source relationships → Flag contradictions                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3. USER REQUESTS ANALYSIS                                              │
│                                                                         │
│  problems(action="analyze", problem_id="prob_001")                      │
│                                                                         │
│  Returns:                                                               │
│  - Problem + description                                                │
│  - Evidence grouped by type (supporting/contradicting)                  │
│  - Source relationships (extends/supports/contradicts)                  │
│  - Connection graph                                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  4. CLAUDE GENERATES ARTICLE IDEAS                                      │
│                                                                         │
│  Claude sees the evidence and says:                                     │
│  "Based on the contradiction between Accelerate and 'Move Fast',        │
│   here's an article idea: 'Feature Flags Are Not Enough'..."            │
│                                                                         │
│  → Ideas are generated in conversation, not stored                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Schema

### Problems Collection (NEW)

```
problems/
  {problem_id}:
    # Core definition
    problem: "Why do feature flags fail?"
    description: "Teams adopt feature flags but still have deployment issues.
                  Interested since reading Team Topologies."

    # Embedding for matching (generated from problem + description)
    embedding: [0.1, 0.2, ...]  # 768 dimensions

    # Status
    status: "active" | "archived"

    # Evidence (auto-populated by pipeline)
    evidence: [
      {
        chunk_id: "chunk_123",
        source_id: "accelerate",
        source_title: "Accelerate",
        quote: "Elite performers deploy 208x more frequently...",
        similarity: 0.85,
        added_at: timestamp,
        relationship: {
          type: "extends",
          target_source: "continuous-delivery",
          context: "Adds empirical metrics"
        }
      },
      {
        chunk_id: "chunk_456",
        source_id: "move-fast-article",
        source_title: "Move Fast and Break Things",
        quote: "Speed requires accepting some bugs...",
        similarity: 0.78,
        added_at: timestamp,
        relationship: {
          type: "contradicts",
          target_source: "accelerate",
          context: "Different philosophy on quality tradeoffs"
        },
        is_contradiction: true  # Flag for highlighting
      }
    ]

    # Metadata
    created_at: timestamp
    updated_at: timestamp
    evidence_count: 5
    contradiction_count: 1
```

---

## Story 10.1: Problems Collection & MCP Tool

**Status:** Planned

**Summary:** Create the problems collection and the unified `problems` MCP tool with all actions.

### MCP Tool Implementation

```python
def problems(
    action: str,
    problem: str = None,
    description: str = None,
    problem_id: str = None
) -> dict:
    """
    Unified tool for managing Feynman-style problems.

    Actions:
        add: Create new problem
        list: Show all active problems with evidence counts
        analyze: Get evidence + connections for problem(s)
        archive: Archive a problem
    """
```

### Action: `add`

```python
problems(
    action="add",
    problem="Why do feature flags fail?",
    description="Teams adopt them but still have issues. Interested since Team Topologies."
)
```

**Returns:**
```json
{
  "problem_id": "prob_001",
  "problem": "Why do feature flags fail?",
  "description": "Teams adopt them but still have issues...",
  "status": "active",
  "created_at": "2026-01-10T..."
}
```

**Implementation:**
1. Validate problem text is not empty
2. Generate embedding from `problem + " " + description`
3. Create Firestore document
4. Return confirmation

### Action: `list`

```python
problems(action="list")
```

**Returns:**
```json
{
  "problems": [
    {
      "problem_id": "prob_001",
      "problem": "Why do feature flags fail?",
      "status": "active",
      "evidence_count": 5,
      "contradiction_count": 1,
      "created_at": "2026-01-10T...",
      "last_evidence_at": "2026-01-12T..."
    }
  ],
  "total": 3,
  "active": 3,
  "archived": 0
}
```

### Action: `analyze`

```python
# Single problem
problems(action="analyze", problem_id="prob_001")

# All problems (batch)
problems(action="analyze")
```

**Returns:**
```json
{
  "problem_id": "prob_001",
  "problem": "Why do feature flags fail?",
  "description": "Teams adopt them but still have issues...",

  "evidence": {
    "supporting": [
      {
        "source_title": "Accelerate",
        "author": "Forsgren, Humble, Kim",
        "quote": "Elite performers deploy 208x more frequently...",
        "chunk_id": "chunk_123",
        "relationship": {
          "type": "extends",
          "target": "Continuous Delivery"
        }
      }
    ],
    "contradicting": [
      {
        "source_title": "Move Fast and Break Things",
        "quote": "Speed requires accepting some bugs will reach production",
        "chunk_id": "chunk_456",
        "relationship": {
          "type": "contradicts",
          "target": "Accelerate"
        },
        "why_interesting": "Challenges the 'no tradeoff' claim"
      }
    ]
  },

  "connections": [
    {"from": "Accelerate", "to": "Continuous Delivery", "type": "extends"},
    {"from": "Move Fast", "to": "Accelerate", "type": "contradicts"}
  ],

  "summary": {
    "evidence_count": 5,
    "contradiction_count": 1,
    "sources": ["Accelerate", "Team Topologies", "Move Fast"],
    "ready_for_article": true
  }
}
```

**Note:** Claude uses this output to generate article ideas in the conversation.

### Action: `archive`

```python
problems(action="archive", problem_id="prob_001")
```

**Returns:**
```json
{
  "problem_id": "prob_001",
  "status": "archived",
  "evidence_preserved": true
}
```

### Tasks

1. [ ] Create `problems` Firestore collection with schema
2. [ ] Implement embedding generation for problems
3. [ ] Implement `add` action
4. [ ] Implement `list` action
5. [ ] Implement `analyze` action with evidence grouping
6. [ ] Implement `archive` action
7. [ ] Add to MCP tool registry
8. [ ] Write tests

### Success Metrics

- All 4 actions work correctly
- Embeddings generated on add
- Evidence correctly grouped by relationship type
- Response time < 2s for single problem, < 5s for all

---

## Story 10.2: Pipeline Integration (Auto-Match)

**Status:** Planned

**Summary:** After daily ingest, automatically match new chunks to active problems using embedding similarity.

### Algorithm

```python
def match_new_chunks_to_problems(new_chunk_ids: list):
    """
    Called after ingest pipeline completes.
    Matches new chunks to active problems using embedding similarity.
    """
    # Get new chunks with embeddings
    new_chunks = get_chunks_with_embeddings(new_chunk_ids)

    # Get all active problems with embeddings
    problems = get_active_problems()

    matches = []

    for chunk in new_chunks:
        for problem in problems:
            similarity = cosine_similarity(
                chunk.embedding,
                problem.embedding
            )

            if similarity > SIMILARITY_THRESHOLD:  # 0.7
                # Get source relationships for this chunk
                relationships = get_source_relationships(chunk.source_id)

                # Check if contradicts existing evidence
                is_contradiction = check_for_contradiction(
                    chunk.source_id,
                    problem.evidence,
                    relationships
                )

                matches.append({
                    "problem_id": problem.id,
                    "chunk_id": chunk.id,
                    "similarity": similarity,
                    "is_contradiction": is_contradiction,
                    "relationships": relationships
                })

    # Batch update problems with new evidence
    update_problem_evidence(matches)

    return {
        "chunks_processed": len(new_chunks),
        "matches_found": len(matches),
        "contradictions_found": sum(1 for m in matches if m["is_contradiction"])
    }
```

### Efficiency

```
Daily ingest: ~5-20 new chunks
Active problems: ~5-12

Comparisons: 20 × 12 = 240 embedding comparisons
Time: < 1 second

vs. Full re-analysis: 800 × 12 = 9600 comparisons
```

### Integration Point

In `src/ingest/main.py` after embedding:

```python
# Existing pipeline
chunks = process_highlights(raw_data)
embedded_chunks = embed_chunks(chunks)
stored_ids = store_chunks(embedded_chunks)

# NEW: Match to problems
from problems import match_new_chunks_to_problems
match_result = match_new_chunks_to_problems(stored_ids)
logger.info(f"Matched {match_result['matches_found']} chunks to problems")
```

### Tasks

1. [ ] Add embedding field to problems schema
2. [ ] Implement `match_new_chunks_to_problems` function
3. [ ] Implement `check_for_contradiction` using source relationships
4. [ ] Add batch update for problem evidence
5. [ ] Integrate into ingest pipeline
6. [ ] Add logging and monitoring
7. [ ] Write integration tests

### Success Metrics

- New evidence added within 24h of ingest
- Contradiction detection accuracy > 90%
- Pipeline overhead < 2 seconds
- No false positives at 0.7 threshold

---

## Story 10.3: Cleanup Legacy Ideas System

**Status:** Planned

**Summary:** Remove the old article ideas system (suggest_article_ideas, list_ideas, accept_idea, reject_idea) and clean up the database.

### Tools to Remove

| Tool | File | Action |
|------|------|--------|
| `suggest_article_ideas` | `tools.py`, `article_ideas.py` | Delete |
| `list_ideas` | `tools.py` | Delete |
| `accept_idea` | `tools.py` | Delete |
| `reject_idea` | `tools.py` | Delete |

### Files to Remove/Modify

```
src/mcp_server/
├── article_ideas.py      # DELETE entire file
├── tools.py              # Remove idea-related functions
└── server.py             # Remove tool registrations
```

### Database Cleanup

```python
def cleanup_article_ideas_collection():
    """
    One-time migration to remove article_ideas collection.
    Run after Epic 10 is deployed.
    """
    db = firestore.Client()

    # Export for backup (optional)
    ideas = db.collection("article_ideas").stream()
    backup = [{"id": doc.id, **doc.to_dict()} for doc in ideas]
    save_to_gcs("backups/article_ideas_backup.json", backup)

    # Delete collection
    delete_collection(db, "article_ideas")

    logger.info(f"Deleted article_ideas collection ({len(backup)} documents backed up)")
```

### MCP Tool Count Change

```
Before: 18 tools (including 4 idea tools)
After:  15 tools (removed 4, added 1 problems tool)

Net: -3 tools (simpler interface)
```

### Tasks

1. [ ] Backup article_ideas collection to GCS
2. [ ] Remove `article_ideas.py`
3. [ ] Remove idea tools from `tools.py`
4. [ ] Remove tool registrations from `server.py`
5. [ ] Delete article_ideas Firestore collection
6. [ ] Update tool documentation
7. [ ] Update tests (remove idea tests, add problem tests)

### Success Metrics

- All idea-related code removed
- No orphaned references
- Tests pass
- Backup verified in GCS

---

## Story 10.4: Update Epic 6 Integration

**Status:** Planned

**Summary:** Update Epic 6 (Blogging Engine) to work with the new problems-based approach.

### Changes to Epic 6

| Story | Change |
|-------|--------|
| 6.1 | ~~Blog Idea Extraction~~ → **Removed** (replaced by Epic 10) |
| 6.2 | Article Outline → Works with problem context from `problems(action="analyze")` |
| 6.3-6.7 | No changes - work with articles, not ideas |

### New Workflow for Article Creation

```
1. problems(action="analyze", problem_id="prob_001")
   → Claude sees evidence + contradictions

2. Claude: "Based on this evidence, here's an article idea:
   'Feature Flags Are Not Enough'. Want me to create an outline?"

3. User: "Yes"

4. create_article_outline(
       title="Feature Flags Are Not Enough",
       source_ids=["accelerate", "move-fast", "team-topologies"]
   )
   → Uses sources from problem evidence
```

### Tasks

1. [ ] Update epic6.md to reflect 6.1 removal
2. [ ] Document new workflow in epic6.md
3. [ ] Ensure outline generation accepts source_ids from evidence

---

## MCP Interface Summary

### Before (4 tools)

```python
suggest_article_ideas(min_sources, focus_tags, limit, save, topic, source_ids)
list_ideas(status, limit)
accept_idea(idea_id)
reject_idea(idea_id)
```

### After (1 tool)

```python
problems(
    action: str,        # "add" | "list" | "analyze" | "archive"
    problem: str = None,
    description: str = None,
    problem_id: str = None
)
```

### Token Efficiency

```
Before: 4 tool definitions in system prompt
After:  1 tool definition in system prompt

Reduction: ~75% fewer tokens for tool definitions
```

---

## Example Workflows

### Creating a Problem

```
User: "I want to explore why feature flags often fail"

Claude: problems(action="add",
                 problem="Why do feature flags fail?",
                 description="Teams adopt them but still have deployment issues")

Claude: "I've created this as a problem to track. As you read and highlight
         relevant content, I'll automatically connect it to this problem.
         You can check progress anytime with 'analyze my problems'."
```

### Checking Problem Status

```
User: "What's the status of my problems?"

Claude: problems(action="list")

Claude: "You have 3 active problems:
         1. 'Why do feature flags fail?' - 5 evidence pieces, 1 contradiction!
         2. 'How to scale engineering teams?' - 3 evidence pieces
         3. 'What makes books stick?' - 2 evidence pieces

         Problem 1 has a contradiction - want me to analyze it?"
```

### Getting Article Ideas

```
User: "Analyze the feature flags problem"

Claude: problems(action="analyze", problem_id="prob_001")

Claude: "Here's what your knowledge base says about feature flags:

         **Supporting Evidence:**
         - Accelerate: 'Elite performers deploy 208x more frequently...'
           (extends Continuous Delivery principles)

         **Contradicting Evidence:** ⚡
         - 'Move Fast and Break Things': 'Speed requires accepting bugs'
           (contradicts Accelerate's 'no tradeoff' claim)

         This contradiction is interesting! It suggests an article angle:

         **Article Idea:** 'Feature Flags Are Not Enough'
         **Thesis:** Feature flags reduce deployment risk, but only when
                     combined with observability. The tension between
                     Accelerate and 'Move Fast' reveals that monitoring
                     is the missing piece.

         Want me to create an outline?"
```

---

## Story 10.5: Infographic Generation (Optional)

**Status:** Planned (Optional)

**Summary:** Generate visual infographics for problems using Gemini 3 Pro Image, visualizing the evidence and contradictions.

### Pricing (Gemini 3 Pro Image)

| Resolution | Tokens | Cost per Image |
|------------|--------|----------------|
| 1K-2K (1024-2048px) | 1,120 | **$0.134** |
| 2K-3K (HD) | ~1,500 | **$0.18** |
| 4K (4096px) | 2,000 | **$0.24** |

**Free tier:** 1,500 images/day in Google AI Studio (dev/testing)

### Usage

```python
problems(
    action="analyze",
    problem_id="prob_001",
    generate_infographic=True  # Optional parameter
)
```

**Returns (additional field):**
```json
{
  "infographic": {
    "url": "gs://kx-hub-infographics/prob_001.png",
    "resolution": "2048x2048",
    "cost": "$0.134",
    "generated_at": "2026-01-10T..."
  }
}
```

### Infographic Content

The generated infographic visualizes:
- Problem statement (center)
- Supporting evidence (green, with source attributions)
- Contradicting evidence (red, highlighted as tension)
- Connection arrows showing relationships
- Key quotes from sources

### Prompt Template

```python
INFOGRAPHIC_PROMPT = """
Create a professional infographic visualizing this research problem.

PROBLEM: {problem}
DESCRIPTION: {description}

SUPPORTING EVIDENCE:
{supporting_evidence_formatted}

CONTRADICTING EVIDENCE (highlight as tension!):
{contradicting_evidence_formatted}

CONNECTIONS:
{connections_formatted}

STYLE:
- Clean, modern, minimalist design
- Problem as central focal point
- Green for supporting, red/orange for contradicting
- Include source attributions for credibility
- Show connection arrows between sources
- Professional typography, readable at 1080p

OUTPUT: 2048x2048 PNG
"""
```

### Tasks

1. [ ] Add `generate_infographic` parameter to analyze action
2. [ ] Implement Gemini 3 Pro Image client
3. [ ] Create infographic prompt template
4. [ ] Upload generated images to GCS
5. [ ] Return image URL in response
6. [ ] Add cost tracking/logging

### Success Metrics

- Infographics are visually clear and accurate
- Generation time < 30 seconds
- Cost tracked per generation
- Images accessible via GCS URL

---

## Implementation Plan

### Phase 1: Core (Stories 10.1, 10.3)
1. Create problems collection + MCP tool
2. Remove legacy ideas system
3. Basic workflow working

### Phase 2: Automation (Story 10.2)
1. Pipeline integration
2. Auto-matching new chunks
3. Contradiction detection

### Phase 3: Integration (Story 10.4)
1. Update Epic 6 workflow
2. Documentation
3. User testing

---

## Summary

| Story | Description | Effort |
|-------|-------------|--------|
| 10.1 | Problems Collection & MCP Tool | 4-6h |
| 10.2 | Pipeline Integration (Auto-Match) | 4-6h |
| 10.3 | Cleanup Legacy Ideas System | 2-3h |
| 10.4 | Update Epic 6 Integration | 1-2h |
| 10.5 | Infographic Generation (Optional) | 2-3h |

**Total Effort:** 13-20 hours (11-17h without infographics)

**Key Deliverables:**
- 1 new MCP tool (`problems` with 4 actions)
- 4 tools removed (suggest_article_ideas, list_ideas, accept_idea, reject_idea)
- Automatic evidence matching in pipeline
- Contradiction highlighting
- Cleaner, more focused workflow

---

*This epic replaces Story 6.1 from Epic 6. The remaining stories (6.2-6.7) continue to work with the new problems-based approach.*
