# Story 4.2: Create `get_chunk` Tool with Embedded Related Chunks and Knowledge Card

Status: review

## Story

As an **AI assistant using kx-hub MCP tools**,
I want a **single `get_chunk` tool that returns full chunk details with knowledge card and related chunks embedded**,
so that **I can retrieve comprehensive chunk information in one API call instead of chaining `get_related_chunks` and `get_knowledge_card`**.

## Acceptance Criteria

1. **New `get_chunk` tool registered** in MCP server with chunk_id parameter
2. **Full chunk content returned** including all fields (title, author, source, tags, content, URLs)
3. **Knowledge card embedded** by default (summary + takeaways) from chunk.knowledge_card field
4. **Related chunks included** by default via vector similarity (default limit: 5)
5. **Cluster membership info included** showing which cluster(s) the chunk belongs to
6. **All URLs included** (readwise_url, source_url, highlight_url) per Story 2.7
7. **Optional include_related parameter** allows disabling related chunks retrieval (default: true)
8. **Optional related_limit parameter** controls max related chunks (default: 5)
9. **Returns gracefully** when chunk_id not found or knowledge card missing
10. **Replaces 2 separate tools** (`get_related_chunks` and `get_knowledge_card`) reducing tool count

## Tasks / Subtasks

- [x] Task 1: Implement `get_chunk` function in tools.py (AC: 1-9)
  - [x] 1.1 Define parameter schema (chunk_id, include_related, related_limit)
  - [x] 1.2 Fetch chunk by ID from Firestore
  - [x] 1.3 Extract and format knowledge card from chunk data
  - [x] 1.4 Get related chunks via vector similarity (if include_related=true)
  - [x] 1.5 Extract cluster membership info from chunk.cluster_id
  - [x] 1.6 Format all URLs using _format_urls helper
  - [x] 1.7 Handle missing chunk, missing knowledge card gracefully

- [x] Task 2: Register `get_chunk` tool in main.py (AC: 1)
  - [x] 2.1 Add Tool definition with complete inputSchema
  - [x] 2.2 Add handler in call_tool_handler switch

- [x] Task 3: Unit tests (AC: 1-9)
  - [x] 3.1 Test get chunk with all fields included
  - [x] 3.2 Test knowledge card extraction and formatting
  - [x] 3.3 Test related chunks retrieval and ranking
  - [x] 3.4 Test cluster membership info
  - [x] 3.5 Test include_related=false option
  - [x] 3.6 Test related_limit parameter
  - [x] 3.7 Test chunk not found (error handling)
  - [x] 3.8 Test missing knowledge card (graceful degradation)
  - [x] 3.9 Test URL fields inclusion

- [ ] Task 4: Integration testing (AC: 1-10)
  - [ ] 4.1 Test via MCP protocol with Claude Desktop
  - [ ] 4.2 Verify response format matches expected schema
  - [ ] 4.3 Verify all embedded data (card, related, cluster, URLs) present

## Dev Notes

### Learnings from Previous Story

**From Story 4-1-search-kb-unified (Status: review)**

- **New Pattern Created**: Unified tool interface with flexible filter object - apply same pattern for optional parameters
- **Helper Functions Available**: `_format_urls()`, `_format_knowledge_card()`, `_format_cluster_info()` already exist in tools.py - REUSE these
- **Testing Pattern Established**: TestSearchKBUnified class with 11 comprehensive tests - follow same structure and naming
- **Schema Design**: Use nested object for optional parameters (like filters in search_kb) - consider for include_related/related_limit
- **Error Handling**: Validate input, return structured error responses - apply to chunk_id validation
- **Files Modified**: tests/test_mcp_tools.py already has test infrastructure - extend with TestGetChunk class

