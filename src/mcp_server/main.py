#!/usr/bin/env python3
"""
MCP Server for kx-hub Knowledge Base Access.

This server exposes the kx-hub Firestore knowledge base via the Model Context
Protocol (MCP) using either stdio transport (local) or SSE transport (remote).

Transport modes:
- stdio: For local Claude Desktop use (default)
- sse: For remote access via HTTPS with Bearer token authentication
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


def create_mcp_server() -> Server:
    """
    Create and configure the MCP server instance with all handlers.

    Returns:
        Configured Server instance ready to run

    This function is shared between stdio and SSE transport modes.
    """
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
                name="search_kb",
                description="Unified knowledge base search with flexible filtering (Story 4.1). Combines semantic search with cluster, metadata, time, and knowledge card filters.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query"
                        },
                        "filters": {
                            "type": "object",
                            "description": "Optional filters to narrow results",
                            "properties": {
                                "cluster_id": {
                                    "type": "string",
                                    "description": "Scope search to specific cluster ID"
                                },
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Filter by tags (array-contains-any)"
                                },
                                "author": {
                                    "type": "string",
                                    "description": "Filter by exact author name"
                                },
                                "source": {
                                    "type": "string",
                                    "description": "Filter by source (e.g., 'kindle', 'reader')"
                                },
                                "date_range": {
                                    "type": "object",
                                    "description": "Filter by date range",
                                    "properties": {
                                        "start": {
                                            "type": "string",
                                            "description": "Start date in YYYY-MM-DD format"
                                        },
                                        "end": {
                                            "type": "string",
                                            "description": "End date in YYYY-MM-DD format"
                                        }
                                    },
                                    "required": ["start", "end"]
                                },
                                "period": {
                                    "type": "string",
                                    "description": "Relative time period",
                                    "enum": ["yesterday", "last_3_days", "last_week", "last_7_days", "last_month", "last_30_days"]
                                },
                                "search_cards_only": {
                                    "type": "boolean",
                                    "description": "Search knowledge card summaries only (default false)",
                                    "default": false
                                }
                            }
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
                name="get_chunk",
                description="Get full details for a specific chunk including knowledge card and related chunks (Story 4.2). Consolidates get_related_chunks and get_knowledge_card into one call.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "chunk_id": {
                            "type": "string",
                            "description": "Chunk ID to retrieve"
                        },
                        "include_related": {
                            "type": "boolean",
                            "description": "Include related chunks via vector similarity (default true)",
                            "default": True
                        },
                        "related_limit": {
                            "type": "integer",
                            "description": "Maximum related chunks to return (default 5, max 20)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": ["chunk_id"]
                }
            ),
            Tool(
                name="get_recent",
                description="Get recent reading activity and chunks (Story 4.3). Consolidates get_recently_added and get_reading_activity into one call.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "period": {
                            "type": "string",
                            "description": "Time period (default 'last_7_days')",
                            "enum": ["today", "yesterday", "last_3_days", "last_week", "last_7_days", "last_month", "last_30_days"],
                            "default": "last_7_days"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum chunks to return (default 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50
                        }
                    }
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
                name="list_clusters",
                description="List all semantic clusters with metadata",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="get_cluster",
                description="Get cluster details with member chunks and related clusters (Story 4.4). Consolidates get_cluster and get_related_clusters.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "cluster_id": {
                            "type": "string",
                            "description": "Cluster ID to fetch"
                        },
                        "include_members": {
                            "type": "boolean",
                            "description": "Whether to include member chunks (default True)",
                            "default": True
                        },
                        "include_related": {
                            "type": "boolean",
                            "description": "Whether to include related clusters (default True)",
                            "default": True
                        },
                        "member_limit": {
                            "type": "integer",
                            "description": "Maximum member chunks to return (default 20)",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 50
                        },
                        "related_limit": {
                            "type": "integer",
                            "description": "Maximum related clusters to return (default 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": ["cluster_id"]
                }
            ),
            Tool(
                name="configure_kb",
                description="Unified configuration tool for kx-hub settings (Story 4.5). Consolidates all configuration tools into single entry point.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Action to perform",
                            "enum": ["show_all", "show_ranking", "show_domains", "show_hot_sites", "update_ranking", "update_domains", "update_hot_sites"]
                        },
                        "params": {
                            "type": "object",
                            "description": "Action-specific parameters (optional)",
                            "properties": {
                                "weights": {
                                    "type": "object",
                                    "description": "Ranking weights for update_ranking (must sum to 1.0)",
                                    "properties": {
                                        "relevance": {"type": "number"},
                                        "recency": {"type": "number"},
                                        "depth": {"type": "number"},
                                        "authority": {"type": "number"}
                                    }
                                },
                                "settings": {
                                    "type": "object",
                                    "description": "Ranking settings for update_ranking"
                                },
                                "add": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Domains to add (for update_domains, update_hot_sites)"
                                },
                                "remove": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Domains to remove (for update_domains, update_hot_sites)"
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Category name (for update_hot_sites)"
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Category description (for update_hot_sites)"
                                }
                            }
                        }
                    },
                    "required": ["action"]
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
            # Story 3.8: Ranking Configuration
        ]

    @server.call_tool()
    async def call_tool_handler(name: str, arguments: Any):
        """Execute a tool by name with arguments."""
        logger.info(f"Handling call_tool request: {name}")

        try:
            if name == "search_kb":
                result = tools.search_kb(
                    query=arguments.get("query"),
                    filters=arguments.get("filters"),
                    limit=arguments.get("limit", 10)
                )

            elif name == "get_chunk":
                result = tools.get_chunk(
                    chunk_id=arguments["chunk_id"],
                    include_related=arguments.get("include_related", True),
                    related_limit=arguments.get("related_limit", 5)
                )

            elif name == "get_recent":
                result = tools.get_recent(
                    period=arguments.get("period", "last_7_days"),
                    limit=arguments.get("limit", 10)
                )

            elif name == "get_stats":
                result = tools.get_stats()
            elif name == "list_clusters":
                result = tools.list_clusters()
            elif name == "get_cluster":
                result = tools.get_cluster(
                    cluster_id=arguments["cluster_id"],
                    include_members=arguments.get("include_members", True),
                    include_related=arguments.get("include_related", True),
                    member_limit=arguments.get("member_limit", 20),
                    related_limit=arguments.get("related_limit", 5)
                )
            elif name == "configure_kb":
                result = tools.configure_kb(
                    action=arguments["action"],
                    params=arguments.get("params")
                )
            elif name == "search_within_cluster":
                result = tools.search_within_cluster_tool(
                    cluster_id=arguments["cluster_id"],
                    query=arguments["query"],
                    limit=arguments.get("limit", 10)
                )
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
    return server


async def run_stdio_mode():
    """Run MCP server with stdio transport (local mode)."""
    logger.info("Starting in STDIO mode (local)")

    # Validate environment variables
    required_vars = ['GOOGLE_APPLICATION_CREDENTIALS', 'GCP_PROJECT', 'GCP_REGION', 'FIRESTORE_COLLECTION']
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    logger.info(f"GCP Project: {os.getenv('GCP_PROJECT')}")
    logger.info(f"GCP Region: {os.getenv('GCP_REGION')}")
    logger.info(f"Firestore Collection: {os.getenv('FIRESTORE_COLLECTION')}")

    # Create server
    server = create_mcp_server()

    # Run with stdio transport
    logger.info("Starting stdio transport...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run_sse_mode():
    """Run MCP server with SSE transport (remote mode)."""
    import uvicorn
    from server_sse import create_sse_app

    logger.info("Starting in SSE mode (remote)")

    # For Cloud Run, GOOGLE_APPLICATION_CREDENTIALS is not needed (uses metadata server)
    # But we still need GCP_PROJECT, GCP_REGION, FIRESTORE_COLLECTION
    required_vars = ['GCP_PROJECT', 'GCP_REGION', 'FIRESTORE_COLLECTION', 'MCP_AUTH_TOKEN']
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    logger.info(f"GCP Project: {os.getenv('GCP_PROJECT')}")
    logger.info(f"GCP Region: {os.getenv('GCP_REGION')}")
    logger.info(f"Firestore Collection: {os.getenv('FIRESTORE_COLLECTION')}")
    logger.info("MCP_AUTH_TOKEN: [REDACTED]")

    # Create server
    server = create_mcp_server()

    # Create SSE app with authentication
    app = create_sse_app(server)

    # Run with uvicorn
    port = int(os.getenv("PORT", "8080"))
    logger.info(f"Starting SSE server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


async def main():
    """Main entry point - routes to stdio or SSE mode based on TRANSPORT_MODE env var."""
    transport_mode = os.getenv("TRANSPORT_MODE", "stdio").lower()

    if transport_mode == "sse":
        # SSE mode is synchronous (uvicorn handles async)
        run_sse_mode()
    elif transport_mode == "stdio":
        # stdio mode is async
        await run_stdio_mode()
    else:
        logger.error(f"Invalid TRANSPORT_MODE: {transport_mode}. Must be 'stdio' or 'sse'.")
        sys.exit(1)


if __name__ == "__main__":
    transport_mode = os.getenv("TRANSPORT_MODE", "stdio").lower()
    if transport_mode == "sse":
        # SSE mode runs sync
        run_sse_mode()
    else:
        # stdio mode runs async
        asyncio.run(main())
