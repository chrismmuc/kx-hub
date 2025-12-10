# MCP Server Usage Guide

This guide shows you how to query your kx-hub knowledge base through Claude Desktop using natural language.

## Available Tools

The kx-hub MCP server provides the following tools, organized by category:

### Core Search Tools

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

---

### Knowledge Card Tools

Knowledge cards provide AI-generated summaries and key takeaways for each chunk, making it easier to scan your knowledge base at a glance.

#### 5. `get_knowledge_card` - Get AI Summary for a Chunk

Retrieve the AI-generated summary and key takeaways for a specific chunk.

**When to use:** Getting a quick summary of a chunk without reading the full content.

**Example Queries:**
```
"Show me the summary for chunk abc-123"
"What are the key takeaways from this chunk?"
```

**Returns:**
- Concise summary (≤200 characters)
- List of key takeaways (3-5 bullet points)
- Chunk metadata (title, author, source)

#### 6. `search_knowledge_cards` - Search AI Summaries

Semantic search across AI-generated summaries only (not full content). Faster than full search, ideal for high-level exploration.

**When to use:** Quickly scanning your knowledge base for relevant topics without diving into full content.

**Example Queries:**
```
"Find summaries about productivity systems"
"What insights do I have about leadership?"
```

**Returns:**
- Knowledge card summaries and takeaways
- No full content (lighter, faster results)

---

### Cluster Discovery Tools

Clusters organize your knowledge base into semantic topic groups, making it easier to browse by theme.

#### 7. `list_clusters` - Browse All Topic Clusters

List all semantic clusters in your knowledge base, sorted by size.

**When to use:** Exploring what topics are in your knowledge base.

**Example Queries:**
```
"What topics are in my knowledge base?"
"Show me all clusters"
```

**Returns:**
- Cluster name and description
- Number of chunks in each cluster
- Cluster IDs for deeper exploration

#### 8. `get_cluster` - Explore a Specific Cluster

Get details about a specific cluster, including member chunks.

**When to use:** Deep-diving into a specific topic area.

**Example Queries:**
```
"Show me the Productivity & Habits cluster"
"What's in cluster-5?"
```

**Parameters:**
- `cluster_id`: Cluster identifier
- `include_chunks`: Whether to include member chunks (default: true)
- `limit`: Maximum chunks to return (default: 20)

**Returns:**
- Cluster metadata (name, description, size)
- Member chunks with knowledge cards
- Cluster overview

#### 9. `search_within_cluster` - Search Within a Topic

Semantic search restricted to a specific cluster.

**When to use:** Finding specific content within a known topic area.

**Example Queries:**
```
"Search for focus techniques in the Productivity cluster"
"Find decision-making insights in the Psychology cluster"
```

**Returns:**
- Search results filtered to cluster members
- Knowledge cards for each result
- Cluster context

#### 10. `get_related_clusters` - Find Related Topic Clusters

Discover clusters conceptually related to a given cluster using vector similarity on cluster centroids. This enables exploration of how different knowledge areas connect.

**When to use:** Exploring connections between topics, finding emergent patterns, discovering "meta-concepts" that span multiple clusters.

**Example Queries:**
```
"What clusters are related to the Semantic Search cluster?"
"Find topics that connect to my AI notes"
"How does this cluster relate to other areas in my knowledge base?"
```

**Parameters:**
- `cluster_id`: Source cluster to find relations for (required)
- `limit`: Maximum related clusters to return (default: 5, max: 20)
- `distance_measure`: Similarity measure - COSINE (default), EUCLIDEAN, or DOT_PRODUCT

**Returns:**
- Source cluster metadata
- List of related clusters with similarity scores (0-1, higher = more similar)
- Distance values for each related cluster

**Example Response:**
```json
{
  "source_cluster": {
    "cluster_id": "cluster_12",
    "name": "Semantic Search",
    "description": "Notes about semantic search techniques",
    "chunk_count": 15
  },
  "related_clusters": [
    {
      "cluster_id": "cluster_18",
      "name": "Personal Knowledge Management",
      "similarity_score": 0.87,
      "chunk_count": 31
    },
    {
      "cluster_id": "cluster_25",
      "name": "MCP and AI Context",
      "similarity_score": 0.82,
      "chunk_count": 12
    }
  ],
  "result_count": 2
}
```

