# MCP Integration Architecture

This document describes the kx-hub MCP server architecture and how it integrates with Claude Desktop.

## Overview

The kx-hub MCP server exposes the Firestore knowledge base to Claude Desktop via the Model Context Protocol (MCP), enabling conversational access to 813 semantically-searchable chunks without context switching.

## Architecture Diagram

```
┌──────────────────────┐
│   Claude Desktop     │
│   (MCP Client)       │
└──────────┬───────────┘
           │ stdio
           │ JSON-RPC
           ▼
┌──────────────────────┐
│  kx-hub MCP Server   │
│  (Python/stdio)      │
│                      │
│  ┌────────────────┐  │
│  │  Resources     │  │  - List/Read chunks
│  └────────────────┘  │
│                      │
│  ┌────────────────┐  │
│  │  Tools         │  │  - search_semantic
│  │                │  │  - search_by_metadata
│  │                │  │  - get_related_chunks
│  │                │  │  - get_stats
│  └────────────────┘  │
│                      │
│  ┌────────────────┐  │
│  │  Prompts       │  │  - find_insights_about
│  │                │  │  - author_deep_dive
│  │                │  │  - tag_exploration
│  │                │  │  - related_to_chunk
│  └────────────────┘  │
└──────────┬───────────┘
           │ HTTPS
           │ Google Cloud APIs
           ▼
┌──────────────────────┐
│   GCP Services       │
│                      │
│  ┌────────────────┐  │
│  │  Firestore     │  │  kb_items collection
│  │  Vector Search │  │  768-dim embeddings
│  └────────────────┘  │
│                      │
│  ┌────────────────┐  │
│  │  Vertex AI     │  │  gemini-embedding-001
│  │  Embeddings    │  │  Query embeddings
│  └────────────────┘  │
└──────────────────────┘
```

## Components

### 1. MCP Server (`main.py`)

**Responsibility:** Protocol handler and request router

**Transport:** stdio (standard input/output)
- Claude Desktop spawns the Python process
- Communication via JSON-RPC over stdio
- Logging to stderr (stdout reserved for protocol)

**Initialization:**
1. Validate environment variables (GCP_PROJECT, credentials, etc.)
2. Create MCP Server instance
3. Register handlers (resources, tools, prompts)
4. Start stdio transport loop

**Error Handling:**
- Graceful degradation (returns error messages to Claude)
- Logs to stderr for debugging
- Continues serving requests after non-fatal errors

### 2. Firestore Client (`firestore_client.py`)

**Responsibility:** Firestore query wrapper and connection pooling

**Key Functions:**

- `list_all_chunks()` - List chunks with metadata
- `get_chunk_by_id()` - Fetch single chunk by ID
- `query_by_metadata()` - Filter by tags/author/source
- `find_nearest()` - Vector similarity search (FIND_NEAREST)
- `get_stats()` - Aggregate statistics

**Performance Optimizations:**
- Client connection caching (lazy initialization)
- Query result limits (default 10-20)
- Efficient Firestore queries (indexed fields)

**Schema:**
```python
{
  'id': 'chunk_id',              # Document ID
  'parent_doc_id': 'doc_id',     # Original document
  'chunk_index': 0,              # Position in sequence
  'total_chunks': 3,             # Total chunks from doc
  'title': 'Book Title',
  'author': 'Author Name',
  'source': 'kindle',
  'category': 'books',
  'tags': ['psychology'],
  'content': 'Full chunk text',  # Stored with embedding
  'embedding': Vector([...]),    # 768-dim Firestore Vector
  'created_at': Timestamp,
  'updated_at': Timestamp
}
```

### 3. Embeddings Module (`embeddings.py`)

**Responsibility:** Query embedding generation using Vertex AI

**Model:** `gemini-embedding-001`
- **Dimensions:** 768 (via `output_dimensionality=768`)
- **Same as document embeddings** (ensures semantic consistency)

**Retry Logic:**
- Max 3 attempts
- Exponential backoff (1s, 2s, 4s, ...)
- Handles rate limits (ResourceExhausted)
- Handles server errors (InternalServerError)

**Client Caching:**
- Vertex AI client initialized once
- Reused across all queries
- Reduces latency (avoids re-authentication)

**Cost:** ~$0.00001 per query (negligible for typical usage)

### 4. Resource Handlers (`resources.py`)

**Responsibility:** Expose chunks as MCP resources with URIs

**URI Patterns:**

```
kxhub://chunk/{chunk_id}              → Single chunk with full content
kxhub://chunks/by-source/kindle       → All kindle chunks
kxhub://chunks/by-author/James%20Clear → All chunks by author
kxhub://chunks/by-tag/psychology      → All chunks tagged psychology
```

**Resource Listing:**
- Returns metadata for all chunks
- Includes URI, name, description, mimeType
- Limit: 1000 chunks (full KB)

**Resource Reading:**
- Parses URI to extract filters
- Fetches chunk(s) from Firestore
- Returns markdown-formatted content

### 5. Tool Handlers (`tools.py`)

**Responsibility:** Execute search and query operations

**Tool: search_semantic**

Flow:
1. Generate embedding for query text (Vertex AI)
2. Execute Firestore FIND_NEAREST with cosine similarity
3. Apply optional metadata filters (post-processing)
4. Format results (metadata + content snippet + full content)

**Tool: search_by_metadata**

Flow:
1. Build Firestore WHERE query
2. Support tags (array-contains-any), author (==), source (==)
3. Sort by created_at descending
4. Return filtered chunks

**Tool: get_related_chunks**

Flow:
1. Fetch source chunk by ID
2. Extract its embedding vector
3. Execute FIND_NEAREST with that vector
4. Exclude source chunk from results
5. Return top N similar chunks

