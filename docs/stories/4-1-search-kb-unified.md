# Story 4.1: Create Unified `search_kb` Tool

Status: review

## Story

As an **AI assistant using kx-hub MCP tools**,
I want a **single unified search_kb tool that combines all search functionality**,
so that **I can find relevant knowledge with fewer tool calls and reduced cognitive overhead when selecting the right search approach**.

## Acceptance Criteria

1. **New `search_kb` tool registered in MCP server** with unified parameter schema
2. **Semantic search works** when only `query` parameter is provided (replaces `search_semantic`)
3. **Metadata filtering works** when `filters.tags`, `filters.author`, or `filters.source` are provided (replaces `search_by_metadata`)
4. **Date range filtering works** when `filters.date_range` is provided with `start` and `end` dates (replaces `search_by_date_range`)
5. **Relative time filtering works** when `filters.period` is provided (replaces `search_by_relative_time`)
6. **Cluster scoping works** when `filters.cluster_id` is provided (replaces `search_within_cluster`)
7. **Knowledge card search works** when `filters.search_cards_only` is true (replaces `search_knowledge_cards`)
8. **Filters combine with AND logic** - multiple filters narrow results
9. **Results include knowledge cards and cluster info** by default
10. **All URLs included** (readwise_url, source_url, highlight_url) per Story 2.7

## Tasks / Subtasks

- [x] Task 1: Implement `search_kb` function in tools.py (AC: 1-10)
  - [x] 1.1 Define unified parameter schema with `query`, `filters`, and `limit`
  - [x] 1.2 Implement filter parsing and validation logic
  - [x] 1.3 Route to appropriate search backend based on filter combination
  - [x] 1.4 Ensure cluster_id filter calls `search_within_cluster` logic
  - [x] 1.5 Ensure period/date_range filters call time-based query logic
  - [x] 1.6 Implement AND logic for combining multiple filters
  - [x] 1.7 Include knowledge_card and cluster info in all results

- [x] Task 2: Register `search_kb` tool in main.py (AC: 1)
  - [x] 2.1 Add Tool definition with complete inputSchema
  - [x] 2.2 Add handler in call_tool_handler switch

- [x] Task 3: Unit tests (AC: 1-10)
  - [x] 3.1 Test semantic search only (query parameter)
  - [x] 3.2 Test metadata filtering (tags, author, source)
  - [x] 3.3 Test date range filtering
  - [x] 3.4 Test relative time filtering (period)
  - [x] 3.5 Test cluster scoping
  - [x] 3.6 Test search_cards_only flag
  - [x] 3.7 Test combined filters (AND logic)
  - [x] 3.8 Test edge cases (empty query, invalid filters)

- [ ] Task 4: Integration testing (AC: 1-10)
  - [ ] 4.1 Test via MCP protocol with Claude Desktop
  - [ ] 4.2 Verify response format matches expected schema
  - [ ] 4.3 Verify URLs, knowledge cards, and cluster info included

## Dev Notes

### Architecture Pattern

The unified `search_kb` tool consolidates 6 separate tools into one:
- `search_semantic` → base semantic search
- `search_by_metadata` → filters.tags/author/source
- `search_by_date_range` → filters.date_range
- `search_by_relative_time` → filters.period
- `search_within_cluster` → filters.cluster_id
- `search_knowledge_cards` → filters.search_cards_only

The implementation reuses existing functions from `tools.py` and `firestore_client.py`.

### Filter Parameter Schema

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Natural language search query"
    },
    "filters": {
      "type": "object",
      "properties": {
        "cluster_id": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "author": {"type": "string"},
        "source": {"type": "string"},
        "date_range": {
          "type": "object",
          "properties": {
            "start": {"type": "string", "format": "date"},
            "end": {"type": "string", "format": "date"}
          }
        },
        "period": {
          "type": "string",
          "enum": ["yesterday", "last_3_days", "last_week", "last_7_days", "last_month", "last_30_days"]
        },
        "search_cards_only": {"type": "boolean"}
      }
    },
    "limit": {
      "type": "integer",
      "default": 10
    }
  },
  "required": ["query"]
}
```

### Implementation Approach

1. Parse incoming filters object
2. Determine primary search mode:
   - If `search_cards_only` → use knowledge card vector index
   - If `cluster_id` → scope to cluster via Firestore filter
   - If `period` or `date_range` → apply time constraints
   - Default → standard semantic search
3. Apply additional filters (tags, author, source) as post-query filters or Firestore constraints
4. Always include knowledge_card and cluster info in results
5. Return unified response format

### Existing Functions to Reuse

From `tools.py`:
- `_format_urls()` - Extract URL fields
- `_format_knowledge_card()` - Format knowledge card
- `_format_cluster_info()` - Get cluster metadata

From `firestore_client.py`:
- `find_nearest()` - Vector search with optional filters
- `query_by_date_range()` - Time-based queries
- `query_by_relative_time()` - Relative time queries
- `search_within_cluster()` - Cluster-scoped search

From `embeddings.py`:
- `generate_query_embedding()` - Generate query vector

### Project Structure Notes

- New function added to: `src/mcp_server/tools.py`
- Tool registration in: `src/mcp_server/main.py`
- Tests added to: `tests/test_tools.py` or new `tests/test_search_kb.py`
- No new files required - extends existing module

### Testing Strategy

Unit tests will mock Firestore and embedding calls. Integration tests will use real MCP protocol.

Key test scenarios:
1. Query only → semantic search
2. Query + cluster_id → scoped search
3. Query + period → time-filtered search
4. Query + multiple filters → AND combination
5. Invalid filter combinations → graceful error

### References

- [Source: docs/epics.md#Epic-4-MCP-Tool-Consolidation] - Tool specification
- [Source: docs/architecture.md#Query-Tools] - Current 22 tools listed
- [Source: src/mcp_server/tools.py] - Existing tool implementations
- [Source: src/mcp_server/main.py] - Tool registration pattern

## Dev Agent Record

### Context Reference

- docs/stories/4-1-search-kb-unified.context.xml

### Agent Model Used

claude-sonnet-4-5-20250929

### Debug Log References

Implementation Plan:
1. Created unified `search_kb` function in tools.py that routes to appropriate backends based on filter combinations
2. Registered tool in main.py with complete JSON Schema
3. Implemented 11 unit tests covering all ACs and edge cases
4. All tests pass (17/17 in test_mcp_tools.py)

### Completion Notes List

- Implemented unified search_kb function consolidating 6 search tools into one interface
- Function routes to appropriate backend: cluster search, date range, relative time, knowledge cards, or semantic search
- Validates conflicting filters (date_range + period)
- Includes knowledge cards, cluster info, and URLs in all results (ACs 9-10)
- Added comprehensive test coverage: 11 new unit tests testing all filter combinations and edge cases
- All existing tests continue to pass - no regressions introduced

### File List

- src/mcp_server/tools.py (modified - added search_kb function)
- src/mcp_server/main.py (modified - registered search_kb tool and handler)
- tests/test_mcp_tools.py (modified - added TestSearchKBUnified test class with 11 tests)

