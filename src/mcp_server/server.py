"""
Consolidated MCP Server with OAuth 2.1 and Streamable HTTP transport.

This single FastAPI server handles:
- OAuth 2.1 with Dynamic Client Registration (RFC 7591)
- MCP Streamable HTTP transport (POST /)
- All knowledge base tools
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# Add current directory for imports
sys.path.insert(0, str(Path(__file__).parent))

import tools
from oauth_server import OAuthServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="KX-Hub MCP Server",
    description="MCP Server with OAuth 2.1 and Streamable HTTP transport",
    version="1.0.0",
)

# Initialize OAuth server
oauth_server = OAuthServer()

# Tool definitions for MCP
TOOL_DEFINITIONS = [
    {
        "name": "search_kb",
        "description": """Unified knowledge base search with flexible filtering.

Returns Knowledge Cards by default for fast comprehension (~5x fewer tokens).
Each result includes a detail_hint - use get_chunk(chunk_id) when you need:
- Full original content or exact quotes
- Related chunks via vector similarity
- Complete context for deep analysis

Two-step pattern: search_kb → scan cards → get_chunk for details.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "filters": {
                    "type": "object",
                    "description": "Optional filters: cluster_id, tags, author, source, date_range, period, include_content (default false)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_chunk",
        "description": "Get full details for a specific chunk including knowledge card and related chunks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chunk_id": {"type": "string", "description": "Chunk ID to retrieve"},
                "include_related": {
                    "type": "boolean",
                    "description": "Include related chunks",
                    "default": True,
                },
                "related_limit": {
                    "type": "integer",
                    "description": "Max related chunks (default 5)",
                    "default": 5,
                },
            },
            "required": ["chunk_id"],
        },
    },
    {
        "name": "get_recent",
        "description": "Get recent reading activity and chunks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max chunks to return (default 10)",
                    "default": 10,
                },
                "period": {
                    "type": "string",
                    "description": "Time period (default 'last_7_days')",
                    "default": "last_7_days",
                    "enum": [
                        "today",
                        "yesterday",
                        "last_3_days",
                        "last_week",
                        "last_7_days",
                        "last_month",
                        "last_30_days",
                    ],
                },
            },
        },
    },
    {
        "name": "get_stats",
        "description": "Get knowledge base statistics (total chunks, sources, authors, tags)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_sources",
        "description": "List all sources (books, articles) with metadata",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max sources to return (default 50)",
                    "default": 50,
                }
            },
        },
    },
    {
        "name": "get_source",
        "description": "Get source details with chunks and cross-source relationships",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "Source ID to retrieve"},
                "include_relationships": {
                    "type": "boolean",
                    "description": "Include relationships to other sources",
                    "default": True,
                },
            },
            "required": ["source_id"],
        },
    },
    {
        "name": "configure_kb",
        "description": "Unified configuration tool for kx-hub settings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform",
                    "enum": [
                        "show_all",
                        "show_ranking",
                        "show_domains",
                        "show_hot_sites",
                        "update_ranking",
                        "update_domains",
                        "update_hot_sites",
                    ],
                },
                "params": {
                    "type": "object",
                    "description": "Action-specific parameters",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "search_within_source",
        "description": "Semantic search restricted to a specific source",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "Source ID to search within",
                },
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10)",
                    "default": 10,
                },
            },
            "required": ["source_id", "query"],
        },
    },
    {
        "name": "get_contradictions",
        "description": "Find contradicting ideas across different sources",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max contradictions to return (default 10)",
                    "default": 10,
                }
            },
        },
    },
    {
        "name": "get_reading_recommendations",
        "description": "Get AI-powered reading recommendations based on your KB content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Lookback period in days (default 14)",
                    "default": 14,
                },
                "hot_sites": {
                    "type": "string",
                    "description": "Source category",
                    "enum": ["tech", "tech_de", "ai", "devops", "business", "all"],
                },
                "include_seen": {
                    "type": "boolean",
                    "description": "Include previously shown",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max recommendations (default 10)",
                    "default": 10,
                },
                "mode": {
                    "type": "string",
                    "description": "Discovery mode",
                    "default": "balanced",
                    "enum": ["balanced", "fresh", "deep", "surprise_me"],
                },
                "predictable": {
                    "type": "boolean",
                    "description": "Disable query variation",
                    "default": False,
                },
            },
        },
    },
]


