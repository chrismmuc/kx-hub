#!/usr/bin/env python3
"""
MCP Server for kx-hub Knowledge Base Access.

This server exposes the kx-hub Firestore knowledge base to Claude Desktop
via the Model Context Protocol (MCP) using stdio transport.
"""

import sys
import logging
import os
import asyncio
import json
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Add parent directory to path for imports when run as script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our modules (absolute imports for script execution)
import resources
import tools
import prompts

# Configure logging to stderr (MCP protocol uses stdout for JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

logger = logging.getLogger('kx-hub-mcp')


async def main():
    """Initialize and run the MCP server."""
    logger.info("Starting kx-hub MCP server...")

    # Validate required environment variables
    required_env_vars = [
        'GOOGLE_APPLICATION_CREDENTIALS',
        'GCP_PROJECT',
        'GCP_REGION',
        'FIRESTORE_COLLECTION'
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)

    logger.info(f"GCP Project: {os.getenv('GCP_PROJECT')}")
    logger.info(f"GCP Region: {os.getenv('GCP_REGION')}")
    logger.info(f"Firestore Collection: {os.getenv('FIRESTORE_COLLECTION')}")

    # Create MCP server instance
    server = Server("kx-hub")

    # Register resource handlers
    @server.list_resources()
    async def list_resources_handler():
        """List all available chunk resources."""
        logger.info("Handling list_resources request")
        return resources.list_resources()

    @server.read_resource()
    async def read_resource_handler(uri: str):
        """Read a chunk resource by URI."""
        logger.info(f"Handling read_resource request: {uri}")
        content = resources.read_resource(uri)
        return TextContent(
            uri=uri,
            mimeType="text/markdown",
            text=content
        )

    # Register tool handlers
    @server.list_tools()
    async def list_tools_handler():
        """List available tools."""
        logger.info("Handling list_tools request")
        return [
            Tool(
                name="search_semantic",
                description="Search knowledge base using semantic similarity (natural language queries)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default 10)",
                            "default": 10
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tag filter"
                        },
                        "author": {
                            "type": "string",
                            "description": "Optional author filter"
                        },
                        "source": {
                            "type": "string",
                            "description": "Optional source filter"
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="search_by_metadata",
                description="Search chunks by metadata filters (tags, author, source)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by tags"
                        },
                        "author": {
                            "type": "string",
                            "description": "Filter by author name"
                        },
                        "source": {
                            "type": "string",
                            "description": "Filter by source (e.g., 'kindle', 'reader')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results (default 20)",
                            "default": 20
                        }
                    }
                }
            ),
            Tool(
                name="get_related_chunks",
                description="Find chunks similar to a given chunk using vector similarity",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "chunk_id": {
                            "type": "string",
                            "description": "Source chunk ID"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum related chunks (default 5)",
                            "default": 5
                        }
                    },
                    "required": ["chunk_id"]
                }
            ),
            Tool(
                name="get_stats",
                description="Get knowledge base statistics (total chunks, sources, authors, tags)",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="search_by_date_range",
                description="Query chunks by date range (e.g., what I read between two dates)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format (e.g., '2025-10-29')"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format (e.g., '2025-10-31')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results (default 20)",
                            "default": 20
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tag filter"
                        },
                        "author": {
                            "type": "string",
                            "description": "Optional author filter"
                        },
                        "source": {
                            "type": "string",
                            "description": "Optional source filter"
                        }
                    },
                    "required": ["start_date", "end_date"]
                }
            ),
            Tool(
                name="search_by_relative_time",
                description="Query chunks using relative time periods (yesterday, last week, last month, etc.)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "period": {
                            "type": "string",
                            "description": "Time period: 'yesterday', 'last_3_days', 'last_week', 'last_7_days', 'last_month', or 'last_30_days'"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results (default 20)",
                            "default": 20
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tag filter"
                        },
                        "author": {
                            "type": "string",
                            "description": "Optional author filter"
                        },
                        "source": {
                            "type": "string",
                            "description": "Optional source filter"
                        }
                    },
                    "required": ["period"]
                }
            ),
            Tool(
                name="get_reading_activity",
                description="Get reading activity summary and statistics (chunks added per day, top sources, top authors)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "period": {
                            "type": "string",
                            "description": "Time period: 'today', 'yesterday', 'last_3_days', 'last_7_days', 'last_week', 'last_30_days', or 'last_month'",
                            "default": "last_7_days"
                        }
                    }
                }
            ),
            Tool(
                name="get_recently_added",
                description="Get most recently added chunks (quick access to latest reading)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum chunks to return (default 10)",
                            "default": 10
                        },
                        "days": {
                            "type": "integer",
                            "description": "Look back this many days (default 7)",
                            "default": 7
                        }
                    }
                }
            ),
            Tool(
                name="get_knowledge_card",
                description="Get knowledge card (AI summary and takeaways) for a specific chunk",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "chunk_id": {
                            "type": "string",
                            "description": "Chunk ID to fetch knowledge card for"
                        }
                    },
                    "required": ["chunk_id"]
                }
            ),
            Tool(
                name="search_knowledge_cards",
                description="Semantic search across knowledge card summaries only (not full content)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default 10)",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="list_clusters",
                description="List all semantic clusters with metadata",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="get_cluster",
                description="Get cluster details with member chunks",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "cluster_id": {
                            "type": "string",
                            "description": "Cluster ID to fetch"
                        },
                        "include_chunks": {
                            "type": "boolean",
                            "description": "Whether to include member chunks (default True)",
                            "default": True
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum member chunks to return (default 20)",
                            "default": 20
                        }
                    },
                    "required": ["cluster_id"]
                }
            ),
            Tool(
                name="search_within_cluster",
                description="Semantic search restricted to a specific cluster",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "cluster_id": {
                            "type": "string",
                            "description": "Cluster ID to search within"
                        },
                        "query": {
                            "type": "string",
                            "description": "Natural language search query"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default 10)",
                            "default": 10
                        }
                    },
                    "required": ["cluster_id", "query"]
                }
            ),
            Tool(
                name="get_related_clusters",
                description="Find clusters conceptually related to a given cluster using vector similarity on centroids (Story 3.4)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "cluster_id": {
                            "type": "string",
                            "description": "Source cluster ID to find relations for"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of related clusters (default 5, max 20)",
                            "default": 5
                        },
                        "distance_measure": {
                            "type": "string",
                            "enum": ["COSINE", "EUCLIDEAN", "DOT_PRODUCT"],
                            "description": "Distance measure for similarity (default COSINE)",
                            "default": "COSINE"
                        }
                    },
                    "required": ["cluster_id"]
                }
            ),
            # Story 3.5 + 3.9: Reading Recommendations with Parameterization
            Tool(
                name="get_reading_recommendations",
                description="Get AI-powered reading recommendations based on your KB content. Analyzes recent reads and clusters, searches quality sources, and filters for depth.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "string",
                            "enum": ["recent", "clusters", "both"],
                            "description": "Scope for recommendations: 'recent' (recent reads), 'clusters' (top clusters), or 'both' (default)",
                            "default": "both"
                        },
                        "days": {
                            "type": "integer",
                            "description": "Lookback period for recent reads in days (default 14)",
                            "default": 14
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum recommendations to return (default 10)",
                            "default": 10
                        },
                        "cluster_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of cluster IDs to scope recommendations (e.g., ['cluster-28', 'cluster-20'])"
                        },
                        "hot_sites": {
                            "type": "string",
                            "enum": ["tech", "tech_de", "ai", "devops", "business", "all"],
                            "description": "Optional source category: 'tech', 'tech_de', 'ai', 'devops', 'business', or 'all'"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["balanced", "fresh", "deep", "surprise_me"],
                            "description": "Discovery mode: 'balanced' (default), 'fresh' (recent content), 'deep' (in-depth), 'surprise_me' (high randomization)",
                            "default": "balanced"
                        },
                        "include_seen": {
                            "type": "boolean",
                            "description": "Include previously shown recommendations (default false)",
                            "default": False
                        },
                        "predictable": {
                            "type": "boolean",
                            "description": "Disable query variation for reproducible results (default false)",
                            "default": False
                        }
                    }
                }
            ),
            Tool(
                name="update_recommendation_domains",
                description="Update the domain whitelist for reading recommendations. Add or remove trusted sources.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "add_domains": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Domains to add to the quality whitelist (e.g., ['newsite.com'])"
                        },
                        "remove_domains": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Domains to remove from the whitelist"
                        }
                    }
                }
            ),
            Tool(
                name="get_recommendation_config",
                description="Get current recommendation configuration including domain whitelist",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            # Story 3.8: Ranking Configuration
            Tool(
                name="get_ranking_config",
                description="Get current ranking configuration for recommendations including weights (relevance, recency, depth, authority) and settings (recency decay, diversity, slots)",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            # Story 3.9: Hot Sites Configuration
            Tool(
                name="get_hot_sites_config",
                description="Get hot sites categories and their domains. Shows curated source lists for tech, tech_de, ai, devops, business.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="update_hot_sites_config",
                description="Update hot sites configuration for a specific category. Add or remove domains from curated source lists.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Category name: tech, tech_de, ai, devops, business (or create new)"
                        },
                        "add_domains": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Domains to add to the category"
                        },
                        "remove_domains": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Domains to remove from the category"
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional new description for the category"
                        }
                    },
                    "required": ["category"]
                }
            ),
            Tool(
                name="update_ranking_config",
                description="Update ranking configuration for recommendations. Set factor weights (must sum to 1.0) or adjust recency decay, diversity, and slot settings.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "weights": {
                            "type": "object",
                            "description": "Factor weights (must sum to 1.0): {relevance, recency, depth, authority}",
                            "properties": {
                                "relevance": {"type": "number", "description": "Weight for semantic relevance (default 0.5)"},
                                "recency": {"type": "number", "description": "Weight for publication freshness (default 0.25)"},
                                "depth": {"type": "number", "description": "Weight for content quality (default 0.15)"},
                                "authority": {"type": "number", "description": "Weight for author/source credibility (default 0.1)"}
                            }
                        },
                        "settings": {
                            "type": "object",
                            "description": "Ranking settings for recency, diversity, and slots",
                            "properties": {
                                "recency": {
                                    "type": "object",
                                    "properties": {
                                        "half_life_days": {"type": "integer", "description": "Days until recency score halves (default 90)"},
                                        "max_age_days": {"type": "integer", "description": "Maximum article age in days (default 365)"},
                                        "tavily_days_filter": {"type": "integer", "description": "Days to search in Tavily (default 180)"}
                                    }
                                },
                                "diversity": {
                                    "type": "object",
                                    "properties": {
                                        "shown_ttl_days": {"type": "integer", "description": "Days to track shown URLs (default 7)"},
                                        "novelty_bonus": {"type": "number", "description": "Score bonus for unseen URLs (default 0.1)"},
                                        "domain_duplicate_penalty": {"type": "number", "description": "Penalty per duplicate domain (default 0.05)"},
                                        "stochastic_temperature": {"type": "number", "description": "Randomization level 0-1 (default 0.3)"}
                                    }
                                },
                                "slots": {
                                    "type": "object",
                                    "properties": {
                                        "relevance_count": {"type": "integer", "description": "Top relevance slots (default 2)"},
                                        "serendipity_count": {"type": "integer", "description": "Discovery slots (default 1)"},
                                        "stale_refresh_count": {"type": "integer", "description": "Refresh slots (default 1)"},
                                        "trending_count": {"type": "integer", "description": "Fresh content slots (default 1)"}
                                    }
                                }
                            }
                        }
                    }
                }
            )
        ]

    @server.call_tool()
    async def call_tool_handler(name: str, arguments: Any):
        """Execute a tool by name with arguments."""
        logger.info(f"Handling call_tool request: {name}")

        try:
            if name == "search_semantic":
                result = tools.search_semantic(
                    query=arguments.get("query"),
                    limit=arguments.get("limit", 10),
                    tags=arguments.get("tags"),
                    author=arguments.get("author"),
                    source=arguments.get("source")
                )
            elif name == "search_by_metadata":
                result = tools.search_by_metadata(
                    tags=arguments.get("tags"),
                    author=arguments.get("author"),
                    source=arguments.get("source"),
                    limit=arguments.get("limit", 20)
                )
            elif name == "get_related_chunks":
                result = tools.get_related_chunks(
                    chunk_id=arguments["chunk_id"],
                    limit=arguments.get("limit", 5)
                )
            elif name == "get_stats":
                result = tools.get_stats()
            elif name == "search_by_date_range":
                result = tools.search_by_date_range(
                    start_date=arguments["start_date"],
                    end_date=arguments["end_date"],
                    limit=arguments.get("limit", 20),
                    tags=arguments.get("tags"),
                    author=arguments.get("author"),
                    source=arguments.get("source")
                )
            elif name == "search_by_relative_time":
                result = tools.search_by_relative_time(
                    period=arguments["period"],
                    limit=arguments.get("limit", 20),
                    tags=arguments.get("tags"),
                    author=arguments.get("author"),
                    source=arguments.get("source")
                )
            elif name == "get_reading_activity":
                result = tools.get_reading_activity(
                    period=arguments.get("period", "last_7_days")
                )
            elif name == "get_recently_added":
                result = tools.get_recently_added(
                    limit=arguments.get("limit", 10),
                    days=arguments.get("days", 7)
                )
            elif name == "get_knowledge_card":
                result = tools.get_knowledge_card(
                    chunk_id=arguments["chunk_id"]
                )
            elif name == "search_knowledge_cards":
                result = tools.search_knowledge_cards(
                    query=arguments["query"],
                    limit=arguments.get("limit", 10)
                )
            elif name == "list_clusters":
                result = tools.list_clusters()
            elif name == "get_cluster":
                result = tools.get_cluster(
                    cluster_id=arguments["cluster_id"],
                    include_chunks=arguments.get("include_chunks", True),
                    limit=arguments.get("limit", 20)
                )
            elif name == "search_within_cluster":
                result = tools.search_within_cluster_tool(
                    cluster_id=arguments["cluster_id"],
                    query=arguments["query"],
                    limit=arguments.get("limit", 10)
                )
            elif name == "get_related_clusters":
                result = tools.get_related_clusters(
                    cluster_id=arguments["cluster_id"],
                    limit=arguments.get("limit", 5),
                    distance_measure=arguments.get("distance_measure", "COSINE")
                )
            # Story 3.5 + 3.9: Reading Recommendations
            elif name == "get_reading_recommendations":
                result = tools.get_reading_recommendations(
                    scope=arguments.get("scope", "both"),
                    days=arguments.get("days", 14),
                    limit=arguments.get("limit", 10),
                    cluster_ids=arguments.get("cluster_ids"),
                    hot_sites=arguments.get("hot_sites"),
                    mode=arguments.get("mode", "balanced"),
                    include_seen=arguments.get("include_seen", False),
                    predictable=arguments.get("predictable", False)
                )
            elif name == "update_recommendation_domains":
                result = tools.update_recommendation_domains(
                    add_domains=arguments.get("add_domains"),
                    remove_domains=arguments.get("remove_domains")
                )
            elif name == "get_recommendation_config":
                result = tools.get_recommendation_config()
            # Story 3.9: Hot Sites Configuration
            elif name == "get_hot_sites_config":
                result = tools.get_hot_sites_config()
            elif name == "update_hot_sites_config":
                result = tools.update_hot_sites_config(
                    category=arguments["category"],
                    add_domains=arguments.get("add_domains"),
                    remove_domains=arguments.get("remove_domains"),
                    description=arguments.get("description")
                )
            # Story 3.8: Ranking Configuration
            elif name == "get_ranking_config":
                result = tools.get_ranking_config()
            elif name == "update_ranking_config":
                result = tools.update_ranking_config(
                    weights=arguments.get("weights"),
                    settings=arguments.get("settings")
                )
            else:
                result = {"error": f"Unknown tool: {name}"}

            # Return result as TextContent
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, indent=2)
            )]

    # Register prompt templates
    @server.list_prompts()
    async def list_prompts_handler():
        """List available prompt templates."""
        logger.info("Handling list_prompts request")
        return prompts.get_prompts()

    @server.get_prompt()
    async def get_prompt_handler(name: str, arguments: dict):
        """Get prompt messages for a template."""
        logger.info(f"Handling get_prompt request: {name}")
        return prompts.get_prompt_messages(name, arguments)

    logger.info("MCP server initialized successfully")
    logger.info("Starting stdio transport...")

    # Run the server with stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