**Tool: get_stats**

Flow:
1. Stream all chunks from Firestore
2. Aggregate unique values (sources, authors, tags, parent_docs)
3. Calculate totals and averages
4. Return summary statistics

### 6. Prompt Templates (`prompts.py`)

**Responsibility:** Pre-defined prompts for common queries

**Template Structure:**
```python
Prompt(
  name="find_insights_about",
  description="Search my reading highlights...",
  arguments=[
    PromptArgument(name="topic", required=True)
  ]
)
```

**Template Messages:**
- User role message with instructions
- Tells Claude which tools to use
- Provides structure for response
- Includes context and goals

## Protocol Flow

### Example: Semantic Search Query

1. **User asks Claude:** "What insights do I have about decision making?"

2. **Claude analyzes request** and determines it needs semantic search

3. **Claude calls MCP tool:**
   ```json
   {
     "method": "tools/call",
     "params": {
       "name": "search_semantic",
       "arguments": {
         "query": "decision making insights",
         "limit": 10
       }
     }
   }
   ```

4. **MCP Server receives request** via stdio

5. **Server generates query embedding:**
   - Calls Vertex AI gemini-embedding-001
   - Returns 768-dimensional vector

6. **Server executes vector search:**
   - Firestore FIND_NEAREST query
   - Cosine similarity on embedding field
   - Returns top 10 chunks

7. **Server formats results:**
   ```json
   {
     "query": "decision making insights",
     "result_count": 10,
     "results": [
       {
         "rank": 1,
         "chunk_id": "...",
         "title": "Thinking, Fast and Slow",
         "author": "Daniel Kahneman",
         "snippet": "...",
         "full_content": "..."
       },
       ...
     ]
   }
   ```

8. **Claude receives results** and synthesizes response for user

9. **User sees:** Curated insights about decision making with sources

## Security Model

### Authentication

- **Service Account:** GCP service account with minimal permissions
- **Key File:** JSON key file specified in `GOOGLE_APPLICATION_CREDENTIALS`
- **No Network Exposure:** stdio transport is local-only (no ports, no HTTP)

### IAM Permissions

Required roles:
- `roles/datastore.user` - Firestore read access to kb_items
- `roles/aiplatform.user` - Vertex AI embeddings API access

### Data Privacy

- **Local Execution:** Server runs on user's machine
- **No Data Storage:** MCP server doesn't store any data
- **No Logging of Queries:** Query text not persisted (only stderr logs)
- **Read-Only:** No write access to Firestore

## Performance Characteristics

### Latency Breakdown

**First Query (Cold Start):**
- Client initialization: ~1.5s
- Embedding generation: ~500ms
- Vector search: ~300ms
- **Total:** ~2-3s

**Subsequent Queries:**
- Embedding generation: ~200-300ms (client cached)
- Vector search: ~200-300ms
- **Total:** <600ms (typical)

### Throughput

- **Concurrent Queries:** Not supported (single-threaded stdio)
- **Sequential Queries:** ~2-3 queries/second (after warmup)

### Resource Usage

- **Memory:** ~100-200 MB (Python + GCP clients)
- **CPU:** Minimal (network I/O bound)
- **Network:** ~50-100 KB per query (embeddings + Firestore)

## Cost Analysis

### Per-Query Costs

1. **Vertex AI Embeddings:** $0.00001 per query
2. **Firestore Reads:** $0.00000036 per document read (10 reads = $0.0000036)
3. **Network Egress:** Negligible (within same region)

**Total per query:** ~$0.000011

### Monthly Cost Estimate

**Typical Usage:** 50-100 queries/month
- **Embeddings:** $0.001
- **Firestore:** $0.0002
- **Total:** ~$0.0012/month

**Heavy Usage:** 500 queries/month
- **Embeddings:** $0.005
- **Firestore:** $0.002
- **Total:** ~$0.007/month

**Cost Impact on kx-hub:** +$0.10-0.20/month (from $1.40 → $1.50-1.60 total)

## Comparison to REST API Approach

| Aspect | MCP Server (Implemented) | REST API (Original Plan) |
|--------|--------------------------|--------------------------|
| **Development Time** | 2-3 days | 7-10 days |
| **User Experience** | Conversational, no context switch | Form-based search, context switch |
| **Infrastructure** | Local server, zero cost | Cloud Run + Load Balancer (~$5-10/month) |
| **Authentication** | Service account (local) | OAuth2 + API keys |
| **Client Support** | Claude Desktop, any MCP client | Custom web/CLI clients needed |
| **Maintenance** | Minimal (Anthropic-maintained protocol) | API versioning, client updates |
| **Extensibility** | Add tools/prompts easily | Requires API changes + deployments |

## Future Enhancements

### Planned (Out of Scope for 1.7)

1. **Remote MCP Server** (SSE transport)
   - Deploy to Cloud Run
   - Enable multi-user access
   - Requires authentication layer

2. **Advanced Filters**
   - Date range filtering
   - Token count filtering
   - Similarity threshold tuning

3. **Caching Layer**
   - Cache frequent queries
   - Reduce Vertex AI costs
   - Improve latency

4. **Query Analytics**
   - Track query patterns
   - Identify popular topics
   - Optimize index strategy

5. **Batch Operations**
   - Compare multiple chunks
   - Generate summaries across chunks
   - Export filtered results

## References

- [MCP Protocol Documentation](https://modelcontextprotocol.io/)
- [Firestore Vector Search](https://cloud.google.com/firestore/docs/vector-search)
- [Vertex AI Embeddings](https://cloud.google.com/vertex-ai/docs/generative-ai/embeddings/get-text-embeddings)
- [Story 1.6 - Document Chunking](../stories/1.6.story.md)