[Source: stories/4-1-search-kb-unified.md#Dev-Agent-Record]

### Architecture Pattern

The `get_chunk` tool consolidates 2 separate tools:
- `get_related_chunks` → embedded as related array in response
- `get_knowledge_card` → embedded as knowledge_card object in response

This follows Epic 4's consolidation principle: reduce tool count while maintaining functionality.

### Parameter Schema

```json
{
  "type": "object",
  "properties": {
    "chunk_id": {
      "type": "string",
      "description": "Chunk ID to retrieve",
      "required": true
    },
    "include_related": {
      "type": "boolean",
      "description": "Include related chunks via vector similarity (default true)",
      "default": true
    },
    "related_limit": {
      "type": "integer",
      "description": "Maximum related chunks to return (default 5)",
      "default": 5,
      "minimum": 1,
      "maximum": 20
    }
  },
  "required": ["chunk_id"]
}
```

### Expected Response Format

```json
{
  "chunk_id": "abc123",
  "title": "Book Title",
  "author": "Author Name",
  "source": "kindle",
  "tags": ["ai", "agents"],
  "content": "Full chunk text...",
  "chunk_info": "1/5",
  "knowledge_card": {
    "summary": "AI-generated summary of the chunk",
    "takeaways": [
      "Key point 1",
      "Key point 2"
    ]
  },
  "cluster": {
    "cluster_id": ["cluster-28"],
    "cluster_name": "AI Agents & LLMs",
    "description": "Content about AI agents and large language models"
  },
  "related_chunks": [
    {
      "chunk_id": "def456",
      "title": "Related Book",
      "author": "Another Author",
      "snippet": "Preview of related content...",
      "similarity_score": 0.89
    }
  ],
  "readwise_url": "https://readwise.io/...",
  "source_url": "https://example.com/...",
  "highlight_url": "https://readwise.io/highlights/..."
}
```

### Implementation Approach

1. **Fetch chunk** by ID from Firestore using `firestore_client.get_chunk_by_id()`
2. **Extract knowledge card** from chunk.knowledge_card field (if exists)
3. **Get related chunks** if include_related=true:
   - Use chunk.embedding vector
   - Call `firestore_client.find_nearest()` with chunk's embedding
   - Filter out the source chunk from results
   - Limit to related_limit
4. **Extract cluster info** using `_format_cluster_info(chunk)`
5. **Extract URLs** using `_format_urls(chunk)`
6. **Format response** with all embedded data

### Existing Functions to Reuse

From `tools.py`:
- `_format_urls()` - Extract URL fields (Story 2.7)
- `_format_knowledge_card()` - Format knowledge card from chunk data
- `_format_cluster_info()` - Get cluster metadata from chunk.cluster_id

From `firestore_client.py`:
- `get_chunk_by_id(chunk_id)` - Fetch single chunk
- `find_nearest(embedding_vector, limit)` - Vector similarity search for related chunks

From `embeddings.py`:
- No embedding generation needed (chunk already has embedding)

### Project Structure Notes

- New function added to: `src/mcp_server/tools.py`
- Tool registration in: `src/mcp_server/main.py`
- Tests added to: `tests/test_mcp_tools.py` (new TestGetChunk class)
- No new files required - extends existing module

Following pattern from Story 4.1:
- Single function in tools.py
- Registration in main.py
- Comprehensive test class in test_mcp_tools.py

### Testing Strategy

Unit tests will mock Firestore calls. Integration tests will use real MCP protocol.

Key test scenarios:
1. Get chunk with all embedded data (knowledge card + related + cluster + URLs)
2. Get chunk with include_related=false
3. Get chunk with custom related_limit
4. Get chunk where knowledge_card is missing (graceful)
5. Get chunk that doesn't exist (error handling)
6. Get chunk with no related chunks available
7. Verify URL fields always included
8. Verify cluster info extraction

### References

- [Source: docs/epics.md#Epic-4-Story-4.2] - Tool specification
- [Source: docs/epics.md#Consolidated-Tool-Spec-get_chunk] - Detailed parameters and return format
- [Source: src/mcp_server/tools.py] - Existing helper functions (_format_*)
- [Source: src/mcp_server/firestore_client.py] - get_chunk_by_id, find_nearest
- [Source: stories/4-1-search-kb-unified.md] - Pattern for unified tool implementation and testing

## Dev Agent Record

### Context Reference

- docs/stories/4-2-get-chunk-enhanced.context.xml

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

N/A - No integration testing required for unit test phase

### Completion Notes List

**Implementation Complete - 2025-12-19**

✅ **Task 1 - Implemented get_chunk function** (src/mcp_server/tools.py:121-250)
- Created comprehensive get_chunk function following Story 4.1 pattern
- Reused existing helper functions (_format_urls, _format_knowledge_card, _format_cluster_info)
- Used firestore_client.get_chunk_by_id() and find_nearest() for data retrieval
- Implemented source chunk filtering in related chunks results
- Added parameter validation for related_limit (1-20 range)
- Updated module docstring to include new tool

✅ **Task 2 - Registered get_chunk tool in MCP server** (src/mcp_server/main.py)
- Added Tool definition with complete inputSchema (lines 144-169)
- Registered handler in call_tool_handler switch (lines 661-666)
- Tool positioned after search_kb in tools list for logical ordering

✅ **Task 3 - Comprehensive unit test coverage** (tests/test_mcp_tools.py:527-852)
- Created TestGetChunk class with 8 comprehensive tests
- Coverage for all 9 acceptance criteria (AC 2-9)
- All tests passing (8/8) with existing test suite intact (25/25 total)
- Test scenarios:
  1. test_get_chunk_with_all_fields - AC 2,3,4,5,6
  2. test_get_chunk_with_include_related_false - AC 7
  3. test_get_chunk_with_custom_related_limit - AC 8
  4. test_get_chunk_not_found - AC 9 (error handling)
  5. test_get_chunk_missing_knowledge_card - AC 9 (graceful degradation)
  6. test_get_chunk_no_embedding_for_related - Edge case handling
  7. test_get_chunk_all_url_fields - AC 6
  8. test_get_chunk_filters_out_source_chunk - Constraint validation

**Test Results:**
- All 8 new tests PASSED
- All 25 total tests PASSED (17 existing + 8 new)
- Test execution time: ~2.1s
- Zero regressions in existing functionality

**Acceptance Criteria Status:**
- AC 1: ✅ get_chunk tool registered in MCP server
- AC 2: ✅ Full chunk content returned with all fields
- AC 3: ✅ Knowledge card embedded by default
- AC 4: ✅ Related chunks included via vector similarity (default limit 5)
- AC 5: ✅ Cluster membership info included
- AC 6: ✅ All URLs included (readwise_url, source_url, highlight_url)
- AC 7: ✅ Optional include_related parameter (default true)
- AC 8: ✅ Optional related_limit parameter (default 5, max 20)
- AC 9: ✅ Graceful error handling for missing chunk/knowledge card
- AC 10: ⚠️ Integration testing pending (Task 4) - ready for MCP protocol validation

**Code Quality Notes:**
- Followed existing code patterns from Story 4.1 (search_kb)
- Proper error handling with ValueError for missing chunks
- Comprehensive logging for debugging
- Clean separation of concerns (fetch, format, assemble)
- No code duplication - reused all helper functions
- Backwards compatible - existing tools remain functional

**Next Steps:**
- Task 4: Integration testing via MCP protocol
- Recommended: Test with Claude Desktop to verify MCP protocol integration
- Epic 4.6: Deprecate get_related_chunks and get_knowledge_card after integration validation

### File List

**Modified Files:**
1. src/mcp_server/tools.py - Added get_chunk function (130 lines)
2. src/mcp_server/main.py - Registered get_chunk tool (tool definition + handler)
3. tests/test_mcp_tools.py - Added TestGetChunk class with 8 tests (327 lines)
4. docs/stories/4-2-get-chunk-enhanced.md - Updated task completion status and completion notes

