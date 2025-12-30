# Epic 4: Cross-Chunk Relationships & Knowledge Connections

**Goal:** Build automated relationship extraction between knowledge chunks to enable connection queries, timeline evolution, and contradiction detection - without manual ontology or predefined entity types.

**Business Value:** Transforms the knowledge base from isolated chunks into a connected knowledge network. Enables queries like "How are these concepts connected?", "How has my understanding evolved?", and "Are there contradictions in my knowledge?"

**Dependencies:** Epic 2 (Knowledge Cards, Clustering complete), Epic 3 (MCP Server)

**Status:** Planned

---

## Research Background

### Why Relationships, Not Entity Types?

Based on research into knowledge graph best practices (Dec 2025):

1. **Personal Knowledge ≠ Enterprise Ontology**
   - Tools like Zettelkasten, Obsidian, Roam emphasize *connections over categories*
   - Fixed entity types (PERSON, CONCEPT, TECHNOLOGY) are rigid and require maintenance
   - Your knowledge spans multiple domains (Tech, Parenting, Leadership, Travel)

2. **State of the Art: Schema-Free Extraction**
   - EDC Framework (Zhang & Soh, EMNLP 2024): Extract → Define → Canonicalize
   - LLM-based extraction achieves 89.7% precision, 92.3% recall
   - No predefined schema needed - relationships emerge from content

3. **Your Query Use Cases**
   | Query Type | What You Need |
   |------------|---------------|
   | Verbindungen | Cross-chunk links between related ideas |
   | Timeline | `extends` relationships showing concept evolution |
   | Widersprüche | `contradicts` relationships between chunks |
   | Empfehlungen | Already working via clusters + embeddings |

### Pragmatic Approach for kx-hub

Instead of full EDC or Neo4j, we use:
- **Existing Embeddings** for similarity-based canonicalization
- **Existing Clusters** for scoping relationship extraction
- **Firestore** as graph store (no new infrastructure)
- **LLM Relationship Extraction** similar to LangChain LLMGraphTransformer

---

## Story 4.1: Chunk-to-Chunk Relationship Extraction

**Status:** Planned

**Summary:** Extract semantic relationships between chunks within the same cluster or with high embedding similarity. Store relationships in Firestore with type, confidence, and source provenance.

**Key Design Decisions:**
- **No Entity Extraction** - relationships are between *chunks*, not extracted entities
- **Relationship Types** (small, fixed set for queryability):
  - `relates_to` - General semantic connection
  - `extends` - Builds upon, evolves, is next step
  - `supports` - Provides evidence, confirms, reinforces
  - `contradicts` - Conflicts with, disagrees, challenges
  - `applies_to` - Practical application of concept
- **Scoped Extraction** - Only compare chunks within same cluster or similarity > 0.8
- **Fully Automated** - No manual review required

**Technical Approach:**

```
Pipeline:
1. For each cluster:
   - Get all chunk pairs (n*(n-1)/2 comparisons)
   - Filter by embedding similarity > 0.8
2. For each pair:
   - LLM prompt: "What is the relationship between these two texts?"
   - Output: {type, confidence, explanation}
3. Store in Firestore
4. Canonicalize: Merge bidirectional duplicates
```

**Firestore Schema:**
```
relationships/
  {relationship_id}:
    source_chunk_id: "chunk-001"
    target_chunk_id: "chunk-002" 
    type: "extends"              # from fixed set
    confidence: 0.85
    explanation: "Platform Engineering builds on DevOps practices"
    cluster_id: "cluster-42"
    created_at: timestamp
```

**LLM Prompt (Gemini Flash):**
```
Compare these two knowledge chunks and determine their relationship.

Chunk A: {title_a}
{summary_a}

Chunk B: {title_b}
{summary_b}

What is the relationship from A to B?
Options:
- relates_to: General thematic connection
- extends: B builds upon or evolves A
- supports: B provides evidence or confirms A
- contradicts: B conflicts with or challenges A
- applies_to: B is practical application of A
- none: No meaningful relationship

Return JSON: {"type": "...", "confidence": 0.0-1.0, "explanation": "..."}
```

**Success Metrics:**
- Relationships extracted for all clusters
- Average 2-5 relationships per chunk
- <5% false positives (spot-check validation)
- Processing time: <1 hour for full KB (~900 chunks)
- Cost: <$1 for initial extraction, <$0.10/month incremental

---

## Story 4.2: MCP Tools for Relationship Queries

**Status:** Planned

**Summary:** Expose relationships via MCP tools to answer connection, timeline, and contradiction queries.

**MCP Tools:**