def verify_jwt_token(request: Request) -> Optional[Dict[str, Any]]:
    """Verify JWT token from Authorization header."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]  # Remove "Bearer " prefix
    try:
        import jwt

        public_key = oauth_server.get_public_key()
        # Skip audience verification - aud is dynamic client_id from DCR
        decoded = jwt.decode(
            token, public_key, algorithms=["RS256"], options={"verify_aud": False}
        )
        return decoded
    except Exception as e:
        logger.error(f"JWT verification failed: {e}")
        return None


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call a tool by name with arguments."""
    logger.info(f"Calling tool: {name}")

    if name == "search_kb":
        return tools.search_kb(
            query=arguments.get("query", ""),
            filters=arguments.get("filters"),
            limit=arguments.get("limit", 10),
        )
    elif name == "get_chunk":
        return tools.get_chunk(
            chunk_id=arguments.get("chunk_id", ""),
            include_related=arguments.get("include_related", True),
            related_limit=arguments.get("related_limit", 5),
        )
    elif name == "get_recent":
        return tools.get_recent(
            period=arguments.get("period", "last_7_days"),
            limit=arguments.get("limit", 10),
        )
    elif name == "get_stats":
        return tools.get_stats()
    elif name == "list_sources":
        return tools.list_sources(limit=arguments.get("limit", 50))
    elif name == "get_source":
        return tools.get_source(
            source_id=arguments.get("source_id", ""),
            include_relationships=arguments.get("include_relationships", True),
        )
    elif name == "configure_kb":
        return tools.configure_kb(
            action=arguments.get("action", ""), params=arguments.get("params")
        )
    elif name == "search_within_source":
        return tools.search_within_source(
            source_id=arguments.get("source_id", ""),
            query=arguments.get("query", ""),
            limit=arguments.get("limit", 10),
        )
    elif name == "get_contradictions":
        return tools.get_contradictions(limit=arguments.get("limit", 10))
    elif name == "get_reading_recommendations":
        return tools.get_reading_recommendations(
            days=arguments.get("days", 14),
            hot_sites=arguments.get("hot_sites"),
            include_seen=arguments.get("include_seen", False),
            limit=arguments.get("limit", 10),
            mode=arguments.get("mode", "balanced"),
            predictable=arguments.get("predictable", False),
        )
    else:
        raise ValueError(f"Unknown tool: {name}")


# ==================== Health Check ====================


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "kx-hub-mcp-server",
        "transport": "streamable-http",
    }


# ==================== OAuth 2.1 Endpoints ====================


@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata(request: Request):
    """OAuth 2.1 Authorization Server Metadata (RFC 8414)."""
    return await oauth_server.authorization_server_metadata(request)


@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource(request: Request):
    """OAuth Protected Resource Metadata (RFC 9728)."""
    return await oauth_server.oauth_protected_resource_metadata(request)


@app.post("/register")
async def register_client(request: Request):
    """Dynamic Client Registration (RFC 7591)."""
    return await oauth_server.register_client(request)


@app.get("/authorize")
@app.post("/authorize")
async def authorize(request: Request):
    """Authorization endpoint - show login page and handle consent."""
    return await oauth_server.authorize(request)


@app.post("/token")
async def token_endpoint(request: Request):
    """Token endpoint - exchange authorization code for tokens."""
    return await oauth_server.token(request)


# ==================== MCP Streamable HTTP ====================


@app.post("/")
@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """
    MCP Streamable HTTP endpoint.
    Handles JSON-RPC requests for MCP protocol.
    """
    # Verify JWT token
    token_data = verify_jwt_token(request)
    if not token_data:
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "error_description": "Invalid or missing token",
            },
        )

    logger.info(f"MCP request from user: {token_data.get('sub')}")

    try:
        body = await request.json()
        method = body.get("method")
        request_id = body.get("id")

        logger.info(f"MCP method: {method}")

        if method == "initialize":
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "kx-hub", "version": "1.0.0"},
                        "capabilities": {"tools": {}},
                    },
                }
            )

        elif method == "tools/list":
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": TOOL_DEFINITIONS},
                }
            )

        elif method == "tools/call":
            tool_name = body.get("params", {}).get("name")
            tool_args = body.get("params", {}).get("arguments", {})

            try:
                result = call_tool(tool_name, tool_args)
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(result)}]
                        },
                    }
                )
            except Exception as e:
                logger.error(f"Tool call error: {e}", exc_info=True)
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32603, "message": str(e)},
                    }
                )

        elif method == "notifications/initialized":
            # 204 No Content must have no body - use Response instead of JSONResponse
            return Response(status_code=204)

        else:
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )

    except Exception as e:
        logger.error(f"MCP endpoint error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            },
        )


@app.get("/")
async def root():
    """Server info endpoint."""
    return {
        "name": "kx-hub-mcp-server",
        "version": "1.0.0",
        "transport": "streamable-http",
        "oauth": {
            "metadata": "/.well-known/oauth-authorization-server",
            "protected_resource": "/.well-known/oauth-protected-resource",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
