# Epic 2 PRD – Enhanced Knowledge Graph & Clustering

**Project:** kx-hub - Personal AI Knowledge Base (Google Cloud + Vertex AI)

**Epic:** 2 - Enhanced Knowledge Graph & Clustering

**Version:** 1.0

**Status:** Draft

**Last Updated:** 2025-10-31

---

## 1. Epic Goal & Value Proposition

**Goal:** Transform 813+ passive highlight chunks into an active, interconnected knowledge system through semantic clustering, AI-generated knowledge cards, cross-cluster synthesis, and gap analysis—enabling effortless topic exploration, insight discovery, and knowledge evolution tracking.

**Business Value:**
- **From Archive to Intelligence:** Converts passive highlight collection into active knowledge organization with automated distillation
- **Cognitive Load Reduction:** Knowledge cards shrink 813 chunks into scannable, pre-digested insights (TL;DR + key takeaways)
- **Topic-Based Discovery:** Enables cluster browsing vs. keyword-only search, revealing thematic patterns
- **Cross-Topic Synthesis:** Identifies unexpected connections and bridges between seemingly unrelated topics
- **Knowledge Gaps Surfaced:** Automatically identifies missing information and follow-up research opportunities
- **Evolution Tracking:** See how your reading and thinking patterns evolve over time

**Success Metrics:**
- 100% chunk clustering (all 813 chunks assigned to clusters)
- ≥80% cluster quality (evaluated by coherence score ≥0.75)
- ≥90% knowledge card generation success rate
- ≥5 cross-cluster connections identified per major cluster
- Synthesis generation time: <30s per cluster (async, non-blocking)
- Cost impact: ≤$0.60/month additional (LLM API calls)
- MCP query latency: <500ms P95 for cluster/card retrieval

---

## 2. Background & Research Foundation

### Progressive Summarization in PKM (2025)

Modern personal knowledge management emphasizes **progressive summarization** (CODE workflow: Capture-Organize-**Distill**-Express). The distillation phase—extracting the most important insights—is where knowledge cards operate.

**Research Insight:** "Smart summaries can shrink 3,000-word reads into 10 bullet insights" (Source: PKM 2025 trends)

### Atomic Notes vs. Raw Highlights

**Zettelkasten Principle:** "The true atomic unit should be your own processed ideas, not raw highlights."

**Epic 2 Solution:** AI-generated knowledge cards bridge the gap:
- Raw highlight → Knowledge card (TL;DR + takeaways) → Foundation for future synthesis

### Semantic Search + Generative AI (RAG Enhancement)

**Research Insight:** "Combining semantic search with generative AI offers complementary benefits—retrieve top-k documents, then use pre-computed summaries for context-aware responses."

**Epic 2 Integration:** Knowledge cards serve as pre-computed summaries, accelerating MCP query comprehension.

### Knowledge Synthesis & Gap Analysis

**Research Finding:** "Generative AI can analyze lengthy documents and identify gaps or unanswered questions within synthesized content."

**Epic 2 Enhancement:** Automated gap analysis per cluster surfaces research opportunities and contradictions.

---

## 3. Scope & Core Use Cases

### In Scope (Epic 2)

#### **3.1 Semantic Clustering** (Story 2.1)
- Automatically group 813+ chunks by semantic similarity using 768-dim embeddings
- Assign each chunk to primary cluster (and optionally secondary clusters)
- Generate cluster metadata: size, coherence score, creation date
- Support threshold-based or K-means clustering algorithm

#### **3.2 LLM-Based Cluster Labeling** (Story 2.2)
- Generate human-readable cluster labels/names (e.g., "AI & Machine Learning", "Urban Planning")
- Create cluster descriptions (2-3 sentences explaining theme)
- Store cluster documents in Firestore `kb_clusters` collection
- Handle label updates on re-clustering

#### **3.3 Knowledge Card Generation** (Story 2.3)
- For each chunk, generate:
  - **One-line summary:** "Key insight in 1 sentence"
  - **3-5 key takeaways:** Actionable bullet points
  - **Related tags/themes:** Auto-extracted topics
  - **Source attribution:** Author, title, date
