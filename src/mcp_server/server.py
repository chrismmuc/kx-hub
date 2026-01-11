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
    # Story 7.1: Async Recommendations
    {
        "name": "recommendations",
        "description": """Get reading recommendations based on your KB content.

Simple interface - settings come from config/recommendations in Firestore.

Usage:
1. recommendations() → starts job, returns {job_id, poll_after_seconds}
2. recommendations(job_id="...") → poll for results
3. recommendations(topic="kubernetes") → one-time topic override""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job ID to poll (omit to start new job)",
                },
                "topic": {
                    "type": "string",
                    "description": "Optional topic override (e.g., 'kubernetes security')",
                },
            },
        },
    },
    {
        "name": "recommendations_history",
        "description": "Get all recommendations from the last N days as a flat list.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Lookback period in days (default 14)",
                    "default": 14,
                },
            },
        },
    },
    # Epic 10: Feynman-style Problems
    {
        "name": "problems",
        "description": """Manage Feynman-style problems for knowledge-driven article ideation.

Based on Richard Feynman's "12 Favorite Problems" method: define your important questions,
and the system automatically matches relevant evidence from your reading.

Actions:
- add: Create a new problem with optional description
- list: Show all active problems with evidence counts
- analyze: Get evidence + connections for a problem (or all problems if no ID)
- archive: Archive a resolved/inactive problem

Usage patterns:
- problems(action="add", problem="Why do feature flags fail?", description="Teams adopt them but...")
- problems(action="list")
- problems(action="analyze", problem_id="prob_001")
- problems(action="analyze")  # All active problems
- problems(action="archive", problem_id="prob_001")""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform",
                    "enum": ["add", "list", "analyze", "archive"],
                },
                "problem": {
                    "type": "string",
                    "description": "Problem statement (required for 'add')",
                },
                "description": {
                    "type": "string",
                    "description": "Optional context/motivation for the problem",
                },
                "problem_id": {
                    "type": "string",
                    "description": "Problem ID (for 'analyze' single or 'archive')",
                },
            },
            "required": ["action"],
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
    # Story 7.1: Async Recommendations, Story 7.2: Simplified interface
    elif name == "recommendations":
        return tools.recommendations(
            job_id=arguments.get("job_id"),
            topic=arguments.get("topic"),
        )
    elif name == "recommendations_history":
        return tools.recommendations_history(
            days=arguments.get("days", 14),
        )
    # Epic 10: Feynman-style Problems
    elif name == "problems":
        return tools.problems(
            action=arguments.get("action", ""),
            problem=arguments.get("problem"),
            description=arguments.get("description"),
            problem_id=arguments.get("problem_id"),
        )
    else:
        raise ValueError(f"Unknown tool: {name}")


# ==================== Async Job Execution (Epic 7) ====================


@app.post("/jobs/run")
async def run_job(request: Request):
    """
    Execute an async job. Called by Cloud Tasks.

    Epic 7: Cloud Tasks calls this endpoint to execute recommendation jobs.
    The job_id and params are passed in the request body.

    Request body:
        {
            "job_id": "rec-abc123",
            "job_type": "recommendations",
            "params": {"mode": "balanced", "limit": 10, ...}
        }

    Security: This endpoint is protected by Cloud Run IAM.
    Only the cloud-tasks-invoker service account can call it.
    """
    try:
        body = await request.json()
        job_id = body.get("job_id")
        job_type = body.get("job_type")
        params = body.get("params", {})

        if not job_id or not job_type:
            raise HTTPException(status_code=400, detail="Missing job_id or job_type")

        logger.info(f"Executing async job: {job_id} (type={job_type})")

        if job_type == "recommendations":
            # Execute the recommendations job synchronously
            # (Cloud Tasks handles the async dispatch)
            tools.execute_recommendations_job(job_id, params)
            return {"status": "completed", "job_id": job_id}
        else:
            raise HTTPException(status_code=400, detail=f"Unknown job_type: {job_type}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
