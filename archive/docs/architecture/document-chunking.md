# Document Chunking Strategy

## Overview

This document defines the intelligent document chunking approach for KX Hub's knowledge base. The strategy splits large documents into optimally-sized chunks with semantic awareness and overlap to improve vector search relevance while maintaining context preservation.

## Problem Context

**Current State (Pre-1.6):**
- One document = One 768-dim embedding vector
- Large books (100+ highlights, 20KB+) lose granularity
- Search returns entire book references, not specific passages
- Extra round trip required: Firestore query → GCS fetch for content

**Target State (Post-1.6):**
- Optimal-sized chunks (400-600 tokens) get individual embeddings
- Passage-level search results with context
- Single Firestore query includes full content
- Better vector quality due to optimal context window usage

---

## Chunking Strategy

### 1. Token Counting

**Approach:** Use `tiktoken` library (OpenAI's tokenizer) as proxy for Gemini token counting.

**Rationale:**
- Gemini token counts are highly correlated with OpenAI tokenizers
- Tiktoken is lightweight, well-tested, and widely available
- Better than character-based heuristics (0.25 char/token ratio)

**Configuration:**
```python
CHUNK_TARGET_TOKENS = 512        # Ideal chunk size
CHUNK_MAX_TOKENS = 1024          # Hard limit before forced split
CHUNK_MIN_SIZE_TOKENS = 100      # Minimum viable chunk
CHUNK_OVERLAP_TOKENS = 75        # Context overlap between chunks
```

**Practical Equivalents:**
- 512 tokens ≈ 2,048 characters ≈ 200-300 words
- 1024 tokens ≈ 4,096 characters ≈ 400-600 words
- 75 tokens ≈ 300 characters ≈ 30-50 words

---

### 2. Chunking Algorithm

**Approach:** Hierarchical semantic boundary detection with sliding window overlap.

```
Algorithm: Intelligent Document Chunking

Input: markdown_content (parsed document with frontmatter)
Output: list of chunks with overlaps

1. Parse YAML frontmatter → store for chunk enrichment
2. Extract content (everything after ---)
3. Split by primary boundary (highlights) → block_list
4. For each block in block_list:
   a. If block < CHUNK_MIN_SIZE: skip (combine with next)
   b. If block <= CHUNK_TARGET_TOKENS:
      - Create single chunk from block
   c. If block > CHUNK_TARGET_TOKENS:
      - Split block using secondary boundaries:
        i. Paragraph boundaries (\n\n)
        ii. Sentence boundaries (. followed by uppercase)
        iii. Token limit (fallback hard split)
      - Apply sliding window overlap (CHUNK_OVERLAP_TOKENS)
5. For each chunk:
   a. Prepend overlap from previous chunk (if exists)
   b. Append overlap to next chunk (if exists)
   c. Track overlap_start and overlap_end character counts
6. Inject chunk-specific frontmatter
7. Return chunked_list with metadata
```

---

### 3. Semantic Boundary Detection

**Priority Order (highest to lowest):**

| Priority | Boundary Type | Pattern | Use Case |
|----------|---------------|---------|----------|
| 1 (Primary) | Highlight | `^> ` (blockquote start) | Between highlights in Readwise exports |
| 2 (Secondary) | Paragraph | `\n\n` (double newline) | Between paragraphs within highlights |
| 3 (Tertiary) | Sentence | `. ` + uppercase letter | Mid-paragraph splits |
| 4 (Fallback) | Token limit | Hard split at CHUNK_MAX_TOKENS | Last resort |

**Example:**
```markdown
> Quote 1
> - Location: Page 10
> - Note: Personal reflection

> Quote 2
> - Location: Page 42
> - Note: Key insight

Paragraph 1 of notes. This is sentence 1. This is sentence 2.

Paragraph 2 of notes. This is another sentence.
```

Boundaries detected:
1. Between `> Quote 1` block and `> Quote 2` block → PRIMARY
2. Between note text and first paragraph → SECONDARY
3. Between sentences within paragraph → TERTIARY (if needed)

---

### 4. Overlap Strategy

**Why Overlap?**
- Preserve context at chunk boundaries
- Prevent information loss when queries fall at split points
- Improve semantic continuity for RAG applications

**Sliding Window Approach:**

```
Document: [==Chunk 1==][OVERLAP_1][==Chunk 2==][OVERLAP_2][==Chunk 3==]

Where:
- Chunk N: CHUNK_TARGET_TOKENS
- OVERLAP: CHUNK_OVERLAP_TOKENS (shared with adjacent chunks)

Character Counts:
- Chunk start: document_offset
- Chunk end: document_offset + chunk_length
- Overlap start: document_offset (shared with previous chunk)
- Overlap end: document_offset + overlap_length (shared with next chunk)
```

**Example with Tokens:**

```
Original chunk (600 tokens): "The quick brown fox jumps over the lazy dog..."

Split point (target 512 tokens):
- Chunk 1: "The quick brown fox jumps over the lazy dog..." (512 tokens)
- Overlap: "...lazy dog. The brown fox..." (75 tokens, end of Chunk 1)
- Chunk 2: "...lazy dog. The brown fox... and continued content" (512 tokens)
```

**Metadata Tracking:**
```yaml
chunk_1:
  token_count: 512
  char_start: 0
  char_end: 2048
  overlap_end: 300      # Last 300 chars belong to next chunk too

chunk_2:
  token_count: 512
  char_start: 1748      # Starts 300 chars before "end" of Chunk 1
  char_end: 3796
  overlap_start: 0      # First 300 chars shared with previous
  overlap_end: 300      # Last 300 chars shared with next
```

---

### 5. Frontmatter Injection

**Original Frontmatter (from Readwise):**
```yaml
---
id: '41094950'
title: "Thinking, Fast and Slow"
author: "Daniel Kahneman"
source: kindle
url: https://readwise.io/books/41094950
created_at: 2024-06-01T13:22:09.640Z
updated_at: 2024-06-01T13:22:09.641Z
tags: [psychology, behavioral-economics]
highlight_count: 156
user_book_id: 41094950
category: books
---
```

**Chunk-Specific Frontmatter (generated during chunking):**
```yaml
---
# Original document context
doc_id: '41094950'
title: "Thinking, Fast and Slow"
author: "Daniel Kahneman"
source: kindle
category: books
tags: [psychology, behavioral-economics]

# Chunk-specific fields
chunk_id: '41094950-chunk-003'
chunk_index: 3
total_chunks: 25

# Overlap tracking (for retrieval optimization)
overlap_start: 50      # First 50 chars are overlap from previous
overlap_end: 75        # Last 75 chars are overlap into next chunk
---
```

**Benefits:**
- Each chunk is self-contained with parent context
- No secondary lookup needed to understand document origin
- Supports filtering by book/author/category at chunk level
- Enables parent-child relationship tracking in Firestore

---

## Implementation Details

### Vector Index Schema

**Firestore `kb_items` collection:**

```python
{
    "chunk_id": "41094950-chunk-003",           # Primary key (string)
    "parent_doc_id": "41094950",                # Reference to original doc
    "chunk_index": 3,                           # Position in sequence
    "total_chunks": 25,                         # Total chunks from parent

    # Metadata from parent document
    "title": "Thinking, Fast and Slow",
    "author": "Daniel Kahneman",
    "source": "kindle",
    "category": "books",
    "tags": ["psychology", "behavioral-economics"],

    # Chunk content (NEW - eliminates GCS fetch)
    "content": "Full text of chunk with overlap...",

    # Vector embedding (768 dimensions)
    "embedding": Vector([0.1, 0.2, ..., 0.3]),  # firestore_v1.vector.Vector

    # Chunk metadata
    "chunk_boundaries": {
        "start": 5120,                          # Char offset in original doc
        "end": 7240
    },
    "overlap_start": 50,                        # Overlap with previous chunk
    "overlap_end": 75,                          # Overlap with next chunk
    "token_count": 512,                         # Actual token count

    # Processing status
    "embedding_status": "complete",             # complete|pending|failed
    "embedding_model": "gemini-embedding-001",
    "content_hash": "sha256:...",

    # Timestamps
    "created_at": Timestamp(...),
    "updated_at": Timestamp(...),
}
```

**Firestore Indexes:**
```
Composite indexes needed:
- (parent_doc_id, chunk_index)                  # Retrieve all chunks of document
- (embedding) with vector index                 # Vector search queries
- (source, category, tags) for filtering        # Metadata filtering
```

---

## Cost Impact Analysis

### Embedding API Costs

| Metric | Current | Proposed | Change |
|--------|---------|----------|--------|
| Total documents | 271 | 271 | - |
| Chunks per document | 1 | 5 (avg) | +400% |
| Total embeddings | 271 | 1,350 | +398% |
| Embedding cost/month | $0.10 | $0.50 | +$0.40 |

**Calculation:**
- Current: 271 books × 1 embedding × $0.0003/embedding ≈ $0.08/month
- Proposed: 1,350 chunks × $0.0003/embedding ≈ $0.40/month

### Storage Costs

| Component | Current | Proposed | Change |
|-----------|---------|----------|--------|
| Firestore (metadata only) | $0.10 | $0.15 | +$0.05 |
| GCS (markdown + retrieval) | $0.05 | $0.00 | -$0.05 |
| **Net storage** | **$0.15** | **$0.15** | **$0.00** |

### Retrieval Performance Gains

| Metric | Current | Proposed | Benefit |
|--------|---------|----------|---------|
| Round trips per query | 2 | 1 | -50% |
| Average latency | ~200ms | ~100ms | -50% |
| Cold start penalty | High (GCS) | None | Eliminated |

### Total System Cost Impact

```
Current System:
- Embeddings: $0.10
- Vector Storage: $0.10
- Generative: $0.00
- Functions/Storage: $0.50
- Firestore reads/writes: $0.20
- Total: $0.90/month

Proposed System:
- Embeddings: $0.50 (+$0.40)
- Vector Storage: $0.10 (no change)
- Generative: $0.00
- Functions/Storage: $0.50 (slight increase)
- Firestore reads/writes: $0.20
- Total: $1.30/month (+$0.40)

ROI:
- Cost increase: +44% (+$0.40/month)
- Benefits:
  - Passage-level search results
  - 50% faster retrieval (1 query vs 2)
  - Better vector quality (optimal context)
  - Simpler architecture (no GCS in retrieval path)
```

**Verdict:** Excellent trade-off. Pay 40¢/month for significantly better UX and simpler architecture.

---

## Testing Strategy

### Unit Tests

1. **Token Counting**
   - Test `calculate_tokens()` against known text samples
   - Validate correlation with actual Gemini tokens (sampling)

2. **Semantic Boundary Detection**
   - Test highlight boundary detection (blockquote patterns)
   - Test paragraph boundary detection (double newline)
   - Test sentence boundary detection (period + uppercase)

3. **Overlap Calculation**
   - Verify overlap_start/overlap_end char counts
   - Validate no data loss at boundaries
   - Check overlap size consistency

4. **Chunking Algorithm**
   - Small document (single chunk) - should not split
   - Medium document (3-5 chunks) - split at boundaries
   - Large document (20+ chunks) - proper overlap application

5. **Frontmatter Injection**
   - Verify chunk_id generation (format: `{doc_id}-chunk-{index}`)
   - Validate metadata preservation
   - Check YAML serialization

### Integration Tests

1. **End-to-End Pipeline**
   - Readwise ingest → JSON
   - Normalize (chunking) → multiple markdowns
   - Embed → Firestore write
   - Vector search query → verify chunk retrieval

2. **Data Integrity**
   - No content loss during chunking
   - Overlaps correctly tracked
   - Parent-child relationships valid

3. **Performance**
   - Query latency < 100ms
   - Embedding generation consistent
   - No GCS calls in retrieval path

---

## Configuration

**Environment Variables:**

```bash
# Token-based chunking
CHUNK_TARGET_TOKENS=512
CHUNK_MAX_TOKENS=1024
CHUNK_MIN_SIZE_TOKENS=100
CHUNK_OVERLAP_TOKENS=75

# Boundary detection sensitivity
ENABLE_HIGHLIGHT_BOUNDARY=true      # Primary
ENABLE_PARAGRAPH_BOUNDARY=true      # Secondary
ENABLE_SENTENCE_BOUNDARY=true       # Tertiary
FALLBACK_TO_TOKEN_SPLIT=true        # Fallback
```

**Pipeline Configuration:**

```yaml
# In src/normalize/main.py
chunking_config:
  enabled: true
  strategy: "semantic_hierarchical"
  target_tokens: 512
  max_tokens: 1024
  overlap_tokens: 75
  min_size: 100
```

---

## Deployment Checklist

- [ ] Add `tiktoken` to `src/embed/requirements.txt` and all relevant functions
- [ ] Create `src/common/chunker.py` with all chunking logic
- [ ] Update `src/normalize/main.py` to use chunking
- [ ] Update `src/embed/main.py` to handle chunk metadata
- [ ] Create comprehensive unit tests
- [ ] Run integration tests with test fixtures
- [ ] Update documentation across architecture/PRD
- [ ] Clear Firestore `kb_items` and `pipeline_items` collections
- [ ] Clear GCS `markdown-normalized` bucket
- [ ] Deploy Cloud Functions with chunking enabled
- [ ] Trigger full re-ingest from Readwise
- [ ] Monitor chunk metrics in logs

---

## Future Enhancements

1. **Dynamic Chunk Sizing** - Adjust chunk size based on content density
2. **Chunk Clustering** - Group semantically similar chunks across documents
3. **Automatic Link Detection** - Suggest connections between chunks
4. **Temporal Analysis** - Track when chunks were read/highlighted
5. **Custom Overlap Rules** - Different overlap strategies for different content types

---
