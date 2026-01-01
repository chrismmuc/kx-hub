# Epic 4: Source-Based Knowledge Graph

**Goal:** Build a connected knowledge network based on Sources (books/articles) and their Chunks, with explicit relationships at both levels. Remove cluster dependency.

**Business Value:** Transforms isolated chunks into a queryable knowledge graph. Enables "How are these sources connected?", "What contradicts what?", and "How has my understanding evolved?"

**Dependencies:** Epic 2 (Knowledge Cards), Epic 3 (MCP Server)

**Status:** ✅ Complete (all stories done)

---

## Architecture Decision: Sources over Clusters

### Why Remove Clusters?

| Clusters | Relationships |
|----------|---------------|
| Implicit grouping by embedding similarity | Explicit typed connections |
| No semantic meaning | `extends`, `supports`, `contradicts` |
| Redundant with embedding search | Enables multi-hop reasoning |
| Same-source chunks cluster together (trivial) | Cross-source connections (valuable) |

**Key Insight:** High-similarity pairs (0.92+) are mostly same-source chunks. The interesting connections are **cross-source** - when Author A's idea relates to Author B's.

### New Data Model

```
Sources (books, articles)
  └── Chunks (passages with embeddings)
  
Relationships:
  - Source → Source (high-level connections)
  - Chunk → Chunk (cross-source only, detailed connections)
```

**What Clusters Provided (and Replacements):**
| Cluster Feature | Replacement |
|----------------|-------------|
| "Similar content" grouping | Embedding similarity search |
| Topic browsing | Source-level tags/categories |
| Scoping for extraction | Source-based grouping |

---

## Data Schema

### Sources Collection (new)
```
sources/
  {source_id}:  # e.g., "building-a-second-brain"
    title: "Building a Second Brain"
    author: "Tiago Forte"
    type: "book" | "article" | "podcast" | "video"
    chunk_ids: ["chunk-001", "chunk-002", ...]
    chunk_count: 15
    created_at: timestamp
    tags: ["productivity", "pkm"]  # optional, for browsing
```

### Relationships Collection (revised)
```
relationships/
  {auto-id}:
    # Source-to-Source OR Chunk-to-Chunk
    source_id: "building-a-second-brain"      # if source-level
    target_id: "the-para-method"
    # OR
    source_chunk_id: "chunk-001"              # if chunk-level
    target_chunk_id: "chunk-042"
    
    level: "source" | "chunk"
    type: "relates_to" | "extends" | "supports" | "contradicts" | "applies_to"
    confidence: 0.85
    explanation: "Both discuss progressive summarization"
    created_at: timestamp
```

### Relationship Types (unchanged)
- `relates_to` - General thematic connection
- `extends` - Builds upon, develops further
- `supports` - Provides evidence, confirms
- `contradicts` - Conflicts with, challenges
- `applies_to` - Practical application of

---

## Story 4.1: Source Extraction & Migration

**Status:** ✅ Done

**Summary:** Extract unique sources from existing chunks and create sources collection.

**Tasks:**
1. Parse `title` field from chunks to identify unique sources
2. Create `sources/` collection with aggregated metadata
3. Add `source_id` field to each chunk
4. Remove `cluster_id` from chunks (or deprecate)

**Migration Script:**
```python
# Group chunks by title (= source)
sources = {}
for chunk in chunks:
    source_key = normalize(chunk.title)
    if source_key not in sources:
        sources[source_key] = {
            'title': chunk.title,
            'author': chunk.author,
            'chunk_ids': []
        }
    sources[source_key]['chunk_ids'].append(chunk.id)

# Write to Firestore
for source_id, data in sources.items():
    db.collection('sources').document(source_id).set(data)
```

**Success Metrics:**
- All chunks linked to a source
- ~50-100 unique sources expected
- No orphan chunks

---

## Story 4.2: Cross-Source Relationship Extraction

**Status:** ✅ Done

**Summary:** Extract relationships between chunks from **different** sources only.

**Key Changes from Current Implementation:**
1. Skip same-source pairs (currently wasting LLM calls on trivial connections)
2. Use source-level pre-filtering instead of cluster-based
3. Add parallel LLM calls for performance

**Algorithm:**
```
1. For each source pair (A, B):
   - Get all chunks from A and B
   - Compute pairwise embedding similarity
   - Keep pairs with similarity > 0.80
   
2. For each cross-source pair:
   - LLM: Determine relationship type
   - Store if confidence > 0.7
   
3. Aggregate to source level:
   - If 3+ chunk relationships between A and B → create source-level relationship
```

