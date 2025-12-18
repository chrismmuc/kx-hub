#!/usr/bin/env python3
"""
SSE Server for Remote MCP Access.

This module provides Server-Sent Events (SSE) transport for the MCP server,
enabling remote access via HTTPS with Bearer token authentication.
"""

import os
import logging
from typing import Optional
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from mcp.server.sse import SseServerTransport
from mcp.server import Server

logger = logging.getLogger('kx-hub-mcp.sse')


class BearerTokenAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce Bearer token authentication on all requests.

    Security:
    - Validates Authorization header contains correct Bearer token
    - Returns 401 for missing or invalid tokens
    - Does not leak token values in logs or responses
    - Excludes health check endpoint from auth (for Cloud Run)
    """

    def __init__(self, app, required_token: str):
        super().__init__(app)
        self.required_token = required_token

    async def dispatch(self, request: Request, call_next):
        # Allow health checks without authentication (Cloud Run requirement)
        if request.url.path == "/health":
            return await call_next(request)

        # Extract Authorization header
        auth_header = request.headers.get("Authorization", "")

        # Check for Bearer token format
        if not auth_header.startswith("Bearer "):
            logger.warning(f"Missing or invalid Authorization header from {request.client.host}")
            return JSONResponse(
                {"error": "Unauthorized", "message": "Missing or invalid Authorization header"},
                status_code=401
            )

        # Extract token (without logging it)
        token = auth_header[7:]  # Remove "Bearer " prefix

        # Validate token
        if token != self.required_token:
            logger.warning(f"Invalid token attempt from {request.client.host}")
            return JSONResponse(
                {"error": "Unauthorized", "message": "Invalid authentication token"},
                status_code=401
            )

        # Token valid - proceed
        logger.info(f"Authenticated request from {request.client.host} to {request.url.path}")
        return await call_next(request)


async def handle_sse(request: Request) -> Response:
    """
    Handle SSE connection for MCP protocol.

    This endpoint receives MCP protocol messages via SSE and returns responses.
    """
    # Get the MCP server instance from app state
    mcp_server: Server = request.app.state.mcp_server

    # Create SSE transport
    transport = SseServerTransport("/messages")

    # Connect transport to MCP server
    async with transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options()
        )

    # This won't be reached as SSE keeps connection open
    return Response()


async def health_check(request: Request) -> JSONResponse:
    """
    Health check endpoint for Cloud Run.

    This endpoint is excluded from authentication to allow Cloud Run
    to monitor service health.
    """
    return JSONResponse({"status": "healthy"})


def create_sse_app(mcp_server: Server) -> Starlette:
    """
    Create Starlette application with SSE transport and authentication.

    Args:
        mcp_server: Initialized MCP Server instance

    Returns:
        Starlette application ready to serve

    Security:
    - Bearer token authentication on all routes except /health
    - Token loaded from environment variable MCP_AUTH_TOKEN
    - No CORS headers (not needed for MCP SSE)
    """
    # Load authentication token from environment
    auth_token = os.getenv("MCP_AUTH_TOKEN")
    if not auth_token:
        raise ValueError("MCP_AUTH_TOKEN environment variable must be set for SSE mode")

    logger.info("Creating SSE server with Bearer token authentication")

    # Define routes
    routes = [
        Route("/sse", handle_sse, methods=["GET", "POST"]),
        Route("/health", health_check, methods=["GET"]),
    ]

    # Create middleware stack
    middleware = [
        Middleware(BearerTokenAuthMiddleware, required_token=auth_token)
    ]

    # Create Starlette app
    app = Starlette(
        routes=routes,
        middleware=middleware,
        debug=False  # Never enable debug in production
    )

    # Store MCP server instance in app state
    app.state.mcp_server = mcp_server

    logger.info("SSE server created successfully")
    return app