### `get_connections`
Find all relationships for a chunk or concept.
```
Input: {chunk_id: string} or {query: string, limit: int}
Output: {
  connections: [
    {related_chunk, type, explanation, confidence}
  ]
}
```

**Use Case:** "What is connected to my notes on DevOps?"

### `find_path`
Find how two concepts/chunks are connected (multi-hop).
```
Input: {from_query: string, to_query: string, max_hops: int}
Output: {
  path: [chunk_a, --(extends)--> chunk_b, --(relates_to)--> chunk_c],
  explanation: "DevOps → Platform Engineering → Internal Developer Platform"
}
```

**Use Case:** "How are Parenting and Leadership connected in my knowledge?"

### `get_evolution`
Trace how a concept has evolved over time (timeline query).
```
Input: {concept: string}
Output: {
  timeline: [
    {chunk, date, summary},  # ordered by created_at
  ],
  evolution: "Your understanding evolved from X to Y to Z"
}
```

**Use Case:** "How has my understanding of AI evolved?"

### `get_contradictions`
Find conflicting information in the knowledge base.
```
Input: {topic?: string, limit: int}
Output: {
  contradictions: [
    {chunk_a, chunk_b, explanation}
  ]
}
```

**Use Case:** "Are there contradictions in my notes on Remote Work?"

**Success Metrics:**
- All tools respond in <3 seconds (P95)
- Multi-hop paths found in <5 seconds
- Results include source chunk links for verification

---

## Story 4.3: Incremental Relationship Updates

**Status:** Planned

**Summary:** When new chunks are added, automatically extract relationships to existing chunks and surface notable connections.

**Trigger:** After Knowledge Card generation in daily pipeline

**Process:**
1. New chunk embedded and assigned to cluster
2. Find similar chunks (same cluster OR embedding similarity > 0.85)
3. Extract relationships to top 10 similar chunks
4. Store relationships
5. Flag notable connections:
   - `contradicts` → High priority alert
   - `extends` recent chunk → "Continuing thread"
   - Connects two previously unconnected clusters → "Bridge discovery"

**Notable Connections Field:**
Add to chunk document:
```json
{
  "notable_connections": [
    {
      "type": "contradicts",
      "related_chunk_id": "...",
      "explanation": "This article challenges your earlier notes on X"
    }
  ]
}
```

**MCP Tool Addition:**
```
get_recent_connections(days: int)
→ Returns notable connections from recently added chunks
```

**Success Metrics:**
- New chunks processed within daily pipeline (no separate run)
- Contradictions surfaced within 24 hours
- <30 seconds added to per-chunk processing time

---

## Story 4.4: Relationship Visualization Data

**Status:** Planned (Optional)

**Summary:** Provide graph data export for visualization tools (Obsidian, Gephi, or custom UI).

**Export Format:**
```json
{
  "nodes": [
    {"id": "chunk-001", "label": "DevOps Handbook", "cluster": "devops"}
  ],
  "edges": [
    {"source": "chunk-001", "target": "chunk-002", "type": "extends"}
  ]
}
```

**MCP Tool:**
```
export_knowledge_graph(cluster_id?: string, format: "json" | "graphml")
```

**Use Case:** Visualize your knowledge network in external tools

---

## Summary

| Story | Description | Priority |
|-------|-------------|----------|
| 4.1 | Chunk-to-Chunk Relationship Extraction | High |
| 4.2 | MCP Tools for Relationship Queries | High |
| 4.3 | Incremental Relationship Updates | Medium |
| 4.4 | Relationship Visualization Data | Low |

**Key Differences from Original Epic 4:**

| Original | Revised |
|----------|---------|
| Entity Extraction (PERSON, CONCEPT...) | No entities - relationships between chunks |
| Manual entity type definitions | Fully automated, schema-free |
| `kg_nodes` + `kg_edges` collections | Single `relationships` collection |
| Complex ontology | 5 simple relationship types |
| Neo4j-style graph queries | Firestore queries with embedding similarity |

**Implementation Order:**
1. Story 4.1 - Extract relationships (batch for existing, foundation)
2. Story 4.2 - MCP tools (immediate value for queries)
3. Story 4.3 - Incremental updates (integrate into pipeline)
4. Story 4.4 - Visualization (nice-to-have)

**Estimated Cost:** 
- Initial extraction: ~$1-2 (one-time)
- Incremental: <$0.10/month
- No new infrastructure (Firestore only)

**Risk Mitigation:**
- Start with one cluster, validate quality before full rollout
- Log all LLM extractions for debugging
- Confidence threshold (>0.7) for storing relationships
