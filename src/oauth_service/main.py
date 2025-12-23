"""
OAuth 2.1 Authorization Server for Cloud Run.
"""

import sys
from pathlib import Path

# Add oauth_service directory to path for module imports
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from oauth_server import OAuthServer

# Initialize FastAPI app
app = FastAPI(
    title="KX-Hub OAuth Server",
    description="OAuth 2.1 Authorization Server with Dynamic Client Registration",
    version="1.0.0"
)

# Initialize OAuth server
oauth_server = OAuthServer()

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "kx-hub-oauth-server"}

# OAuth 2.1 Discovery
@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata(request: Request):
    """OAuth 2.1 Authorization Server Metadata (RFC 8414)."""
    return await oauth_server.authorization_server_metadata(request)

# Dynamic Client Registration
@app.post("/register")
async def register_client(request: Request):
    """Dynamic Client Registration (RFC 7591)."""
    return await oauth_server.register_client(request)

# Authorization endpoint (handles both GET and POST)
@app.get("/authorize")
@app.post("/authorize")
async def authorize(request: Request):
    """Authorization endpoint - show login page and handle consent."""
    return await oauth_server.authorize(request)

# Token endpoint
@app.post("/token")
async def token_endpoint(request: Request):
    """Token endpoint - exchange authorization code for tokens."""
    return await oauth_server.token(request)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
