# kx-hub MCP Tools API Reference

**Last Updated:** December 2025
**Version:** v2.0 (Epic 4 Consolidation)

This document provides technical reference for all MCP tools available in the kx-hub knowledge base server.

## Overview

The kx-hub MCP server provides **9 optimized tools** (reduced from 25) for querying and managing your personal knowledge base:

| Tool | Purpose | Replaces |
|------|---------|----------|
| `search_kb` | Unified semantic + filtered search | 5 tools |
| `get_chunk` | Retrieve chunk with related content | 2 tools |
| `get_recent` | Recent reading + activity summary | 2 tools |
| `get_cluster` | Cluster details with related clusters | 2 tools |
| `configure_kb` | Unified configuration management | 6 tools |
| `get_stats` | Knowledge base statistics | - |
| `list_clusters` | List all semantic clusters | - |
| `get_reading_recommendations` | AI-powered reading suggestions | - |
| `search_within_cluster` | Semantic search scoped to cluster | - |

---

## Core Tools (Consolidated)

### 1. `search_kb` - Unified Knowledge Base Search

**Purpose:** Single entry point for all search operations with flexible filtering.

**Replaces:** `search_semantic`, `search_by_metadata`, `search_by_date_range`, `search_by_relative_time`, `search_knowledge_cards`

**Parameters:**
```typescript
{
  query: string;                    // Natural language search query (required)
  filters?: {
    cluster_id?: string;            // Scope to specific cluster
    tags?: string[];                // Filter by tags (array-contains-any)
    author?: string;                // Filter by exact author name
    source?: string;                // Filter by source (e.g., 'kindle', 'reader')
    date_range?: {
      start: string;                // Start date (YYYY-MM-DD)
      end: string;                  // End date (YYYY-MM-DD)
    };
    period?: string;                // Relative time period
    search_cards_only?: boolean;   // Search knowledge card summaries only
  };
  limit?: number;                   // Maximum results (default: 10)
}
```

**Period Values:**
- `"yesterday"`
- `"last_3_days"`
- `"last_week"` / `"last_7_days"`
- `"last_month"` / `"last_30_days"`

**Returns:**
```typescript
{
  query: string;
  result_count: number;
  results: [
    {
      chunk_id: string;
      title: string;
      author: string;
      source: string;
      tags: string[];
      content: string;
      relevance_score: number;
      knowledge_card?: {
        summary: string;
        takeaways: string[];
      };
      cluster?: {
        cluster_id: string;
        cluster_name: string;
        description: string;
      };
      readwise_url?: string;
      source_url?: string;
      highlight_url?: string;
    }
  ]
}
```

**Examples:**
```typescript
// Semantic search only
search_kb({ query: "decision making frameworks" })

// Search with metadata filter
search_kb({
  query: "microservices",
  filters: { author: "Martin Fowler" }
})

// Search with time period
search_kb({
  query: "AI agents",
  filters: { period: "last_week" }
})

// Search within cluster
search_kb({
  query: "architecture patterns",
  filters: { cluster_id: "cluster-28" }
})

// Search knowledge cards only
search_kb({
  query: "leadership",
  filters: { search_cards_only: true }
})
```

---

### 2. `get_chunk` - Retrieve Chunk with Context

**Purpose:** Get complete chunk details including knowledge card and related chunks.

**Replaces:** `get_related_chunks`, `get_knowledge_card`

**Parameters:**
```typescript
{
  chunk_id: string;                // Chunk ID to retrieve (required)
  include_related?: boolean;       // Include related chunks (default: true)
  related_limit?: number;          // Max related chunks (default: 5, max: 20)
}
```