- Store knowledge cards in `kb_items.knowledge_card` field
- Optimize LLM prompts for concise, actionable output

#### **3.4 Cluster Synthesis & Overview** (Story 2.4)
- Generate cohesive synthesis per cluster:
  - **Cluster overview:** "What this cluster is about" (2-3 sentences)
  - **Key themes:** Synthesis of main ideas across all chunks in cluster
  - **Interesting patterns:** Recurring concepts or author perspectives
- Store synthesis in `kb_clusters.synthesis` field

#### **3.5 Cross-Cluster Knowledge Graph** (Story 2.7 - NEW)
- Identify explicit concept bridges between clusters using:
  - Embedding similarity between cluster centroids
  - LLM extraction of cross-topic mentions in chunk text
- Store weighted edges as `cross_cluster_links` in Firestore
- Example: "Urban Planning" cluster mentions "behavioral psychology" → link to Psychology cluster
- Enable MCP tool: `find_connections(topic_a, topic_b)` - "How do my notes on X relate to Y?"

#### **3.6 Synthesis Gap Analysis** (Story 2.8 - NEW)
- For each cluster, LLM generates:
  - **What's missing:** "You have 15 highlights on AI safety, but none discuss regulatory frameworks"
  - **Follow-up questions:** "Based on this cluster, you might explore: How does interpretability relate to safety?"
  - **Contradictions:** "These two highlights disagree on whether AGI is achievable"
- Store in `kb_clusters.gap_analysis` field
- Transforms knowledge base from archive to active exploration tool

#### **3.7 MCP Server Integration** (Story 2.5)
- Add 4 new tools to MCP server:
  - `get_clusters()` – List all clusters with metadata (label, size, coherence)
  - `get_cluster_chunks(cluster_id)` – Fetch chunks in cluster with knowledge cards
  - `get_cluster_synthesis(cluster_id)` – Fetch cluster summary + gap analysis
  - `find_connections(topic_a, topic_b)` – Discover cross-cluster knowledge bridges
- Test tools from Claude Desktop
- Document usage patterns and examples

#### **3.8 End-to-End Testing & Deployment** (Story 2.6)
- Integration test full clustering pipeline
- Validate clustering quality metrics (coherence, coverage)
- Performance testing (latency, cost)
- Deploy to production
- Update sprint-status.yaml with Epic 2 completion

### Out of Scope (Future Epics)

- **Weekly intelligence digest** – Covered in Epic 3 (Export & Distribution)
- **Visual knowledge graph UI** – Future enhancement (web visualization)
- **Manual cluster curation/renaming** – Future (currently LLM-generated only)
- **Hierarchical cluster management** – Deferred to Phase 2 (parent-child topics)
- **Temporal clustering** (reading evolution tracking) – Epic 4 or future
- **Evergreen note promotion** (highlight high-value insights) – Epic 4 or future
- **Cross-topic recommendation engine** – Future feature enhancement

---

## 4. Dependencies & Prerequisites

**From Epic 1 (Completed):**
- ✅ 813 chunks stored in Firestore `kb_items` collection
- ✅ 768-dimensional embeddings computed and accessible
- ✅ MCP server infrastructure running locally
- ✅ Firestore database with full read/write access
- ✅ Vertex AI Gemini API access (for LLM calls)

**New Technical Requirements (Epic 2):**
- Firestore schema extension: `kb_clusters` collection
- Knowledge card storage in `kb_items.knowledge_card` sub-field
- Clustering algorithm implementation (Python/Cloud Function)
- LLM prompts for label, synthesis, and gap analysis generation
- Cross-cluster graph storage and query capability
- MCP server extensions (4 new tools)

---

## 5. Technical Architecture

### 5.1 Data Model Extensions

#### **New Firestore Collection: `kb_clusters`**