**Use case: Concept Chain Exploration**
```
1. "What clusters are related to Semantic Search?"
2. "Now show me what's related to Personal Knowledge Management"
3. "I see a pattern emerging about AI-powered personal knowledge systems!"
```

---

### Reading Recommendation Tools

These tools help you discover new articles to read based on your knowledge base content.

#### 11. `get_reading_recommendations` - AI-Powered Reading Recommendations

Get personalized reading recommendations based on your recent reads and top interest clusters. Uses Tavily Search to find high-quality articles from trusted sources.

**When to use:** Finding new articles to read, discovering content that extends your existing knowledge.

**Example Queries:**
```
"What should I read next?"
"Give me reading recommendations based on my recent highlights"
"Find new articles about my top interest areas"
```

**Parameters:**
- `scope`: What to base recommendations on
  - `"recent"` - Recent reads only (last N days)
  - `"clusters"` - Top clusters by size
  - `"both"` (default) - Both recent reads and clusters
- `days`: Lookback period for recent reads (default: 14)
- `limit`: Maximum recommendations to return (default: 10)

**Returns:**
```json
{
  "generated_at": "2025-12-10T14:30:00Z",
  "processing_time_seconds": 35,
  "scope": "both",
  "days_analyzed": 14,
  "queries_used": ["platform engineering latest developments 2024 2025", "..."],
  "recommendations": [
    {
      "title": "The Future of Platform Engineering",
      "url": "https://martinfowler.com/articles/...",
      "domain": "martinfowler.com",
      "snippet": "...",
      "published_date": "2025-12-01",
      "depth_score": 4,
      "why_recommended": "Connects to your reading cluster: Platform Engineering"
    }
  ],
  "filtered_out": {
    "duplicate_count": 3,
    "low_quality_count": 2,
    "diversity_cap_count": 1
  }
}
```

**Quality Filtering:**
- Articles are scored for depth (1-5 scale, only 3+ are included)
- Duplicates against your KB are filtered out
- Maximum 2 recommendations per domain for diversity
- Only searches trusted sources from domain whitelist

**Example Conversation:**
```
You: "What should I read next based on my recent highlights?"

Claude uses: get_reading_recommendations(scope="recent", days=7, limit=5)

Claude: "Based on your recent reading about Platform Engineering and Developer Experience,
I recommend:

1. 'Platform Engineering in 2025' (martinfowler.com)
   - Depth: ★★★★☆
   - Why: Connects to your Platform Engineering cluster

2. 'The Rise of Internal Developer Platforms' (infoq.com)
   - Depth: ★★★★★
   - Why: Extends your learning about developer experience

..."
```

#### 12. `update_recommendation_domains` - Manage Domain Whitelist

Add or remove domains from the trusted sources whitelist for recommendations.

**When to use:** Customizing which sources to include in recommendations.

**Example Queries:**
```
"Add techcrunch.com to my recommendation sources"
"Remove medium.com from my reading sources"
"What domains are in my recommendation whitelist?"
```

**Parameters:**
- `add_domains`: List of domains to add (e.g., ["newsite.com"])
- `remove_domains`: List of domains to remove

**Returns:**
```json
{
  "success": true,
  "quality_domains": ["martinfowler.com", "infoq.com", "newsite.com", "..."],
  "domain_count": 15,
  "changes": {
    "domains_added": ["newsite.com"],
    "domains_removed": []
  }
}
```

**Default Whitelist:**
The system starts with these trusted sources:
- martinfowler.com, infoq.com, thoughtworks.com
- thenewstack.io, oreilly.com, acm.org
- anthropic.com, openai.com, huggingface.co
- hbr.org, mckinsey.com
- heise.de, golem.de, arxiv.org

#### 13. `get_recommendation_config` - View Recommendation Settings

View the current recommendation configuration including domain whitelist.

**When to use:** Checking your current recommendation settings.

**Example Query:**
```
"Show me my recommendation settings"
"What sources are in my whitelist?"
```

**Returns:**
```json
{
  "quality_domains": ["martinfowler.com", "infoq.com", "..."],
  "excluded_domains": ["medium.com"],
  "domain_count": 14,
  "last_updated": "2025-12-10T12:00:00Z"
}
```