**Returns:**
```typescript
{
  chunk_id: string;
  title: string;
  author: string;
  source: string;
  tags: string[];
  content: string;
  chunk_info: string;              // e.g., "chunk 2/5"
  knowledge_card?: {
    summary: string;
    takeaways: string[];
  };
  cluster?: {
    cluster_id: string;
    cluster_name: string;
    description: string;
  };
  readwise_url?: string;
  source_url?: string;
  highlight_url?: string;
  related_chunks: [                 // Only if include_related=true
    {
      chunk_id: string;
      title: string;
      author: string;
      source: string;
      similarity_score: number;
      knowledge_card?: {...};
      readwise_url?: string;
      source_url?: string;
      highlight_url?: string;
    }
  ]
}
```

**Examples:**
```typescript
// Get chunk with related content
get_chunk({ chunk_id: "chunk-abc123" })

// Get chunk without related chunks
get_chunk({
  chunk_id: "chunk-abc123",
  include_related: false
})

// Get chunk with more related items
get_chunk({
  chunk_id: "chunk-abc123",
  related_limit: 10
})
```

---

### 3. `get_recent` - Recent Reading + Activity

**Purpose:** Get recent chunks with activity summary and cluster distribution.

**Replaces:** `get_recently_added`, `get_reading_activity`

**Parameters:**
```typescript
{
  period?: string;                 // Time period (default: "last_7_days")
  limit?: number;                  // Max chunks to return (default: 10, max: 50)
}
```

**Period Values:** Same as `search_kb` plus `"today"`

**Returns:**
```typescript
{
  period: string;
  recent_chunks: [
    {
      chunk_id: string;
      title: string;
      author: string;
      source: string;
      tags: string[];
      snippet: string;
      chunk_info: string;
      added_date: string;
      knowledge_card?: {
        summary: string;
        takeaways: string[];
      };
      cluster?: {
        cluster_id: string;
        cluster_name: string;
        description: string;
      };
      readwise_url?: string;
      source_url?: string;
      highlight_url?: string;
    }
  ];
  activity_summary: {
    total_chunks_added: number;
    days_with_activity: number;
    chunks_by_day: { [date: string]: number };
    top_sources: [{ source: string; count: number }];
    top_authors: [{ author: string; count: number }];
  };
  cluster_distribution: {
    [cluster_id: string]: {
      name: string;
      count: number;
    }
  }
}
```

**Examples:**
```typescript
// Get recent reading with defaults
get_recent()

// Get today's reading
get_recent({ period: "today" })

// Get last month's activity
get_recent({ period: "last_month", limit: 20 })
```

---

### 4. `get_cluster` - Cluster Details + Related

**Purpose:** Get cluster metadata, member chunks, and related clusters.

**Replaces:** `get_related_clusters` (enhanced original `get_cluster`)

**Parameters:**
```typescript
{
  cluster_id: string;              // Cluster ID to fetch (required)
  include_members?: boolean;       // Include member chunks (default: true)
  include_related?: boolean;       // Include related clusters (default: true)
  member_limit?: number;           // Max members (default: 20, max: 50)
  related_limit?: number;          // Max related clusters (default: 5, max: 20)
}
```

**Returns:**
```typescript
{
  cluster_id: string;
  name: string;
  description: string;
  size: number;
  created_at: string;
  member_count?: number;           // Only if include_members=true
  members?: [                      // Only if include_members=true
    {
      chunk_id: string;
      title: string;
      author: string;
      source: string;
      knowledge_card?: {...};
      readwise_url?: string;
      source_url?: string;
      highlight_url?: string;
    }
  ];
  related_count?: number;          // Only if include_related=true
  related_clusters?: [             // Only if include_related=true
    {
      cluster_id: string;
      name: string;
      description: string;
      similarity_score: number;    // 0-1, based on centroid similarity
      size: number;
    }
  ]
}
```

**Examples:**
```typescript
// Get cluster with members and related
get_cluster({ cluster_id: "cluster-28" })

// Get cluster metadata only
get_cluster({
  cluster_id: "cluster-28",
  include_members: false,
  include_related: false
})

// Get cluster with custom limits
get_cluster({
  cluster_id: "cluster-28",
  member_limit: 50,
  related_limit: 10
})
```