```javascript
Document ID: cluster-{uuid}

Fields:
{
  label: "AI & Machine Learning",  // LLM-generated cluster name
  description: "Articles and highlights on AI, ML, deep learning concepts and applications",
  member_count: 247,  // Number of chunks in cluster
  created_at: Timestamp,
  updated_at: Timestamp,
  coherence_score: 0.87,  // Avg semantic similarity within cluster

  // Synthesis (Story 2.4)
  synthesis: {
    overview: "This cluster explores...",
    key_themes: ["Deep learning architectures", "AI safety", "LLM applications"],
    patterns: "Recurring focus on transformer models and emergent capabilities"
  },

  // Gap Analysis (Story 2.8 - NEW)
  gap_analysis: {
    missing_topics: ["Regulatory frameworks", "Energy consumption of large models"],
    follow_up_questions: [
      "How does interpretability relate to AI safety?",
      "What are the economic impacts of AI automation?"
    ],
    contradictions: [
      {
        description: "Disagreement on AGI timelines",
        chunk_ids: ["chunk-123", "chunk-456"]
      }
    ]
  },

  // Cross-cluster links (Story 2.7 - NEW)
  cross_cluster_links: [
    {
      target_cluster_id: "cluster-neuroscience",
      connection_strength: 0.73,
      bridge_concepts: ["neural networks", "cognitive architectures"],
      example_chunks: ["chunk-789", "chunk-101"]
    },
    {
      target_cluster_id: "cluster-philosophy",
      connection_strength: 0.68,
      bridge_concepts: ["consciousness", "intelligence definitions"],
      example_chunks: ["chunk-234", "chunk-567"]
    }
  ]
}
```

#### **Extension to `kb_items` Collection**

```javascript
Existing chunk document + new fields:

{
  // ... existing fields (id, title, content, embedding, etc.)

  // Clustering (Story 2.1)
  cluster_id: "cluster-{uuid}",  // Primary cluster assignment
  secondary_clusters: ["cluster-{uuid}", ...],  // Optional multi-cluster membership

  // Knowledge Card (Story 2.3)
  knowledge_card: {
    summary: "One-line key insight from this chunk",
    takeaways: [
      "First actionable takeaway",
      "Second key point",
      "Third important insight"
    ],
    tags: ["theme1", "theme2", "concept1"],
    generated_at: Timestamp
  }
}
```

---

### 5.2 Processing Pipeline

```
Daily Batch Job (Cloud Function triggered after chunk ingestion):

    ↓
┌─────────────────────────────────────────────────────────┐
│ 1. Load all chunks from kb_items (813+)                │
│    - Fetch chunk IDs, embeddings, content               │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Semantic Clustering (Story 2.1)                     │
│    - Use 768-dim embeddings for similarity calc         │
│    - Apply clustering algorithm (threshold-based/K-means)│
│    - Assign cluster IDs to chunks                       │
│    - Calculate coherence scores per cluster             │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Cluster Label Generation (Story 2.2)                │
│    - For each cluster: extract sample chunks            │
│    - LLM prompt: "Generate label + description"         │
│    - Create cluster docs in kb_clusters                 │
│    - Update chunks with cluster_id field                │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Knowledge Card Generation (Story 2.3)               │
│    - For each chunk: LLM generates summary + takeaways  │
│    - Update kb_items with knowledge_card field          │
│    - Batch updates for performance (100 chunks at a time)│
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 5. Cluster Synthesis (Story 2.4)                       │
│    - For each cluster: aggregate chunk content          │
│    - LLM generates overview + key themes + patterns     │
│    - Update kb_clusters.synthesis field                 │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 6. Cross-Cluster Knowledge Graph (Story 2.7)           │
│    - Calculate embedding similarity between centroids   │
│    - LLM extracts explicit cross-topic mentions         │
│    - Store weighted edges in cross_cluster_links        │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 7. Synthesis Gap Analysis (Story 2.8)                  │
│    - For each cluster: LLM analyzes synthesis           │
│    - Generate: missing topics, questions, contradictions│
│    - Update kb_clusters.gap_analysis field              │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 8. Save All Updates to Firestore                       │
│    - Batch write all cluster and chunk updates          │
│    - Transaction guarantees for consistency             │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│ 9. MCP Server Integration (Story 2.5)                  │
│    - Register 4 new tools in MCP server                 │
│    - Test tool invocation from Claude Desktop           │
└─────────────────────────────────────────────────────────┘

Total Pipeline Time: ~5-10 minutes for 813 chunks
```

