# MCP Server Usage Guide

This guide shows you how to query your kx-hub knowledge base through Claude Desktop using natural language.

## Available Tools

The kx-hub MCP server provides four main tools:

### 1. `search_semantic` - Semantic Search

Search your knowledge base using natural language queries. Uses vector embeddings for semantic similarity.

**When to use:** Finding passages related to concepts, ideas, or questions.

**Example Queries:**
```
"What insights do I have about decision making?"
"Find highlights about productivity systems"
"Show me content related to habit formation"
```

**How it works:** Claude will use this tool behind the scenes to:
1. Generate an embedding for your query
2. Search Firestore for semantically similar chunks
3. Return relevant passages with context

### 2. `search_by_metadata` - Metadata Filtering

Filter chunks by author, source, or tags without semantic search.

**When to use:** Exploring specific authors, sources, or tagged content.

**Example Queries:**
```
"Show me all highlights from Daniel Kahneman"
"What have I saved from Kindle?"
"List all content tagged with 'psychology'"
```

**Parameters:**
- `tags`: Array of tags (matches any)
- `author`: Exact author name
- `source`: Source type (kindle, reader, etc.)

### 3. `get_related_chunks` - Find Similar Content

Find chunks similar to a specific chunk using vector similarity.

**When to use:** Discovering related content after finding something interesting.

**Example Queries:**
```
"Find content related to chunk [chunk_id]"
"Show me similar passages to this one"
```

### 4. `get_stats` - Knowledge Base Statistics

Get overview statistics about your knowledge base.

**When to use:** Understanding the scope and content of your KB.

**Example Query:**
```
"What's in my knowledge base?"
```

**Returns:**
- Total chunks and documents
- Number of sources
- Author count
- Tag count
- Average chunks per document

## Prompt Templates

The MCP server includes pre-defined prompts for common queries:

### `find_insights_about`

Search for insights about a specific topic with structured analysis.

**Usage:**
```
Use the 'find_insights_about' prompt with topic: "leadership"
```

**What it does:**
- Searches for relevant chunks
- Analyzes and synthesizes key insights
- Presents organized findings with practical applications

### `author_deep_dive`

Analyze all content from a specific author.

**Usage:**
```
Use the 'author_deep_dive' prompt with author: "James Clear"
```

**What it does:**
- Retrieves all chunks by the author
- Identifies main themes and recurring concepts
- Provides comprehensive overview of their ideas

### `tag_exploration`

Explore all content with a specific tag.

**Usage:**
```
Use the 'tag_exploration' prompt with tag: "self-improvement"
```

**What it does:**
- Fetches tagged chunks
- Summarizes themes and patterns
- Highlights standout quotes and actionable takeaways

### `related_to_chunk`

Find and analyze content related to a specific chunk.

**Usage:**
```
Use the 'related_to_chunk' prompt with chunk_id: "41094950-chunk-003"
```

**What it does:**
- Shows source chunk for context
- Finds similar chunks via vector search
- Explains connections and common themes

## Example Conversations

### Basic Search

**You:**
> What do I have about cognitive biases?

**Claude uses:** `search_semantic(query="cognitive biases", limit=10)`

**Result:** Claude shows relevant passages from your highlights about cognitive biases, with sources and context.

---

### Author Exploration

**You:**
> Show me everything I've saved from Nassim Taleb and identify the key themes

**Claude uses:** `search_by_metadata(author="Nassim Taleb", limit=50)`

**Result:** Claude retrieves all Taleb content and analyzes themes like anti-fragility, black swans, and uncertainty.

---

### Deep Dive with Template

**You:**
> Use the find_insights_about prompt for "habit formation"

**Claude uses:** Pre-defined template that:
1. Searches for habit-related chunks
2. Analyzes key concepts
3. Identifies practical applications
4. Highlights surprising findings

**Result:** Structured analysis of your highlights about habit formation.

---

### Finding Related Content

**You:**
> I liked this passage about compound effects. Find similar content.

**Claude uses:** `get_related_chunks(chunk_id="...", limit=5)`

**Result:** Claude shows 5 similar passages that discuss related concepts like incremental improvement, consistency, or long-term thinking.

---

## Tips for Effective Queries

### 1. Be Specific

❌ "Tell me about books"
✅ "What insights do I have about time management from productivity books?"

### 2. Use Natural Language

The semantic search understands concepts, not just keywords:
- "improving focus" will match "concentration techniques", "attention management", etc.
- "decision making" will match "choices", "judgment", "cognitive biases"

### 3. Combine Filters

```
"Search for highlights about learning from author 'James Clear'"
```

Claude will use `search_semantic` with author filter.

### 4. Explore Connections

After finding interesting content:
1. Ask for related chunks
2. Request author deep dive
3. Explore shared tags

### 5. Use Prompt Templates for Structure

When you want organized analysis, invoke the prompt templates explicitly:
```
"Use the author_deep_dive prompt for Daniel Kahneman"
```

## Performance

- **First Query:** 2-3 seconds (cold start - client initialization)
- **Subsequent Queries:** <1 second (typical)
- **Embedding Generation:** ~200-500ms per query
- **Large Result Sets:** May take longer (50+ chunks)

## Limitations

1. **No Fuzzy Author Matching:**
   - Must use exact author name: "James Clear" not "clear"
   - Tip: Use get_stats to see available authors

2. **Tag Filtering is OR Logic:**
   - `tags=["psychology", "business"]` matches chunks with ANY of these tags
   - No AND logic (yet)

3. **No Date Filtering:**
   - Cannot filter by created_at or updated_at
   - Feature planned for future release

4. **Result Limit:**
   - Default limits: 10 (semantic), 20 (metadata)
   - Can request higher limits, but may impact performance

5. **No Full-Text Boolean Search:**
   - Cannot use operators like AND, OR, NOT, quotation marks
   - Use semantic search instead

## Next Steps

- [Setup Guide](./mcp-server-setup.md) - Installation and configuration
- [Architecture Overview](./architecture/mcp-integration.md) - How it works
- [Troubleshooting](./mcp-server-setup.md#troubleshooting) - Common issues