---

### 5. `configure_kb` - Unified Configuration

**Purpose:** Single tool for all configuration management.

**Replaces:** `update_recommendation_domains`, `get_recommendation_config`, `get_ranking_config`, `get_hot_sites_config`, `update_hot_sites_config`, `update_ranking_config`

**Parameters:**
```typescript
{
  action: string;                  // Action to perform (required)
  params?: object;                 // Action-specific parameters
}
```

**Actions:**

| Action | Description | Parameters |
|--------|-------------|------------|
| `show_all` | Display all configuration | None |
| `show_ranking` | Show ranking weights/settings | None |
| `show_domains` | Show domain whitelist | None |
| `show_hot_sites` | Show hot sites categories | None |
| `update_ranking` | Update ranking config | `{weights?, settings?}` |
| `update_domains` | Modify domain whitelist | `{add?, remove?}` |
| `update_hot_sites` | Modify hot sites | `{category, add?, remove?, description?}` |

**Returns:** Action-specific response structure

**Examples:**
```typescript
// View all configuration
configure_kb({ action: "show_all" })

// Update ranking weights
configure_kb({
  action: "update_ranking",
  params: {
    weights: {
      relevance: 0.6,
      recency: 0.2,
      depth: 0.1,
      authority: 0.1
    }
  }
})

// Add trusted domain
configure_kb({
  action: "update_domains",
  params: {
    add: ["newsite.com"]
  }
})

// Add site to hot sites category
configure_kb({
  action: "update_hot_sites",
  params: {
    category: "ai",
    add: ["anthropic.com"]
  }
})
```

---

## Standalone Tools

### 6. `get_stats` - Knowledge Base Statistics

**Purpose:** Get overall KB statistics and metadata.

**Parameters:** None

**Returns:**
```typescript
{
  total_chunks: number;
  total_clusters: number;
  sources: string[];
  authors: string[];
  tags: string[];
  date_range: {
    earliest: string;
    latest: string;
  }
}
```

**Example:**
```typescript
get_stats()
```

---

### 7. `list_clusters` - List All Clusters

**Purpose:** List all semantic clusters with metadata.

**Parameters:** None

**Returns:**
```typescript
{
  cluster_count: number;
  clusters: [
    {
      cluster_id: string;
      name: string;
      description: string;
      size: number;
      created_at: string;
    }
  ]
}
```

**Example:**
```typescript
list_clusters()
```

---

### 8. `get_reading_recommendations` - AI-Powered Suggestions

**Purpose:** Get personalized reading recommendations based on your KB.

**Parameters:**
```typescript
{
  scope?: string;                  // "recent", "clusters", "both" (default: "both")
  days?: number;                   // Lookback period (default: 14)
  limit?: number;                  // Max recommendations (default: 10)
  cluster_ids?: string[];          // Optional cluster filter
  hot_sites?: string;              // "tech", "ai", "devops", "business", "all"
  mode?: string;                   // "balanced", "fresh", "deep", "surprise_me"
  include_seen?: boolean;          // Include previously shown (default: false)
  predictable?: boolean;           // Disable randomization (default: false)
}
```

**Returns:**
```typescript
{
  recommendation_count: number;
  recommendations: [
    {
      url: string;
      title: string;
      description: string;
      source: string;
      published_date: string;
      relevance_score: number;
      ranking_factors: {
        relevance: number;
        recency: number;
        depth: number;
        authority: number;
      }
    }
  ]
}
```

**Example:**
```typescript
// Get balanced recommendations
get_reading_recommendations()

// Get fresh AI content
get_reading_recommendations({
  hot_sites: "ai",
  mode: "fresh",
  limit: 5
})
```

---

### 9. `search_within_cluster` - Cluster-Scoped Search

**Purpose:** Semantic search restricted to a specific cluster.