---

### 5.3 Cost Impact Analysis

| Task | Model | Volume | Tokens Est. | Cost/Month |
|------|-------|--------|-------------|------------|
| 813 knowledge card summaries | Gemini 1.5 Flash | 813 cards | ~10K tokens | $0.10 |
| 50-100 cluster labels + descriptions | Gemini 1.5 Flash | ~75 clusters | ~5K tokens | $0.05 |
| 50-100 cluster syntheses | Gemini 1.5 Flash | ~75 clusters | ~20K tokens | $0.20 |
| Cross-cluster link extraction | Gemini 1.5 Flash | ~75 clusters | ~8K tokens | $0.08 |
| Gap analysis per cluster | Gemini 1.5 Flash | ~75 clusters | ~12K tokens | $0.12 |
| Embedding API (re-clustering) | Vertex AI Embeddings | As needed | ~2K tokens | $0.02 |
| **Total** | | | **~57K tokens** | **~$0.57/month** |

**Current Epic 1 Baseline:** $1.40/month
**Epic 2 Total:** $1.40 + $0.57 = **$1.97/month**
**Budget Status:** 60% under $5/month target ✅

---

## 6. Functional Requirements

| Req ID | Requirement | Priority | Story |
|--------|-----------|----------|-------|
| FR1 | System shall automatically cluster all 813+ chunks using semantic similarity with ≥0.75 coherence score | MUST | 2.1 |
| FR2 | System shall assign each chunk to exactly one primary cluster and 0-2 secondary clusters | MUST | 2.1 |
| FR3 | System shall generate human-readable cluster labels and descriptions via LLM | MUST | 2.2 |
| FR4 | System shall generate knowledge card (summary + 3-5 takeaways) for each chunk | MUST | 2.3 |
| FR5 | System shall generate cluster synthesis (overview + themes + patterns) for each cluster | MUST | 2.4 |
| FR6 | System shall identify and store cross-cluster connections with weighted edges | MUST | 2.7 |
| FR7 | System shall generate gap analysis (missing topics, questions, contradictions) per cluster | MUST | 2.8 |
| FR8 | System shall expose 4 new MCP tools for Claude Desktop access to clusters | MUST | 2.5 |
| FR9 | System shall complete full pipeline (clustering → cards → synthesis → gaps) within daily batch window | MUST | 2.6 |
| FR10 | System shall maintain backward compatibility with existing chunk queries | MUST | 2.6 |
| FR11 | System shall support on-demand re-clustering if chunk corpus changes significantly | SHOULD | 2.1 |
| FR12 | System shall handle edge cases: very small clusters (<5 items), singleton chunks | SHOULD | 2.1 |
| FR13 | System shall provide cluster quality metrics (coherence score, silhouette coefficient) | SHOULD | 2.1 |

---

## 7. Non-Functional Requirements

| Req ID | Requirement | Target | Story |
|--------|-----------|--------|-------|
| NFR1 | Clustering completion time for 813 chunks | <2 minutes | 2.1 |
| NFR2 | LLM API calls latency (label + synthesis generation) | <30s per cluster | 2.2, 2.4 |
| NFR3 | Knowledge card generation time (batch processing) | <5 minutes for 813 chunks | 2.3 |
| NFR4 | Firestore batch write time (all updates) | <10s | 2.6 |
| NFR5 | MCP tool query latency (cluster fetch) | <500ms (P95) | 2.5 |
| NFR6 | Cost increase vs. Epic 1 baseline | ≤$0.60/month | All |
| NFR7 | System availability during clustering (no impact on query tools) | ≥99% | 2.6 |
| NFR8 | Data consistency after batch job (transactional updates) | 100% | 2.6 |
| NFR9 | Cross-cluster link calculation accuracy | ≥85% user validation | 2.7 |
| NFR10 | Gap analysis relevance (useful questions/missing topics) | ≥80% user satisfaction | 2.8 |