**Performance Target:**
- ~50-100 sources = 1,225-4,950 source pairs
- Filter to ~500 pairs with high cross-source similarity
- ~10 min with parallel LLM calls (10 concurrent)
- Cost: ~$0.10

**Success Metrics:**
- Only cross-source relationships stored
- Average 1-3 relationships per source
- <10% noise (validated by spot-check)

---

## Story 4.3: MCP Tools for Source & Relationship Queries

**Status:** ✅ Done

**Summary:** Expose relationships via MCP tools.

### `get_source_connections`
```python
get_source_connections(source_id: str) -> {
    "source": {"title": "...", "author": "..."},
    "connections": [
        {"target": {...}, "type": "extends", "explanation": "..."}
    ]
}
```

### `find_path`
```python
find_path(from_query: str, to_query: str, max_hops: int = 3) -> {
    "path": ["Source A", "--(extends)-->", "Source B", "--(supports)-->", "Source C"],
    "explanation": "..."
}
```

### `get_contradictions`
```python
get_contradictions(topic: str = None, limit: int = 10) -> {
    "contradictions": [
        {"source_a": {...}, "source_b": {...}, "explanation": "..."}
    ]
}
```

### `get_evolution`
```python
get_evolution(concept: str) -> {
    "timeline": [
        {"source": {...}, "date": "...", "chunk": {...}}
    ],
    "summary": "Your understanding evolved from X to Y"
}
```

---

## Story 4.4: Cluster Deprecation

**Status:** ✅ Done

**Summary:** Remove cluster-related code and data after relationship migration.

**Completed Tasks:**
1. ✅ Removed cluster tools from MCP server (`list_clusters`, `get_cluster`, `search_within_cluster`, `get_related_clusters`)
2. ✅ Removed `cluster_ids` parameter from `get_reading_recommendations`
3. ✅ Replaced `_format_cluster_info` with `_format_source_info` in tools.py
4. ✅ Removed cluster functions from `firestore_client.py`
5. ✅ Removed cluster formatters from `resources.py`
6. ✅ Updated `recommendation_queries.py` to use sources instead of clusters
7. ✅ Deleted `test_cluster_relationships.py` and updated remaining tests
8. ✅ All 268 tests pass

**MCP Tool Changes:**
| Old | New |
|-----|-----|
| `list_clusters` | `list_sources` |
| `get_cluster` | `get_source` |
| `search_within_cluster` | `search_within_source` |
| `get_related_clusters` | (removed, use `get_source` with relationships) |

**Note:** Clustering code in `src/clustering/` is archived but not actively used by MCP server.

---

## Story 4.5: Incremental Relationship Updates

**Status:** ✅ Done

**Summary:** When new chunks are ingested, automatically find cross-source relationships.

**Trigger:** After knowledge-cards step in daily pipeline

**Implementation:**
1. `functions/relationships/` - Cloud Function that processes new chunks
2. For each new chunk, finds top 10 similar chunks from OTHER sources via Firestore vector search
3. Extracts relationships via Gemini 2.0 Flash LLM
4. Saves relationships to `relationships` collection in Firestore

**Files:**
- `functions/relationships/main.py` - Standalone Cloud Function
- `terraform/relationships.tf` - Infrastructure
- `terraform/workflows/batch-pipeline.yaml` - Pipeline integration
- `src/relationships/` - CLI for manual full extraction (`python -m src.relationships.main`)

---

## Migration Plan

1. **Phase 1:** Create sources collection (Story 4.1)
2. **Phase 2:** Refactor relationship extraction for cross-source (Story 4.2)
3. **Phase 3:** Update MCP tools (Story 4.3)
4. **Phase 4:** Deprecate clusters (Story 4.4)
5. **Phase 5:** Integrate into pipeline (Story 4.5)

---

## Summary

| Story | Description | Priority | Status |
|-------|-------------|----------|--------|
| 4.1 | Source Extraction & Migration | High | ✅ Done |
| 4.2 | Cross-Source Relationship Extraction | High | ✅ Done |
| 4.3 | MCP Tools for Sources & Relationships | High | ✅ Done |
| 4.4 | Cluster Deprecation | Medium | ✅ Done |
| 4.5 | Incremental Updates | Medium | ✅ Done |

**Key Simplifications:**
- No more cluster maintenance
- Only meaningful cross-source relationships
- Source as first-class entity for navigation
- Cleaner data model

**Estimated Effort:**
- Story 4.1: 2-3 hours (migration script)
- Story 4.2: 4-6 hours (refactor extraction)
- Story 4.3: 4-6 hours (MCP tools)
- Story 4.4: 2-3 hours (cleanup)
- Story 4.5: 2-3 hours (pipeline integration)