**Parameters:**
```typescript
{
  cluster_id: string;              // Cluster to search within (required)
  query: string;                   // Search query (required)
  limit?: number;                  // Max results (default: 10)
}
```

**Returns:** Same format as `search_kb`

**Example:**
```typescript
search_within_cluster({
  cluster_id: "cluster-28",
  query: "software architecture"
})
```

---

## Migration Guide

### From Old Tools to New (Epic 4 Consolidation)

| Old Tool(s) | New Tool | Migration Notes |
|-------------|----------|-----------------|
| `search_semantic` | `search_kb` | Use without filters |
| `search_by_metadata` | `search_kb` | Pass filters in `filters` object |
| `search_by_date_range` | `search_kb` | Use `filters.date_range` |
| `search_by_relative_time` | `search_kb` | Use `filters.period` |
| `search_knowledge_cards` | `search_kb` | Use `filters.search_cards_only: true` |
| `get_related_chunks` | `get_chunk` | Default behavior, `include_related: true` |
| `get_knowledge_card` | `get_chunk` | Embedded in response |
| `get_recently_added` | `get_recent` | See `recent_chunks` array |
| `get_reading_activity` | `get_recent` | See `activity_summary` object |
| `get_related_clusters` | `get_cluster` | Default behavior, `include_related: true` |
| `get_recommendation_config` | `configure_kb` | Use `action: "show_domains"` |
| `update_recommendation_domains` | `configure_kb` | Use `action: "update_domains"` |
| `get_ranking_config` | `configure_kb` | Use `action: "show_ranking"` |
| `update_ranking_config` | `configure_kb` | Use `action: "update_ranking"` |
| `get_hot_sites_config` | `configure_kb` | Use `action: "show_hot_sites"` |
| `update_hot_sites_config` | `configure_kb` | Use `action: "update_hot_sites"` |

---

## Common Patterns

### 1. Search and Explore

```typescript
// Start with broad search
search_kb({ query: "artificial intelligence" })

// Get detailed chunk with context
get_chunk({ chunk_id: "chunk-abc123" })

// Explore cluster
get_cluster({ cluster_id: "cluster-28" })

// Search within cluster for more
search_within_cluster({
  cluster_id: "cluster-28",
  query: "neural networks"
})
```

### 2. Recent Activity Review

```typescript
// Get today's reading
get_recent({ period: "today" })

// Get week overview
get_recent({ period: "last_week", limit: 20 })

// Deep dive on specific chunk
get_chunk({ chunk_id: "chunk-xyz789" })
```

### 3. Discovery and Recommendations

```typescript
// List all clusters
list_clusters()

// Explore interesting cluster
get_cluster({
  cluster_id: "cluster-15",
  include_related: true
})

// Get recommendations based on cluster
get_reading_recommendations({
  cluster_ids: ["cluster-15"],
  mode: "deep"
})
```

---

## Performance Notes

- **Search operations**: <500ms typical response time
- **Cluster operations**: <300ms for metadata, <1s with members
- **Recommendations**: 2-5s (external API calls)
- **Rate limits**: None (local/self-hosted)

---

## Version History

### v2.0 (December 2025) - Epic 4 Consolidation
- Reduced from 25 tools to 9 tools (64% reduction)
- Consolidated 5 search tools → `search_kb`
- Consolidated 2 chunk tools → `get_chunk`
- Consolidated 2 activity tools → `get_recent`
- Enhanced `get_cluster` with related clusters
- Consolidated 6 config tools → `configure_kb`

### v1.0 (November 2025) - Initial Release
- 25 individual tools
- Basic search, metadata filtering, clustering
- Knowledge cards and recommendations

---

## See Also

- [User Guide](mcp-server-guide.md) - Non-technical usage guide
- [Setup Guide](mcp-server-setup.md) - Installation and configuration
- [Architecture](architecture.md) - Technical architecture details