---

## 8. Epic Stories Breakdown

**Story Sequencing Note:** Knowledge cards are generated first to provide immediate value and enable enhanced clustering that uses both embeddings and card-extracted keywords.

---

### **Story 2.1: Knowledge Card Generation**
**Goal:** Create TL;DR summaries with key takeaways for each chunk

**Rationale:** Generate atomic note summaries first to:
- Deliver immediate value (scan 813 chunks via knowledge cards)
- Enable enhanced clustering (use card keywords + embeddings for dual-signal clustering)
- Follow progressive summarization best practices (distill before organize)

**Tasks:**
- Design knowledge card schema
- Create LLM prompt (summary + 3-5 takeaways)
- Implement batch processing (100 chunks per batch)
- Update `kb_items.knowledge_card` field
- Optimize prompt for concise, actionable output

**Acceptance Criteria:**
- 813/813 chunks have knowledge cards
- Summaries are 1-2 sentences max
- Takeaways are actionable and distinct
- Cost ≤$0.10/month
- Generation time <5 minutes total

**Estimated Effort:** 4-5 hours

---

### **Story 2.2: Semantic Clustering Algorithm (Enhanced)**
**Goal:** Automatically group 813+ chunks into semantic clusters using embeddings + knowledge card keywords

**Rationale:** Use dual-signal clustering (embeddings + card-extracted themes) for higher quality topic grouping.

**Tasks:**
- Implement clustering algorithm (threshold-based or K-means)
- Load embeddings from Firestore `kb_items`
- Extract keywords/themes from knowledge cards (generated in Story 2.1)
- Calculate similarity matrix using cosine similarity on embeddings
- Enhance clustering with card keyword overlap
- Assign cluster IDs to chunks (primary + optional secondary)
- Calculate coherence scores per cluster
- Handle edge cases (small clusters, singletons)

**Acceptance Criteria:**
- 100% of chunks assigned to clusters
- Average cluster coherence ≥0.75
- No clusters with <3 chunks (merge or reassign)
- **Clustering produces quality results within reasonable time (≤10 minutes acceptable for initial 813-chunk clustering)**
- Delta clustering (<1 min for batches of ≤50 new chunks)

**Estimated Effort:** 5-7 hours (enhanced algorithm)

---

### **Story 2.3: LLM-Based Cluster Labeling**
**Goal:** Generate human-readable cluster names and descriptions

**Tasks:**
- Create LLM prompt for label generation
- Sample representative chunks per cluster
- Use knowledge cards as input for richer context
- Generate label + 2-3 sentence description
- Create cluster documents in `kb_clusters` collection
- Update chunks with `cluster_id` field

**Acceptance Criteria:**
- All clusters have labels and descriptions
- Labels are concise (<5 words) and descriptive
- Cost ≤$0.05/month for label generation
- Labels match cluster content (manual validation sample)

**Estimated Effort:** 4-5 hours

---

### **Story 2.4: Cluster Synthesis & Overview**
**Goal:** Generate cohesive summaries per cluster with key themes

**Tasks:**
- Design synthesis schema (overview, themes, patterns)
- Create LLM prompt for cluster-level synthesis
- Aggregate chunk content per cluster
- Generate synthesis and store in `kb_clusters`
- Handle large clusters (>50 chunks) with sampling

**Acceptance Criteria:**
- All clusters have synthesis
- Synthesis captures main themes accurately
- Patterns section identifies recurring concepts
- Cost ≤$0.20/month
- Synthesis generation <30s per cluster

**Estimated Effort:** 5-7 hours

---

### **Story 2.5: MCP Server Integration**
**Goal:** Expose clustering and knowledge card tools to Claude Desktop

**Tasks:**
- Add 4 new tool definitions to MCP server:
  - `get_clusters()` – List clusters with metadata
  - `get_cluster_chunks(cluster_id)` – Fetch chunks + cards
  - `get_cluster_synthesis(cluster_id)` – Fetch summary + gaps
  - `find_connections(topic_a, topic_b)` – Cross-cluster bridges
