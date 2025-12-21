"""
FastAPI HTTP server for MCP tools.
Provides simple HTTP endpoints for all knowledge base tools.
"""

import logging
from typing import Any, Dict, Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import sys
from pathlib import Path

# Add parent directory to path to import tools module
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))
import tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="KX-Hub Tools API",
    description="HTTP API for knowledge base tools",
    version="1.0.0"
)

# Request/Response models

class SearchKbRequest(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None
    limit: int = Field(default=10, ge=1, le=50)

class GetChunkRequest(BaseModel):
    chunk_id: str
    include_related: bool = True
    related_limit: int = Field(default=5, ge=1, le=20)

class GetRecentRequest(BaseModel):
    period: str = "last_7_days"
    limit: int = Field(default=10, ge=1, le=50)

class GetClusterRequest(BaseModel):
    cluster_id: str
    include_members: bool = True
    include_related: bool = True
    member_limit: int = Field(default=20, ge=1, le=50)
    related_limit: int = Field(default=5, ge=1, le=20)

class ConfigureKbRequest(BaseModel):
    action: str
    params: Optional[Dict[str, Any]] = None

class SearchWithinClusterRequest(BaseModel):
    cluster_id: str
    query: str
    limit: int = Field(default=10, ge=1, le=50)

class GetReadingRecommendationsRequest(BaseModel):
    cluster_ids: Optional[List[str]] = None
    days: int = Field(default=14, ge=1)
    hot_sites: Optional[str] = None
    include_seen: bool = False
    limit: int = Field(default=10, ge=1, le=50)
    mode: str = "balanced"
    predictable: bool = False
    scope: str = "both"

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "kx-hub-tools-api"}

# Tool endpoints

@app.post("/tools/search_kb")
async def search_kb_endpoint(request: SearchKbRequest):
    """
    Unified knowledge base search with flexible filtering.
    """
    try:
        logger.info(f"search_kb: query={request.query}, limit={request.limit}")
        result = tools.search_kb(
            query=request.query,
            filters=request.filters,
            limit=request.limit
        )
        return result
    except Exception as e:
        logger.error(f"Error in search_kb: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/get_chunk")
async def get_chunk_endpoint(request: GetChunkRequest):
    """
    Get full details for a specific chunk including knowledge card and related chunks.
    """
    try:
        logger.info(f"get_chunk: chunk_id={request.chunk_id}")
        result = tools.get_chunk(
            chunk_id=request.chunk_id,
            include_related=request.include_related,
            related_limit=request.related_limit
        )
        return result
    except Exception as e:
        logger.error(f"Error in get_chunk: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/get_recent")
async def get_recent_endpoint(request: GetRecentRequest):
    """
    Get recent reading activity and chunks.
    """
    try:
        logger.info(f"get_recent: period={request.period}, limit={request.limit}")
        result = tools.get_recent(
            period=request.period,
            limit=request.limit
        )
        return result
    except Exception as e:
        logger.error(f"Error in get_recent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/get_stats")
async def get_stats_endpoint():
    """
    Get knowledge base statistics.
    """
    try:
        logger.info("get_stats")
        result = tools.get_stats()
        return result
    except Exception as e:
        logger.error(f"Error in get_stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/list_clusters")
async def list_clusters_endpoint():
    """
    List all semantic clusters with metadata.
    """
    try:
        logger.info("list_clusters")
        result = tools.list_clusters()
        return result
    except Exception as e:
        logger.error(f"Error in list_clusters: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/get_cluster")
async def get_cluster_endpoint(request: GetClusterRequest):
    """
    Get cluster details with member chunks and related clusters.
    """
    try:
        logger.info(f"get_cluster: cluster_id={request.cluster_id}")
        result = tools.get_cluster(
            cluster_id=request.cluster_id,
            include_members=request.include_members,
            include_related=request.include_related,
            member_limit=request.member_limit,
            related_limit=request.related_limit
        )
        return result
    except Exception as e:
        logger.error(f"Error in get_cluster: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/configure_kb")
async def configure_kb_endpoint(request: ConfigureKbRequest):
    """
    Unified configuration tool for kx-hub settings.
    """
    try:
        logger.info(f"configure_kb: action={request.action}")
        result = tools.configure_kb(
            action=request.action,
            params=request.params
        )
        return result
    except Exception as e:
        logger.error(f"Error in configure_kb: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/search_within_cluster")
async def search_within_cluster_endpoint(request: SearchWithinClusterRequest):
    """
    Semantic search restricted to a specific cluster.
    """
    try:
        logger.info(f"search_within_cluster: cluster_id={request.cluster_id}, query={request.query}")
        result = tools.search_within_cluster(
            cluster_id=request.cluster_id,
            query=request.query,
            limit=request.limit
        )
        return result
    except Exception as e:
        logger.error(f"Error in search_within_cluster: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/get_reading_recommendations")
async def get_reading_recommendations_endpoint(request: GetReadingRecommendationsRequest):
    """
    Get AI-powered reading recommendations based on your KB content.
    """
    try:
        logger.info(f"get_reading_recommendations: mode={request.mode}, limit={request.limit}")
        result = tools.get_reading_recommendations(
            cluster_ids=request.cluster_ids,
            days=request.days,
            hot_sites=request.hot_sites,
            include_seen=request.include_seen,
            limit=request.limit,
            mode=request.mode,
            predictable=request.predictable,
            scope=request.scope
        )
        return result
    except Exception as e:
        logger.error(f"Error in get_reading_recommendations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
