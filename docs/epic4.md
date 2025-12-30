# Epic 4: Knowledge Graph with Entity & Relation Extraction

**Goal:** Build an AI-powered Knowledge Graph that automatically extracts entities and relationships from knowledge chunks, enabling multi-hop queries, contradiction detection, and proactive knowledge connections beyond simple vector similarity.

**Business Value:** Transforms the knowledge base from a semantic search tool into a true "Wisdom Engine" that discovers hidden connections, surfaces contradictions, and proactively connects past knowledge with current work - aligned with Building a Second Brain's CODE framework (especially Distill and Express phases).

**Dependencies:** Epic 2 (Knowledge Cards, Clustering must be complete)

**Estimated Complexity:** Medium - Extends existing AI generation pipeline with entity/relation extraction

**Status:** In Progress

---

## Story 4.1: Entity Extraction from Knowledge Chunks

**Status:** Planned

**Summary:** Extend the Knowledge Card generation pipeline to also extract named entities (concepts, technologies, people, frameworks, practices) from each chunk. Store entities in a dedicated Firestore collection with references back to source chunks.

**Key Features:**
- **Entity Types:** concept, technology, person, framework, practice, methodology
- **Extraction Method:** Gemini-based extraction during Knowledge Card generation
- **Entity Normalization:** Deduplicate similar entities (e.g., "K8s" → "Kubernetes")
- **Source Tracking:** Link each entity to source chunks for provenance
- **Embedding Storage:** Generate embeddings for entity names for similarity search

**Dependencies:** Story 2.1 (Knowledge Cards) - extends existing generation pipeline

**Technical Approach:**
- Extend `KnowledgeCardGenerator` with entity extraction prompt
- New Firestore collection `kg_nodes` with schema:
  ```json
  {
    "uid": "entity-uuid",
    "label": "Platform Engineering",
    "type": "concept",
    "source_chunks": ["chunk_1", "chunk_2"],
    "embedding": [...],
    "created_at": "2025-12-28T...",
    "mention_count": 5
  }
  ```
- Entity deduplication via embedding similarity (>0.95 = same entity)
- Batch processing for existing chunks, incremental for new chunks

**Success Metrics:**
- Entities extracted from 100% of chunks
- <5% duplicate entities after normalization
- Entity extraction adds <2 seconds to Knowledge Card generation
- Cost impact: <$0.05/month additional

---

## Story 4.2: Relation Extraction Between Entities

**Status:** Planned

**Summary:** Extract semantic relationships between entities found in the same chunk or across related chunks. Store relationships in a dedicated edges collection with relation types and source provenance.

**Key Features:**
- **Relation Types:**
  - `enables` - X enables/supports Y
  - `extends` - X builds upon/extends Y
  - `contradicts` - X contradicts/conflicts with Y
  - `influences` - X influences/affects Y
  - `depends_on` - X requires/depends on Y
  - `part_of` - X is a component of Y
  - `example_of` - X is an example/instance of Y
- **Extraction Method:** Gemini-based extraction with structured output
- **Confidence Scoring:** Weight relationships by mention frequency and context
- **Bidirectional Handling:** Store relationships with direction awareness

**Dependencies:** Story 4.1 (Entity Extraction) - requires entities to exist

**Technical Approach:**
- New extraction prompt for relationship detection
- New Firestore collection `kg_edges` with schema:
  ```json
  {
    "uid": "edge-uuid",
    "source": "entity-uuid-1",
    "target": "entity-uuid-2",
    "relation": "enables",
    "weight": 0.85,
    "source_chunks": ["chunk_1"],
    "created_at": "2025-12-28T..."
  }
  ```
- Process chunks in context windows for cross-chunk relationships
- Aggregate duplicate relationships with weight accumulation

**Success Metrics:**
- Average 3-5 relationships extracted per chunk
- Relationship types distributed across all 7 categories
- <10% false positive rate (manual spot-check)
- Cost impact: <$0.05/month additional

---

## Story 4.3: MCP Tools for Knowledge Graph Queries

**Status:** Planned

**Summary:** Expose the Knowledge Graph via new MCP tools enabling users to query entity relationships, find contradictions, trace influence chains, and discover concept connections through Claude.

**Key Features:**
- **Entity Query Tools:**
  - `get_entity(name)` - Get entity details with related chunks
  - `search_entities(query, type?)` - Semantic search for entities
  - `list_entity_types()` - Browse entities by type
- **Relationship Query Tools:**
  - `get_influences(entity)` - What influences this entity?
  - `get_influenced_by(entity)` - What does this entity influence?
  - `get_contradictions(entity?)` - Find conflicting information
  - `get_dependencies(entity)` - What does this depend on?
  - `find_path(entity_a, entity_b)` - How are two concepts connected?
- **Discovery Tools:**
  - `get_knowledge_gaps()` - Entities with few connections
  - `get_emerging_themes()` - Recently connected entity clusters

**Dependencies:** Stories 4.1, 4.2 (Entity and Relation Extraction)

**Technical Approach:**
- Implement tools using Firestore queries on kg_nodes and kg_edges
- Multi-hop traversal for `find_path` (max 3 hops)
- Aggregate results with source chunk references
- Response includes "why" explanations with source links

**Success Metrics:**
- All tools respond in <2 seconds (P95)
- Multi-hop queries find paths in <5 seconds
- Tools return actionable, source-linked results
- Zero additional infrastructure cost

---

## Story 4.4: Proactive Knowledge Connections

**Status:** Planned

**Summary:** When new chunks are added to the knowledge base, automatically identify and surface connections to existing knowledge. Alert users to contradictions, supporting evidence, and knowledge gaps.

**Key Features:**
- **New Chunk Analysis:** On chunk import, analyze entity overlap with existing KB
- **Connection Types:**
  - "This new article **supports** your existing notes on X"
  - "This new article **contradicts** something you read before"
  - "This fills a **knowledge gap** in your understanding of X"
  - "This connects previously **unrelated** concepts X and Y"
- **Surfacing Method:** Include in Knowledge Card or separate "connections" field
- **MCP Tool:** `get_new_connections(days?)` - What connected recently?

**Dependencies:** Stories 4.1-4.3 (Full Knowledge Graph infrastructure)

**Technical Approach:**
- Hook into daily pipeline after Knowledge Card generation
- Compare new entity set against existing graph
- Detect contradictions via `contradicts` relation type
- Store connections in chunk metadata for retrieval
- Optional: Push notifications for high-value connections

**Success Metrics:**
- 80% of new chunks have at least one connection identified
- Contradictions surfaced within 24 hours of import
- Connection quality rated "useful" by user (manual validation)
- No additional latency to daily pipeline (<30 seconds total)

---

## Summary

| Story | Description | Status |
|-------|-------------|--------|
| 4.1 | Entity Extraction from Knowledge Chunks | Planned |
| 4.2 | Relation Extraction Between Entities | Planned |
| 4.3 | MCP Tools for Knowledge Graph Queries | Planned |
| 4.4 | Proactive Knowledge Connections | Planned |

**Recommended Implementation Order:**
1. Story 4.1 (Entity Extraction) - foundation for graph
2. Story 4.2 (Relation Extraction) - builds on entities
3. Story 4.3 (MCP Tools) - expose graph to users
4. Story 4.4 (Proactive Connections) - "Wisdom Engine" capability

**Estimated Cost Impact:** <$0.20/month total (Gemini API for extraction)