- Implement tool handlers in `tools.py`
- Test tools from Claude Desktop
- Document usage with examples

**Acceptance Criteria:**
- 4 tools registered and callable from Claude
- Tool responses <500ms (P95)
- All tools return correct data structure
- Documentation includes usage examples

**Estimated Effort:** 3-4 hours

---

### **Story 2.6: End-to-End Testing & Deployment**
**Goal:** Validate full pipeline and deploy to production

**Tasks:**
- Integration test: clustering → labeling → cards → synthesis
- Performance testing (latency, throughput)
- Cost validation (verify ≤$0.60/month)
- Quality metrics: coherence score, user validation sample
- Deploy to production
- Update sprint-status.yaml

**Acceptance Criteria:**
- Full pipeline runs successfully end-to-end
- All 813 chunks clustered and cards generated
- Cost impact verified ≤$0.60/month
- No performance degradation on existing queries
- Epic 2 marked complete in sprint-status.yaml

**Estimated Effort:** 4-6 hours

---

### **Story 2.7: Cross-Cluster Knowledge Graph** ⭐ NEW
**Goal:** Identify and store explicit concept bridges between clusters

**Tasks:**
- Calculate embedding similarity between cluster centroids
- Identify top-N related cluster pairs (threshold: 0.65+)
- Use LLM to extract explicit cross-topic mentions in chunks
- Store weighted edges in `cross_cluster_links`
- Implement MCP tool: `find_connections(topic_a, topic_b)`

**Acceptance Criteria:**
- ≥5 cross-cluster links identified per major cluster
- Link strength scores accurate (manual validation)
- MCP tool returns relevant connections
- Bridge concepts clearly documented
- Example chunks illustrate connections

**Estimated Effort:** 5-6 hours

---

### **Story 2.8: Synthesis Gap Analysis** ⭐ NEW
**Goal:** Automatically identify knowledge gaps, questions, and contradictions per cluster

**Tasks:**
- Design gap analysis schema (missing topics, questions, contradictions)
- Create LLM prompt for gap identification
- Generate gap analysis per cluster
- Store in `kb_clusters.gap_analysis` field
- Integrate into `get_cluster_synthesis()` MCP tool response

**Acceptance Criteria:**
- All clusters have gap analysis
- Missing topics are relevant and actionable
- Follow-up questions are thought-provoking
- Contradictions (if any) are accurately identified
- ≥80% user satisfaction with gap relevance

**Estimated Effort:** 4-5 hours

---

## 9. Timeline & Effort Estimate

| Story | Effort | Duration | Dependencies |
|-------|--------|----------|--------------|
| 2.1: Knowledge Cards | 4-5 hours | 1 day | Epic 1 complete |
| 2.2: Semantic Clustering (Enhanced) | 5-7 hours | 1-2 days | Story 2.1 |
| 2.3: Cluster Labeling | 4-5 hours | 1 day | Story 2.2 |
| 2.4: Synthesis & Overview | 5-7 hours | 1-2 days | Story 2.2, 2.3 |
| 2.7: Cross-Cluster Graph | 5-6 hours | 1 day | Story 2.1, 2.2 |
| 2.8: Gap Analysis | 4-5 hours | 1 day | Story 2.4 |
| 2.5: MCP Integration | 3-4 hours | <1 day | Story 2.4, 2.7, 2.8 |
| 2.6: Testing & Deploy | 4-6 hours | 1 day | All stories |
| **Total** | **33-44 hours** | **5-7 days** | |

**Recommended Sprint Plan:**
- **Week 1:** Stories 2.1, 2.2, 2.3 (clustering foundation + cards)
- **Week 2:** Stories 2.4, 2.7, 2.8, 2.5, 2.6 (synthesis + enhancements + deploy)

---