---

## Resources

The MCP server exposes cluster data as browsable resources via URIs. Claude Desktop can display these as formatted markdown.

### Cluster Resources

#### `kxhub://clusters` - All Clusters Overview

Browse all semantic clusters with descriptions and sizes.

**Example:**
```
"Show me the clusters resource"
"Browse kxhub://clusters"
```

#### `kxhub://cluster/{cluster_id}` - Cluster Details

View a specific cluster with member chunks and snippets.

**Example:**
```
"Show me kxhub://cluster/productivity"
```

#### `kxhub://cluster/{cluster_id}/cards` - Cluster with Knowledge Cards

View a cluster with AI-generated summaries for all members (no full content).

**Example:**
```
"Browse kxhub://cluster/psychology/cards"
```

**Use case:** Quick overview of a topic using AI summaries instead of full text.

---

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

### Using Knowledge Cards

**You:**
> What are the main ideas in my knowledge base about productivity?

**Claude uses:** `search_knowledge_cards(query="productivity", limit=10)`

**Result:** Claude shows AI-generated summaries and key takeaways from 10 relevant chunks, without the full text - perfect for quick scanning.

---

### Browsing by Cluster

**You:**
> What topics are in my knowledge base?

**Claude uses:** `list_clusters()`

**Result:** Claude shows all semantic clusters (e.g., "Productivity & Habits", "AI & Machine Learning", "Psychology & Behavior") with descriptions and sizes.

**You:**
> Tell me more about the Productivity cluster

**Claude uses:** `get_cluster(cluster_id="productivity", include_chunks=True, limit=20)`

**Result:** Claude shows cluster description and member chunks with knowledge cards.

---

## URL Fields in Search Results

All MCP search tools now return URL fields for traceability back to Readwise:

- **`readwise_url`**: Link to book review in Readwise (always present)
- **`source_url`**: Link to original source article/book (may be null for some books)
- **`highlight_url`**: Link to specific highlight in Readwise (optional, for detailed view)

**Example Response:**
```json
{
  "chunk_id": "41094950-chunk-003",
  "title": "Geschwister Als Team",
  "author": "Nicola Schmidt",
  "readwise_url": "https://readwise.io/bookreview/41094950",
  "source_url": null,
  "highlight_url": "https://readwise.io/open/727604197",
  "content": "..."
}
```

**Usage in Claude Desktop:**

You can use these URLs to:
- Open highlights directly in Readwise web interface
- Navigate to original source articles
- Share specific highlights with others
- Verify highlight context in Readwise

**Example Queries:**
```
"Find content about decision making and give me the Readwise links"
"Show me highlights from this author with URLs"
```

Claude will include clickable URLs in the response, making it easy to explore content further in Readwise.

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

### 6. Start with Clusters for Topic Discovery

When exploring your knowledge base:
1. List clusters to see available topics
2. Explore specific clusters for deep dives
3. Use cluster-based search for focused queries

**Example workflow:**
```
1. "What topics are in my knowledge base?"
2. "Show me the Psychology cluster"
3. "Search for cognitive biases in the Psychology cluster"
```

### 8. Discover Cluster Relationships

Find how different knowledge areas connect:
```
1. "What clusters are related to Productivity?"
2. "Show me the connection path between AI clusters and Writing clusters"
3. Claude chains get_related_clusters to find intermediate connections
```

**Example - Emergent Pattern Discovery:**
```
You: "What topics relate to my MCP notes?"
Claude: "Your MCP notes (Cluster #25) connect to:
  - Semantic Search (87% similar) - both focus on information retrieval
  - PKM Systems (82% similar) - both about organizing knowledge
  - AI Workflows (78% similar) - both enable AI-assisted tasks

These four clusters together suggest you're developing thinking 
around 'AI-augmented personal knowledge systems'."
```

### 7. Use Knowledge Cards for Quick Scanning

Knowledge cards provide AI summaries without full content:
- Faster results (lighter payload)
- Perfect for high-level exploration
- Easy to scan multiple ideas quickly

**When to use full search vs knowledge cards:**
- Full search: When you need exact quotes and context
- Knowledge cards: When you want to scan topics quickly

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