## 10. Risks & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|-----------|
| Clustering quality poor (low coherence) | Users unable to browse topics effectively | Medium | Use silhouette coefficient; tune threshold; manual validation sample |
| LLM-generated labels inaccurate | Cluster discovery degraded | Medium | Validate with sample; iterate prompts; add user feedback loop (future) |
| Cost overrun on LLM calls | Exceeds budget | Low | Cap API calls; batch processing; optimize prompt lengths; monitor usage |
| Performance issues during batch job | Query service slowdown | Low | Run clustering in off-peak hours; use async processing; isolate compute |
| Firestore quota limits | Write failures during batch | Low | Pre-calculate write volume; implement incremental updates; request quota increase |
| Knowledge cards too generic | Low user value | Medium | Optimize prompts; use chunk context; iterate based on samples |
| Cross-cluster links spurious | Noise in knowledge graph | Medium | Set similarity threshold conservatively (0.65+); LLM validation; manual review |
| Gap analysis irrelevant | Low engagement | Medium | Tune LLM prompt; use cluster context; iterate based on feedback |

---

## 11. Success Criteria (Definition of Done)

### **Epic 2 Complete When:**

**Story 2.1 Done:**
- ✓ 813/813 chunks successfully assigned to clusters
- ✓ No orphaned chunks
- ✓ Average cluster coherence ≥0.75
- ✓ Clustering time <2 minutes

**Story 2.2 Done:**
- ✓ All clusters have labels and descriptions
- ✓ Labels are accurate (manual validation sample ≥80%)
- ✓ Cost ≤$0.05/month

**Story 2.3 Done:**
- ✓ 813/813 chunks have knowledge cards
- ✓ Summaries concise and actionable
- ✓ Cost ≤$0.10/month
- ✓ Generation time <5 minutes

**Story 2.4 Done:**
- ✓ All clusters have synthesis
- ✓ Synthesis captures key themes accurately
- ✓ Cost ≤$0.20/month

**Story 2.7 Done:**
- ✓ ≥5 cross-cluster links per major cluster
- ✓ Link accuracy ≥85% (manual validation)
- ✓ MCP tool returns relevant connections

**Story 2.8 Done:**
- ✓ All clusters have gap analysis
- ✓ Gap relevance ≥80% user satisfaction
- ✓ Follow-up questions thought-provoking

**Story 2.5 Done:**
- ✓ 4 tools registered and callable from Claude Desktop
- ✓ Tool latency <500ms (P95)
- ✓ Documentation complete with examples

**Story 2.6 Done:**
- ✓ Full pipeline tested end-to-end
- ✓ Cost verified ≤$0.60/month
- ✓ Deployed to production
- ✓ Epic 2 marked complete in sprint-status.yaml
- ✓ No performance degradation on existing queries

---

## 12. Next Steps

### **Immediate Actions:**

1. **Architecture Review** – Validate data model and processing pipeline (Architect agent)
   - Review Firestore schema extensions
   - Validate clustering algorithm choice
   - Approve LLM prompt strategy

2. **Technical Spike** – Evaluate clustering algorithms
   - Test threshold-based vs. K-means on sample data
   - Measure coherence scores
   - Select optimal approach

3. **LLM Prompt Prototyping** – Iterate on prompts for:
   - Cluster labels (concise, descriptive)
   - Knowledge cards (summary + takeaways)
   - Synthesis (overview + themes + gaps)

4. **Sprint Planning** – Break Epic 2 into detailed stories with:
   - Acceptance criteria per story
   - Task breakdown
   - Time estimates

5. **Development Start** – Begin Story 2.1 (Semantic Clustering)

### **Future Enhancements (Epic 3+):**

- Temporal clustering (track reading evolution over time)
- Evergreen note promotion (highlight high-value insights)
- Visual knowledge graph UI (web visualization)
- Manual cluster curation/renaming
- Hierarchical topic management (parent-child clusters)
- Weekly intelligence digest with cluster highlights

---

**Document Owner:** John (Product Manager)

**Stakeholders:** Chris (Developer), Architect, SM

**Last Review:** 2025-10-31

**Next Review:** Upon architecture review completion

**Status:** Ready for architecture review and sprint planning

