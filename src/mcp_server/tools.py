"""
MCP Tool handlers for search and query operations.

Tools:
- configure_kb: Unified configuration tool for all settings (Story 4.5)
- get_chunk: Get full chunk details with knowledge card and related chunks (Story 4.2)
- get_cluster: Get cluster details with members and related clusters (Story 4.4)
- get_recent: Get recent chunks and reading activity (Story 4.3)
- search_kb: Unified search tool with flexible filters (Story 4.1)
- search_semantic: Semantic search using query embeddings
- search_by_metadata: Filter by tags, author, source
- get_related_chunks: Find similar chunks to a given chunk
- get_stats: Get knowledge base statistics
- search_by_date_range: Query chunks by date range
- search_by_relative_time: Query chunks using relative time periods (yesterday, last week, etc.)
- get_reading_activity: Get reading activity summary and statistics
- get_recently_added: Get most recently added chunks
- get_related_clusters: Find clusters conceptually related to a given cluster (Story 3.4)
- recommendations: Async AI-powered reading recommendations via Cloud Tasks (Story 7.1)
- update_recommendation_domains: Update recommendation domain whitelist (Story 3.5)
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import embeddings
import firestore_client

logger = logging.getLogger(__name__)


def _format_urls(chunk: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Extract and format URL fields from chunk data.

    Story 2.7: URL Link Storage - provides traceability back to Readwise.

    Args:
        chunk: Chunk dictionary from Firestore

    Returns:
        Dictionary with URL fields (values may be None)
    """
    return {
        "readwise_url": chunk.get("readwise_url"),
        "source_url": chunk.get("source_url"),
        "highlight_url": chunk.get("highlight_url"),
    }


def _format_knowledge_card(chunk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract and format knowledge card from chunk data.

    Args:
        chunk: Chunk dictionary from Firestore

    Returns:
        Formatted knowledge card dict or None if missing
    """
    knowledge_card = chunk.get("knowledge_card")
    if not knowledge_card:
        return None

    return {
        "summary": knowledge_card.get("summary", ""),
        "takeaways": knowledge_card.get("takeaways", []),
    }


def _format_source_info(chunk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract and format source information from chunk data.
    Story 4.3: Replaced _format_cluster_info with source-based approach.

    Args:
        chunk: Chunk dictionary from Firestore

    Returns:
        Formatted source dict or None if no source_id
    """
    source_id = chunk.get("source_id")

    if not source_id:
        # Fallback: derive from title if no source_id
        return {
            "source_id": None,
            "title": chunk.get("title", "Unknown"),
            "author": chunk.get("author", "Unknown"),
        }

    # Fetch source metadata from Firestore
    try:
        source_metadata = firestore_client.get_source_by_id(source_id)
        if source_metadata:
            return {
                "source_id": source_id,
                "title": source_metadata.get("title", "Unknown"),
                "author": source_metadata.get("author", "Unknown"),
                "type": source_metadata.get("type", "unknown"),
                "chunk_count": source_metadata.get("chunk_count", 0),
            }
        else:
            return {
                "source_id": source_id,
                "title": chunk.get("title", "Unknown"),
                "author": chunk.get("author", "Unknown"),
            }
    except Exception as e:
        logger.warning(f"Failed to fetch source metadata for {source_id}: {e}")
        return {
            "source_id": source_id,
            "title": chunk.get("title", "Unknown"),
            "author": chunk.get("author", "Unknown"),
        }


def _format_search_result(
    chunk: Dict[str, Any], rank: int, include_content: bool = False
) -> Dict[str, Any]:
    """
    Format a chunk as a search result.

    Story 3.10: Returns knowledge cards by default, full content only on request.
    This reduces token usage by ~5x while maintaining quality.

    Args:
        chunk: Chunk dictionary from Firestore
        rank: Result ranking (1-based)
        include_content: If True, include snippet and full_content (default False)

    Returns:
        Formatted search result dict with detail_hint for on-demand loading
    """
    chunk_id = chunk.get("id") or chunk.get("chunk_id", "unknown")
    title = chunk.get("title", "Untitled")
    author_name = chunk.get("author", "Unknown")
    source_name = chunk.get("source", "unknown")
    tags_list = chunk.get("tags", [])
    chunk_index = chunk.get("chunk_index", 0)
    total_chunks = chunk.get("total_chunks", 1)

    # Extract knowledge card and URLs
    knowledge_card = _format_knowledge_card(chunk)
    urls = _format_urls(chunk)

    # Base result with knowledge card (always included)
    result = {
        "rank": rank,
        "chunk_id": chunk_id,
        "title": title,
        "author": author_name,
        "source": source_name,
        "tags": tags_list,
        "chunk_info": f"{chunk_index + 1}/{total_chunks}",
        "knowledge_card": knowledge_card,
        "detail_hint": f"Use get_chunk('{chunk_id}') for full content and related chunks",
        **urls,
    }

    # Story 3.10: Only include content when explicitly requested
    if include_content:
        content = chunk.get("content", "")
        snippet = content[:500] + "..." if len(content) > 500 else content
        result["snippet"] = snippet
        result["full_content"] = content
        # Also include source_info for backwards compatibility
        result["source"] = _format_source_info(chunk)

    return result


def get_chunk(
    chunk_id: str, include_related: bool = True, related_limit: int = 5
) -> Dict[str, Any]:
    """
    Get full chunk details with embedded knowledge card and related chunks.

    Story 4.2: Consolidates get_related_chunks and get_knowledge_card into one tool.
    Returns comprehensive chunk information in a single API call.

    Args:
        chunk_id: Chunk ID to retrieve
        include_related: Include related chunks via vector similarity (default True)
        related_limit: Maximum related chunks to return (default 5, max 20)

    Returns:
        Dictionary with chunk details, knowledge card, cluster info, related chunks, and URLs
    """
    try:
        logger.info(
            f"Getting chunk {chunk_id} (include_related={include_related}, related_limit={related_limit})"
        )

        # Validate related_limit
        if related_limit < 1 or related_limit > 20:
            related_limit = min(max(related_limit, 1), 20)
            logger.warning(f"related_limit adjusted to valid range: {related_limit}")

        # Task 1.2: Fetch chunk by ID from Firestore
        chunk = firestore_client.get_chunk_by_id(chunk_id)

        if not chunk:
            # Task 1.7: Handle missing chunk gracefully
            logger.warning(f"Chunk not found: {chunk_id}")
            raise ValueError(f"Chunk not found: {chunk_id}")

        # Extract basic chunk fields
        title = chunk.get("title", "Untitled")
        author = chunk.get("author", "Unknown")
        source = chunk.get("source", "unknown")
        tags = chunk.get("tags", [])
        content = chunk.get("content", "")
        chunk_index = chunk.get("chunk_index", 0)
        total_chunks = chunk.get("total_chunks", 1)
        chunk_info = f"{chunk_index + 1}/{total_chunks}"

        # Task 1.3: Extract and format knowledge card from chunk data
        knowledge_card = _format_knowledge_card(chunk)

        # Task 1.7: Handle missing knowledge card gracefully (already handled by _format_knowledge_card returning None)
        if not knowledge_card:
            logger.info(f"No knowledge card found for chunk {chunk_id}")

        # Story 4.3: Extract source info instead of cluster
        source_info = _format_source_info(chunk)

        # Task 1.6: Format all URLs using _format_urls helper
        urls = _format_urls(chunk)

        # Task 1.4: Get related chunks via vector similarity (if include_related=true)
        related_chunks = []
        if include_related:
            embedding = chunk.get("embedding")
            if embedding:
                logger.info(
                    f"Finding {related_limit} related chunks using vector similarity"
                )
                # Find related chunks - request one extra to account for filtering out source chunk
                similar_chunks = firestore_client.find_nearest(
                    embedding_vector=embedding,
                    limit=related_limit + 1,  # Get one extra to filter out source chunk
                )

                # Filter out the source chunk and format related chunks
                for similar_chunk in similar_chunks:
                    similar_chunk_id = similar_chunk.get("id") or similar_chunk.get(
                        "chunk_id"
                    )

                    # Skip the source chunk itself
                    if similar_chunk_id == chunk_id:
                        continue

                    # Stop if we have enough related chunks
                    if len(related_chunks) >= related_limit:
                        break

                    # Format related chunk
                    similar_title = similar_chunk.get("title", "Untitled")
                    similar_author = similar_chunk.get("author", "Unknown")
                    similar_content = similar_chunk.get("content", "")

                    # Create snippet (first 200 chars)
                    snippet = (
                        similar_content[:200] + "..."
                        if len(similar_content) > 200
                        else similar_content
                    )

                    # Get similarity score if available (Firestore vector search includes this)
                    similarity_score = similar_chunk.get("similarity_score", 0.0)

                    related_chunks.append(
                        {
                            "chunk_id": similar_chunk_id,
                            "title": similar_title,
                            "author": similar_author,
                            "snippet": snippet,
                            "similarity_score": similarity_score,
                        }
                    )

                logger.info(f"Found {len(related_chunks)} related chunks")
            else:
                logger.warning(
                    f"No embedding found for chunk {chunk_id}, cannot retrieve related chunks"
                )

        # Get explicit relationships for this chunk (Story 4.3)
        relationships = firestore_client.get_chunk_relationships(chunk_id)
        formatted_relationships = []
        for rel in relationships:
            # Get connected chunk details
            connected_chunk = firestore_client.get_chunk_by_id(
                rel["connected_chunk_id"]
            )
            if connected_chunk:
                formatted_relationships.append(
                    {
                        "type": rel["type"],
                        "direction": rel["direction"],
                        "confidence": rel["confidence"],
                        "explanation": rel["explanation"],
                        "connected_chunk": {
                            "chunk_id": rel["connected_chunk_id"],
                            "title": connected_chunk.get("title", "Untitled"),
                            "author": connected_chunk.get("author", "Unknown"),
                        },
                    }
                )

        # Build complete response
        response = {
            "chunk_id": chunk_id,
            "title": title,
            "author": author,
            "source": source,
            "tags": tags,
            "content": content,
            "chunk_info": chunk_info,
            "knowledge_card": knowledge_card,
            "source_info": source_info,  # Story 4.3: Source instead of cluster
            "related_chunks": related_chunks,
            "relationships": formatted_relationships,  # Story 4.3: Explicit relationships
            **urls,  # Unpack URL fields (readwise_url, source_url, highlight_url)
        }

        logger.info(
            f"Successfully retrieved chunk {chunk_id} with {len(related_chunks)} related chunks, {len(formatted_relationships)} relationships"
        )
        return response

    except ValueError as e:
        # Re-raise ValueError for chunk not found
        raise e
    except Exception as e:
        logger.error(f"Error getting chunk {chunk_id}: {e}")
        raise RuntimeError(f"Failed to retrieve chunk: {str(e)}")


def get_recent(period: str = "last_7_days", limit: int = 10) -> Dict[str, Any]:
    """
    Get recent reading activity and chunks.

    Story 4.3: Consolidates get_recently_added and get_reading_activity into one tool.
    Returns recent chunks with activity summary and cluster distribution.

    Uses last_highlighted_at (actual reading time) instead of created_at (ingestion time)
    to show what the user actually read recently.

    Args:
        period: Time period (default "last_7_days")
        limit: Maximum chunks to return (default 10)

    Returns:
        Dictionary with recent chunks, activity summary, and cluster distribution
    """
    try:
        logger.info(f"Getting recent activity for period={period}, limit={limit}")

        # Period to days mapping
        PERIOD_TO_DAYS = {
            "today": 1,
            "yesterday": 1,
            "last_3_days": 3,
            "last_week": 7,
            "last_7_days": 7,
            "last_month": 30,
            "last_30_days": 30,
        }

        # Validate period
        if period not in PERIOD_TO_DAYS:
            logger.warning(f"Invalid period '{period}', defaulting to 'last_7_days'")
            period = "last_7_days"

        # Fetch recently READ chunks (by last_highlighted_at, not created_at)
        days = PERIOD_TO_DAYS[period]
        chunks = firestore_client.get_recently_read(limit=limit, days=days)
        logger.info(f"Fetched {len(chunks)} recently read chunks from last {days} days")

        # Task 1.3: Fetch activity summary from Firestore
        activity_summary = firestore_client.get_activity_summary(period=period)
        logger.info(
            f"Fetched activity summary: {activity_summary.get('total_chunks_added', 0)} chunks added"
        )

        # Task 1.4-1.6: Format each chunk with knowledge card, cluster info, and URLs
        recent_chunks = []
        cluster_counts = {}  # For cluster distribution calculation

        for chunk in chunks:
            chunk_id = chunk.get("id") or chunk.get("chunk_id", "unknown")
            title = chunk.get("title", "Untitled")
            author = chunk.get("author", "Unknown")
            source = chunk.get("source", "unknown")
            tags = chunk.get("tags", [])
            content = chunk.get("content", "")
            chunk_index = chunk.get("chunk_index", 0)
            total_chunks = chunk.get("total_chunks", 1)
            added_date = chunk.get("added_date", "")

            # Content snippet (first 300 chars)
            snippet = content[:300] + "..." if len(content) > 300 else content

            # Task 1.4: Extract knowledge card
            knowledge_card = _format_knowledge_card(chunk)

            # Task 1.5: Extract cluster info
            source_info = _format_source_info(chunk)

            # Task 1.6: Extract URLs
            urls = _format_urls(chunk)

            # Task 1.7: Track cluster for distribution calculation
            cluster_ids = chunk.get("cluster_id", [])
            if cluster_ids:
                primary_cluster = (
                    cluster_ids[0] if isinstance(cluster_ids, list) else cluster_ids
                )
                cluster_counts[primary_cluster] = (
                    cluster_counts.get(primary_cluster, 0) + 1
                )

            formatted_chunk = {
                "chunk_id": chunk_id,
                "title": title,
                "author": author,
                "source": source,
                "tags": tags,
                "snippet": snippet,
                "chunk_info": f"{chunk_index + 1}/{total_chunks}",
                "added_date": added_date,
                "knowledge_card": knowledge_card,
                "source": source_info,
                **urls,  # Unpack URL fields
            }

            recent_chunks.append(formatted_chunk)

        # Task 1.7: Calculate cluster distribution with names
        cluster_distribution = {}
        for cluster_id, count in cluster_counts.items():
            if cluster_id == "noise":
                cluster_distribution[cluster_id] = {
                    "name": "Outliers / Noise",
                    "count": count,
                }
            else:
                # Fetch cluster metadata
                try:
                    cluster_metadata = firestore_client.get_cluster_by_id(cluster_id)
                    cluster_name = (
                        cluster_metadata.get("name", f"Cluster {cluster_id}")
                        if cluster_metadata
                        else f"Cluster {cluster_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch cluster name for {cluster_id}: {e}"
                    )
                    cluster_name = f"Cluster {cluster_id}"

                cluster_distribution[cluster_id] = {
                    "name": cluster_name,
                    "count": count,
                }

        # Task 1.8: Combine chunks and activity summary into unified response
        response = {
            "period": period,
            "recent_chunks": recent_chunks,
            "activity_summary": activity_summary,
            "cluster_distribution": cluster_distribution,
        }

        logger.info(
            f"Successfully retrieved recent activity: {len(recent_chunks)} chunks, {len(cluster_distribution)} clusters"
        )
        return response

    except Exception as e:
        logger.error(f"Error getting recent activity: {e}")
        raise RuntimeError(f"Failed to retrieve recent activity: {str(e)}")


def search_kb(
    query: str, filters: Optional[Dict[str, Any]] = None, limit: int = 10
) -> Dict[str, Any]:
    """
    Unified knowledge base search with flexible filtering options.

    Story 4.1: Consolidates 6 separate search tools into one unified interface.
    Story 3.10: Returns Knowledge Cards by default for faster comprehension.
    Use get_chunk() for full content when quotes or detailed context is needed.

    Args:
        query: Natural language search query
        filters: Optional dict with filter options:
            - cluster_id (str): Scope search to specific cluster
            - tags (list): Filter by tags
            - author (str): Filter by author name
            - source (str): Filter by source
            - date_range (dict): {start: "YYYY-MM-DD", end: "YYYY-MM-DD"}
            - period (str): Relative time ("yesterday", "last_week", etc.)
            - include_content (bool): Include full_content and snippet (default False)
        limit: Maximum number of results (default 10)

    Returns:
        Dictionary with results. Each result includes knowledge_card and detail_hint.
        Use get_chunk(chunk_id) to retrieve full content when needed.
    """
    try:
        logger.info(
            f"Unified search for query: '{query}' with filters: {filters} (limit: {limit})"
        )

        # Parse filters
        filters = filters or {}
        cluster_id = filters.get("cluster_id")
        tags = filters.get("tags")
        author = filters.get("author")
        source = filters.get("source")
        date_range = filters.get("date_range")
        period = filters.get("period")
        # Story 3.10: Default to cards-only (include_content=False)
        include_content = filters.get("include_content", False)

        # Validate conflicting filters
        if date_range and period:
            return {
                "query": query,
                "result_count": 0,
                "error": "Cannot specify both date_range and period filters",
                "results": [],
            }

        # Route to appropriate backend

        # 1. Cluster-scoped search
        if cluster_id:
            logger.info(f"Routing to cluster-scoped search (cluster: {cluster_id})")

            # Verify cluster exists
            cluster = firestore_client.get_cluster_by_id(cluster_id)
            if not cluster:
                return {
                    "query": query,
                    "filters": filters,
                    "result_count": 0,
                    "error": f"Cluster not found: {cluster_id}",
                    "results": [],
                }

            # Generate embedding for query
            query_embedding = embeddings.generate_query_embedding(query)

            # Execute cluster-scoped vector search
            chunks = firestore_client.search_within_cluster(
                cluster_id=cluster_id, embedding_vector=query_embedding, limit=limit
            )

            # Story 3.10: Use unified formatter with include_content
            results = [
                _format_search_result(chunk, rank, include_content)
                for rank, chunk in enumerate(chunks, 1)
            ]

            return {
                "query": query,
                "filters": filters,
                "result_count": len(results),
                "limit": limit,
                "cluster_name": cluster.get("name", f"Cluster {cluster_id}"),
                "results": results,
            }

        # 2. Date range filtering
        if date_range:
            logger.info("Routing to date range search")
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            if not start_date or not end_date:
                return {
                    "query": query,
                    "filters": filters,
                    "result_count": 0,
                    "error": "date_range requires both start and end dates",
                    "results": [],
                }

            # Query with date range
            chunks = firestore_client.query_by_date_range(
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                tags=tags,
                author=author,
                source=source,
            )

            # Story 3.10: Use unified formatter with include_content
            results = [
                _format_search_result(chunk, rank, include_content)
                for rank, chunk in enumerate(chunks, 1)
            ]

            return {
                "query": query,
                "filters": filters,
                "result_count": len(results),
                "limit": limit,
                "results": results,
            }

        # 3. Relative time filtering
        if period:
            logger.info(f"Routing to relative time search (period: {period})")

            # Query with relative time
            chunks = firestore_client.query_by_relative_time(
                period=period, limit=limit, tags=tags, author=author, source=source
            )

            # Story 3.10: Use unified formatter with include_content
            results = [
                _format_search_result(chunk, rank, include_content)
                for rank, chunk in enumerate(chunks, 1)
            ]

            return {
                "query": query,
                "filters": filters,
                "result_count": len(results),
                "limit": limit,
                "results": results,
            }

        # 4. Default: Semantic search with optional metadata filters
        logger.info("Routing to semantic search with metadata filters")

        # Generate embedding for query
        query_embedding = embeddings.generate_query_embedding(query)

        # Execute vector search with filters
        chunks = firestore_client.find_nearest(
            embedding_vector=query_embedding,
            limit=limit,
            filters={"tags": tags, "author": author, "source": source}
            if (tags or author or source)
            else None,
        )

        # Story 3.10: Use unified formatter with include_content
        results = [
            _format_search_result(chunk, rank, include_content)
            for rank, chunk in enumerate(chunks, 1)
        ]

        return {
            "query": query,
            "filters": filters,
            "result_count": len(results),
            "limit": limit,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Unified search failed: {e}")
        return {
            "query": query,
            "filters": filters,
            "result_count": 0,
            "error": str(e),
            "results": [],
        }


def search_semantic(
    query: str,
    limit: int = 10,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Semantic search using query embedding and vector similarity.

    Args:
        query: Natural language query text
        limit: Maximum number of results (default 10)
        tags: Optional tag filter
        author: Optional author filter
        source: Optional source filter

    Returns:
        Dictionary with results list and metadata
    """
    try:
        logger.info(f"Semantic search for query: '{query}' (limit: {limit})")

        # Generate embedding for query
        logger.info("Generating query embedding...")
        query_embedding = embeddings.generate_query_embedding(query)

        # Execute vector search
        logger.info("Executing vector search...")
        chunks = firestore_client.find_nearest(
            embedding_vector=query_embedding,
            limit=limit,
            filters={"tags": tags, "author": author, "source": source}
            if (tags or author or source)
            else None,
        )

        # Format results
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get("id") or chunk.get("chunk_id", "unknown")
            title = chunk.get("title", "Untitled")
            author_name = chunk.get("author", "Unknown")
            source_name = chunk.get("source", "unknown")
            tags_list = chunk.get("tags", [])
            content = chunk.get("content", "")
            chunk_index = chunk.get("chunk_index", 0)
            total_chunks = chunk.get("total_chunks", 1)

            # Content snippet (first 500 chars)
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract knowledge card, cluster info, and URLs
            knowledge_card = _format_knowledge_card(chunk)
            source_info = _format_source_info(chunk)
            urls = _format_urls(chunk)

            result = {
                "rank": rank,
                "chunk_id": chunk_id,
                "title": title,
                "author": author_name,
                "source": source_name,
                "tags": tags_list,
                "chunk_info": f"{chunk_index + 1}/{total_chunks}",
                "snippet": snippet,
                "full_content": content,
                "knowledge_card": knowledge_card,
                "source": source_info,
                **urls,  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} results for query")

        return {
            "query": query,
            "result_count": len(results),
            "limit": limit,
            "filters": {"tags": tags, "author": author, "source": source}
            if (tags or author or source)
            else None,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return {"query": query, "result_count": 0, "error": str(e), "results": []}


def search_by_metadata(
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search chunks by metadata filters only (no semantic search).

    Args:
        tags: Filter by tags (array-contains-any)
        author: Filter by exact author name
        source: Filter by exact source
        limit: Maximum number of results (default 20)

    Returns:
        Dictionary with results list and metadata
    """
    try:
        logger.info(f"Metadata search: tags={tags}, author={author}, source={source}")

        if not (tags or author or source):
            return {
                "error": "At least one filter (tags, author, or source) is required",
                "result_count": 0,
                "results": [],
            }

        # Query Firestore
        chunks = firestore_client.query_by_metadata(
            tags=tags, author=author, source=source, limit=limit
        )

        # Format results
        results = []
        for chunk in chunks:
            chunk_id = chunk.get("id") or chunk.get("chunk_id", "unknown")
            title = chunk.get("title", "Untitled")
            author_name = chunk.get("author", "Unknown")
            source_name = chunk.get("source", "unknown")
            tags_list = chunk.get("tags", [])
            content = chunk.get("content", "")
            chunk_index = chunk.get("chunk_index", 0)
            total_chunks = chunk.get("total_chunks", 1)

            # Content snippet
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract knowledge card, cluster info, and URLs
            knowledge_card = _format_knowledge_card(chunk)
            source_info = _format_source_info(chunk)
            urls = _format_urls(chunk)

            result = {
                "chunk_id": chunk_id,
                "title": title,
                "author": author_name,
                "source": source_name,
                "tags": tags_list,
                "chunk_info": f"{chunk_index + 1}/{total_chunks}",
                "snippet": snippet,
                "full_content": content,
                "knowledge_card": knowledge_card,
                "source": source_info,
                **urls,  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} results matching metadata filters")

        return {
            "result_count": len(results),
            "filters": {"tags": tags, "author": author, "source": source},
            "limit": limit,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Metadata search failed: {e}")
        return {"result_count": 0, "error": str(e), "results": []}


def get_related_chunks(chunk_id: str, limit: int = 5) -> Dict[str, Any]:
    """
    Find chunks similar to a given chunk using vector similarity.

    Args:
        chunk_id: Source chunk ID
        limit: Maximum number of related chunks (default 5)

    Returns:
        Dictionary with related chunks and source chunk info
    """
    try:
        logger.info(f"Finding chunks related to {chunk_id} (limit: {limit})")

        # Fetch source chunk
        source_chunk = firestore_client.get_chunk_by_id(chunk_id)

        if not source_chunk:
            return {
                "error": f"Chunk not found: {chunk_id}",
                "result_count": 0,
                "results": [],
            }

        # Get embedding from source chunk
        embedding = source_chunk.get("embedding")

        if not embedding:
            return {
                "error": f"Chunk {chunk_id} has no embedding vector",
                "result_count": 0,
                "results": [],
            }

        # Convert Firestore Vector to list if needed
        if hasattr(embedding, "to_map_value"):
            # It's a Firestore Vector object
            embedding_vector = list(embedding.to_map_value()["value"])
        else:
            embedding_vector = list(embedding)

        logger.info(f"Source chunk embedding: {len(embedding_vector)} dimensions")

        # Find similar chunks (limit + 1 to account for source chunk)
        similar_chunks = firestore_client.find_nearest(
            embedding_vector=embedding_vector, limit=limit + 1
        )

        # Filter out the source chunk
        related_chunks = [c for c in similar_chunks if c.get("id") != chunk_id][:limit]

        # Format results
        results = []
        for chunk in related_chunks:
            related_id = chunk.get("id") or chunk.get("chunk_id", "unknown")
            title = chunk.get("title", "Untitled")
            author = chunk.get("author", "Unknown")
            source = chunk.get("source", "unknown")
            content = chunk.get("content", "")
            chunk_index = chunk.get("chunk_index", 0)
            total_chunks = chunk.get("total_chunks", 1)

            # Content snippet
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract knowledge card, cluster info, and URLs
            knowledge_card = _format_knowledge_card(chunk)
            source_info = _format_source_info(chunk)
            urls = _format_urls(chunk)

            result = {
                "chunk_id": related_id,
                "title": title,
                "author": author,
                "source": source,
                "chunk_info": f"{chunk_index + 1}/{total_chunks}",
                "snippet": snippet,
                "full_content": content,
                "knowledge_card": knowledge_card,
                "source": source_info,
                **urls,  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} related chunks")

        return {
            "source_chunk_id": chunk_id,
            "source_title": source_chunk.get("title", "Untitled"),
            "result_count": len(results),
            "limit": limit,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Get related chunks failed: {e}")
        return {
            "source_chunk_id": chunk_id,
            "result_count": 0,
            "error": str(e),
            "results": [],
        }


def get_stats() -> Dict[str, Any]:
    """
    Get statistics about the knowledge base.

    Returns:
        Dictionary with counts and unique values
    """
    try:
        logger.info("Collecting knowledge base statistics...")

        stats = firestore_client.get_stats()

        logger.info(f"Stats collected: {stats.get('total_chunks', 0)} chunks")

        return stats

    except Exception as e:
        logger.error(f"Get stats failed: {e}")
        return {"error": str(e), "total_chunks": 0, "total_documents": 0}


def search_by_date_range(
    start_date: str,
    end_date: str,
    limit: int = 20,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query chunks by date range (created_at timestamp).

    Args:
        start_date: Start date in ISO format (YYYY-MM-DD)
        end_date: End date in ISO format (YYYY-MM-DD)
        limit: Maximum results (default 20)
        tags: Optional tag filter
        author: Optional author filter
        source: Optional source filter

    Returns:
        Dictionary with results list and metadata
    """
    try:
        logger.info(f"Date range search: {start_date} to {end_date} (limit: {limit})")

        chunks = firestore_client.query_by_date_range(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            tags=tags,
            author=author,
            source=source,
        )

        # Format results
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get("id") or chunk.get("chunk_id", "unknown")
            title = chunk.get("title", "Untitled")
            author_name = chunk.get("author", "Unknown")
            source_name = chunk.get("source", "unknown")
            tags_list = chunk.get("tags", [])
            content = chunk.get("content", "")
            chunk_index = chunk.get("chunk_index", 0)
            total_chunks = chunk.get("total_chunks", 1)

            # Content snippet (first 500 chars)
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract URLs (Story 2.7)
            urls = _format_urls(chunk)

            result = {
                "rank": rank,
                "chunk_id": chunk_id,
                "title": title,
                "author": author_name,
                "source": source_name,
                "tags": tags_list,
                "chunk_info": f"{chunk_index + 1}/{total_chunks}",
                "snippet": snippet,
                "full_content": content,
                **urls,  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} chunks in date range")

        return {
            "start_date": start_date,
            "end_date": end_date,
            "result_count": len(results),
            "limit": limit,
            "filters": {"tags": tags, "author": author, "source": source}
            if (tags or author or source)
            else None,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Date range search failed: {e}")
        return {
            "start_date": start_date,
            "end_date": end_date,
            "result_count": 0,
            "error": str(e),
            "results": [],
        }


def search_by_relative_time(
    period: str,
    limit: int = 20,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query chunks using relative time periods.

    Args:
        period: Time period ("yesterday", "last_3_days", "last_week", "last_month")
        limit: Maximum results (default 20)
        tags: Optional tag filter
        author: Optional author filter
        source: Optional source filter

    Returns:
        Dictionary with results list and metadata
    """
    try:
        logger.info(f"Relative time search: {period} (limit: {limit})")

        chunks = firestore_client.query_by_relative_time(
            period=period, limit=limit, tags=tags, author=author, source=source
        )

        # Format results
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get("id") or chunk.get("chunk_id", "unknown")
            title = chunk.get("title", "Untitled")
            author_name = chunk.get("author", "Unknown")
            source_name = chunk.get("source", "unknown")
            tags_list = chunk.get("tags", [])
            content = chunk.get("content", "")
            chunk_index = chunk.get("chunk_index", 0)
            total_chunks = chunk.get("total_chunks", 1)

            # Content snippet (first 500 chars)
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract URLs (Story 2.7)
            urls = _format_urls(chunk)

            result = {
                "rank": rank,
                "chunk_id": chunk_id,
                "title": title,
                "author": author_name,
                "source": source_name,
                "tags": tags_list,
                "chunk_info": f"{chunk_index + 1}/{total_chunks}",
                "snippet": snippet,
                "full_content": content,
                **urls,  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} chunks for period '{period}'")

        return {
            "period": period,
            "result_count": len(results),
            "limit": limit,
            "filters": {"tags": tags, "author": author, "source": source}
            if (tags or author or source)
            else None,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Relative time search failed: {e}")
        return {"period": period, "result_count": 0, "error": str(e), "results": []}


def get_reading_activity(period: str = "last_7_days") -> Dict[str, Any]:
    """
    Get reading activity summary and statistics.

    Args:
        period: Time period ("today", "yesterday", "last_3_days", "last_7_days", "last_30_days", "last_month")

    Returns:
        Dictionary with activity stats
    """
    try:
        logger.info(f"Collecting reading activity for {period}...")

        activity = firestore_client.get_activity_summary(period=period)

        logger.info(
            f"Activity collected: {activity.get('total_chunks_added', 0)} chunks added"
        )

        return activity

    except Exception as e:
        logger.error(f"Get reading activity failed: {e}")
        return {
            "error": str(e),
            "period": period,
            "total_chunks_added": 0,
            "days_with_activity": 0,
            "chunks_by_day": {},
            "top_sources": [],
            "top_authors": [],
        }


def get_recently_added(limit: int = 10, days: int = 7) -> Dict[str, Any]:
    """
    Get most recently added chunks.

    Args:
        limit: Maximum chunks to return (default 10)
        days: Look back this many days (default 7)

    Returns:
        Dictionary with results list and metadata
    """
    try:
        logger.info(f"Getting {limit} recently added chunks from last {days} days...")

        chunks = firestore_client.get_recently_added(limit=limit, days=days)

        # Format results
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get("id") or chunk.get("chunk_id", "unknown")
            title = chunk.get("title", "Untitled")
            author_name = chunk.get("author", "Unknown")
            source_name = chunk.get("source", "unknown")
            tags_list = chunk.get("tags", [])
            content = chunk.get("content", "")
            chunk_index = chunk.get("chunk_index", 0)
            total_chunks = chunk.get("total_chunks", 1)

            # Content snippet (first 500 chars)
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract URLs (Story 2.7)
            urls = _format_urls(chunk)

            result = {
                "rank": rank,
                "chunk_id": chunk_id,
                "title": title,
                "author": author_name,
                "source": source_name,
                "tags": tags_list,
                "chunk_info": f"{chunk_index + 1}/{total_chunks}",
                "snippet": snippet,
                "full_content": content,
                **urls,  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Retrieved {len(results)} recently added chunks")

        return {
            "result_count": len(results),
            "limit": limit,
            "days": days,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Get recently added failed: {e}")
        return {"result_count": 0, "error": str(e), "results": []}


def get_knowledge_card(chunk_id: str) -> Dict[str, Any]:
    """
    Get knowledge card (AI summary and takeaways) for a specific chunk.

    Args:
        chunk_id: Chunk ID to fetch knowledge card for

    Returns:
        Dictionary with knowledge card details or error
    """
    try:
        logger.info(f"Fetching knowledge card for chunk {chunk_id}")

        # Fetch chunk from Firestore
        chunk = firestore_client.get_chunk_by_id(chunk_id)

        if not chunk:
            return {"error": f"Chunk not found: {chunk_id}", "chunk_id": chunk_id}

        # Extract knowledge card
        knowledge_card = chunk.get("knowledge_card")

        if not knowledge_card:
            return {
                "error": f"Knowledge card not available for chunk {chunk_id}",
                "chunk_id": chunk_id,
                "title": chunk.get("title", "Untitled"),
                "source": chunk.get("source", "unknown"),
            }

        logger.info(f"Retrieved knowledge card for {chunk_id}")

        # Extract URLs (Story 2.7)
        urls = _format_urls(chunk)

        return {
            "chunk_id": chunk_id,
            "title": chunk.get("title", "Untitled"),
            "author": chunk.get("author", "Unknown"),
            "source": chunk.get("source", "unknown"),
            "knowledge_card": {
                "summary": knowledge_card.get("summary", ""),
                "takeaways": knowledge_card.get("takeaways", []),
            },
            **urls,  # Story 2.7: Include URL fields
        }

    except Exception as e:
        logger.error(f"Get knowledge card failed: {e}")
        return {"error": str(e), "chunk_id": chunk_id}


def search_knowledge_cards(query: str, limit: int = 10) -> Dict[str, Any]:
    """
    Semantic search across knowledge card summaries only (not full content).

    Args:
        query: Natural language search query
        limit: Maximum number of results (default 10)

    Returns:
        Dictionary with knowledge card search results
    """
    try:
        logger.info(f"Searching knowledge cards for query: '{query}' (limit: {limit})")

        # Generate embedding for query
        query_embedding = embeddings.generate_query_embedding(query)

        # Execute vector search
        chunks = firestore_client.find_nearest(
            embedding_vector=query_embedding, limit=limit
        )

        # Format results - return only knowledge card summaries
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get("id") or chunk.get("chunk_id", "unknown")
            title = chunk.get("title", "Untitled")
            author = chunk.get("author", "Unknown")
            source = chunk.get("source", "unknown")

            # Extract knowledge card
            knowledge_card = chunk.get("knowledge_card")

            # Extract URLs (Story 2.7)
            urls = _format_urls(chunk)

            result = {
                "rank": rank,
                "chunk_id": chunk_id,
                "title": title,
                "author": author,
                "source": source,
                "knowledge_card": {
                    "summary": knowledge_card.get("summary", "")
                    if knowledge_card
                    else "Knowledge card not available",
                    "takeaways": knowledge_card.get("takeaways", [])
                    if knowledge_card
                    else [],
                },
                **urls,  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} knowledge card results")

        return {
            "query": query,
            "result_count": len(results),
            "limit": limit,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Search knowledge cards failed: {e}")
        return {"query": query, "result_count": 0, "error": str(e), "results": []}


# ============================================================================
# Reading Recommendations (Story 3.5)
# ============================================================================


def _get_reading_recommendations(
    days: int = 14,
    limit: int = 10,
    user_id: str = "default",
    hot_sites: Optional[str] = None,
    mode: str = "balanced",
    include_seen: bool = False,
    predictable: bool = False,
    tavily_days: Optional[int] = None,
    topic: Optional[str] = None,
    problems: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Internal: Get AI-powered reading recommendations based on KB content.

    Called by the async recommendations job via Cloud Tasks.
    Not exposed as a public MCP tool.

    Story 3.5: AI-Powered Reading Recommendations
    Story 3.8: Enhanced Recommendation Ranking
    Story 3.9: Parameterized Recommendations
    Story 4.4: Removed cluster dependency
    Story 7.1: Made internal, called via Cloud Tasks
    Story 7.2: Simplified interface with topic override
    Story 11.3: Problem-driven recommendations with graph enhancement

    Args:
        days: Lookback period for recent reads (default 14)
        limit: Maximum recommendations to return (default 10)
        user_id: User identifier for shown tracking (default "default")
        hot_sites: Optional source category: "tech", "tech_de", "ai", "devops", "business", "all"
        mode: Discovery mode for Epic 11: "deepen" | "explore" | "balanced"
              Legacy modes ("fresh", "deep", "surprise_me") mapped to balanced
        include_seen: Include previously shown recommendations (default False)
        predictable: Disable query variation for reproducible results (default False)
        tavily_days: Override tavily search days (default: from mode config)
        topic: Optional topic override for query generation (deprecated, use problems)
        problems: Optional list of problem IDs to focus recommendations on

    Returns:
        Dictionary with recommendations and metadata.
    """
    start_time = time.time()
    scope = "both"  # Story 4.4: Fixed scope, no longer configurable

    try:
        logger.info(
            f"Generating reading recommendations: days={days}, limit={limit}, "
            f"mode={mode}, hot_sites={hot_sites}, problems={problems}"
        )

        # Story 11.3: Map modes - Epic 11 modes take precedence
        epic11_modes = ["deepen", "explore", "balanced"]
        legacy_modes = ["fresh", "deep", "surprise_me"]

        if mode in legacy_modes:
            # Map legacy modes to balanced for backwards compatibility
            logger.info(f"Mapping legacy mode '{mode}' to 'balanced'")
            mode = "balanced"
        elif mode not in epic11_modes:
            return {
                "error": f"Invalid mode: {mode}. Must be one of {epic11_modes}",
                "recommendations": [],
            }

        # Import recommendation modules
        import recommendation_filter
        import recommendation_problems
        import recommendation_queries
        import tavily_client

        # Story 3.9: Get mode configuration
        mode_config = recommendation_filter.get_mode_config(mode)
        logger.info(f"Using mode '{mode}': {mode_config.get('description', '')}")

        # Build filters_applied for response
        filters_applied = {"include_seen": include_seen, "predictable": predictable}

        # Resolve hot sites domain filtering
        hot_sites_domains = []
        if hot_sites:
            hot_sites_domains = firestore_client.get_hot_sites_domains(hot_sites)
            filters_applied["hot_sites"] = hot_sites
            filters_applied["hot_sites_domain_count"] = len(hot_sites_domains)
            logger.info(
                f"Hot sites filter '{hot_sites}': {len(hot_sites_domains)} domains"
            )

        # Step 1: Get recommendation config (domain whitelist)
        config = firestore_client.get_recommendation_config()
        quality_domains = config.get("quality_domains", [])
        excluded_domains = config.get("excluded_domains", [])

        # Story 3.9: Use mode-specific weights (override stored config)
        weights = mode_config.get(
            "weights", recommendation_filter.DEFAULT_RANKING_WEIGHTS
        )

        # Get base ranking settings
        ranking_config = firestore_client.get_ranking_config()
        settings = ranking_config.get("settings", {})

        recency_settings = settings.get("recency", {})
        diversity_settings = settings.get("diversity", {})

        half_life_days = recency_settings.get(
            "half_life_days", recommendation_filter.DEFAULT_RECENCY_HALF_LIFE_DAYS
        )
        max_age_days = recency_settings.get(
            "max_age_days", recommendation_filter.DEFAULT_MAX_AGE_DAYS
        )

        # Story 7.2: Use passed tavily_days or fall back to mode config
        if tavily_days is None:
            tavily_days = mode_config.get(
                "tavily_days", recency_settings.get("tavily_days_filter", 180)
            )

        # Story 3.9: Use mode-specific temperature
        temperature = mode_config.get(
            "temperature", diversity_settings.get("stochastic_temperature", 0.3)
        )

        # Story 3.9: Use mode-specific slot configuration
        slot_config = mode_config.get("slots", settings.get("slots", {}))

        # Story 3.9: Use mode-specific min_depth_score
        min_depth_score = mode_config.get("min_depth_score", 3)

        novelty_bonus = diversity_settings.get(
            "novelty_bonus", recommendation_filter.DEFAULT_NOVELTY_BONUS
        )
        domain_penalty = diversity_settings.get(
            "domain_duplicate_penalty",
            recommendation_filter.DEFAULT_DOMAIN_DUPLICATE_PENALTY,
        )

        # Story 3.9 AC: Get previously shown URLs (unless include_seen=True)
        shown_ttl = diversity_settings.get("shown_ttl_days", 7)
        if include_seen:
            shown_urls = []
            logger.info("include_seen=True: Not excluding previously shown URLs")
        else:
            shown_urls = firestore_client.get_shown_urls(
                user_id=user_id, ttl_days=shown_ttl
            )
            logger.info(f"Excluding {len(shown_urls)} previously shown URLs")

        # Step 2: Get KB credibility signals (all known authors and source domains)
        kb_credibility = firestore_client.get_kb_credibility_signals()
        known_authors = kb_credibility.get("authors", [])
        known_domains = kb_credibility.get("domains", [])
        logger.info(
            f"KB credibility: {len(known_authors)} authors, {len(known_domains)} domains"
        )

        # Story 11.3: Problem-driven query generation
        # Falls back to topic or legacy queries if no problems
        use_variation = not predictable
        problem_evidence = []  # For graph-enhanced filtering

        # Try problem-based queries first (Epic 11)
        problem_queries = recommendation_problems.generate_problem_queries(
            problems=problems,
            mode=mode,
            max_queries=8,
        )

        if problem_queries:
            logger.info(f"Using {len(problem_queries)} problem-based queries")
            queries = problem_queries
            filters_applied["query_source"] = "problems"
            filters_applied["problems_used"] = list(set(q.get("problem_id") for q in problem_queries))

            # Collect evidence for graph filtering
            for pid in filters_applied["problems_used"]:
                evidence = firestore_client.get_problem_evidence_sources(pid)
                problem_evidence.extend(evidence)
            logger.info(f"Collected {len(problem_evidence)} evidence sources for graph filtering")

        elif topic:
            # Topic override: generate simple topic-based queries (deprecated)
            logger.info(f"Using topic override: {topic}")
            queries = [
                {"query": f"{topic} best practices 2025", "source": "topic_override"},
                {"query": f"{topic} latest developments", "source": "topic_override"},
                {"query": f"advanced {topic} techniques", "source": "topic_override"},
            ]
            filters_applied["topic"] = topic
            filters_applied["query_source"] = "topic"
        else:
            # Fallback to legacy tag/source-based queries
            queries = recommendation_queries.generate_search_queries(
                days=days,
                max_queries=8,
                use_variation=use_variation,
            )
            filters_applied["query_source"] = "legacy"

        if not queries:
            return {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "processing_time_seconds": round(time.time() - start_time, 1),
                "scope": scope,
                "mode": mode,
                "filters_applied": filters_applied,
                "days_analyzed": days,
                "error": "No queries generated - insufficient KB content",
                "queries_used": [],
                "recommendations": [],
                "filtered_out": {},
            }

        query_strings = [q.get("query", str(q)) for q in queries]
        logger.info(f"Generated {len(queries)} search queries")

        # Step 4: Search Tavily
        all_results = []
        all_contexts = []
        query_source = filters_applied.get("query_source", "legacy")

        for query_dict in queries:
            # Story 11.3: Use appropriate formatter based on query source
            if query_source == "problems":
                query_str = recommendation_problems.format_query_for_tavily(query_dict)
            else:
                query_str = recommendation_queries.format_query_for_tavily(query_dict)

            try:
                # Story 3.9: Determine include_domains for Tavily
                include_domains = None
                if hot_sites_domains:
                    include_domains = hot_sites_domains

                search_result = tavily_client.search(
                    query=query_str,
                    exclude_domains=excluded_domains if excluded_domains else None,
                    include_domains=include_domains,  # Story 3.9: hot sites filtering
                    days=tavily_days,
                    max_results=5,
                    search_depth="advanced",
                )

                for result in search_result.get("results", []):
                    # Skip previously shown URLs (unless include_seen)
                    if not include_seen and result.get("url") in shown_urls:
                        logger.debug(f"Skipping previously shown: {result.get('url')}")
                        continue

                    # Calculate recency score
                    pub_date = recommendation_filter.parse_published_date(
                        result.get("published_date")
                    )
                    recency_score = recommendation_filter.calculate_recency_score(
                        pub_date, half_life_days, max_age_days
                    )

                    # Skip articles that are too old (recency_score = 0)
                    if recency_score == 0:
                        logger.debug(f"Skipping old article: {result.get('title')}")
                        continue

                    result["recency_score"] = recency_score
                    result["relevance_score"] = result.get("score", 0.5)

                    # Add query context for slot assignment
                    result["related_to"] = query_dict.get("context", {})

                    all_results.append(result)
                    all_contexts.append(query_dict)

            except Exception as e:
                logger.warning(
                    f"Tavily search failed for query '{query_str[:50]}...': {e}"
                )
                continue

        logger.info(
            f"Tavily returned {len(all_results)} total results (after shown/age filtering)"
        )

        if not all_results:
            return {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "processing_time_seconds": round(time.time() - start_time, 1),
                "scope": scope,
                "mode": mode,
                "filters_applied": filters_applied,
                "days_analyzed": days,
                "queries_used": query_strings,
                "recommendations": [],
                "filtered_out": {"no_results": True, "shown_excluded": len(shown_urls)},
                "ranking_config": {"weights": weights, "mode": mode},
            }

        # Step 5: Filter for quality and deduplicate
        # Story 11.4: Use evidence dedup + graph-enhanced filtering when we have problems
        problems_used = filters_applied.get("problems_used", [])
        if problem_evidence or problems_used:
            logger.info(
                f"Using evidence dedup + graph filtering with "
                f"{len(problem_evidence)} evidence sources, {len(problems_used)} problems"
            )
            filter_result = recommendation_filter.filter_recommendations_with_evidence_dedup(
                recommendations=all_results,
                query_contexts=all_contexts,
                problem_ids=problems_used,
                problem_evidence=problem_evidence,
                mode=mode,
                min_depth_score=min_depth_score,
                max_per_domain=diversity_settings.get("max_per_domain", 2),
                check_duplicates=True,
                known_authors=known_authors,
                known_sources=known_domains,
                trusted_sources=quality_domains,
            )
            graph_stats = filter_result.get("graph_stats", {})
            filters_applied["graph_stats"] = graph_stats

            # Story 11.4: Track evidence duplicates in stats
            already_evidence = filter_result.get("filtered_out", {}).get("already_evidence", 0)
            if already_evidence > 0:
                filters_applied["evidence_duplicates_filtered"] = already_evidence
        else:
            filter_result = recommendation_filter.filter_recommendations(
                recommendations=all_results,
                query_contexts=all_contexts,
                min_depth_score=min_depth_score,  # Story 3.9: mode-specific
                max_per_domain=diversity_settings.get("max_per_domain", 2),
                check_duplicates=True,
                known_authors=known_authors,
                known_sources=known_domains,
                trusted_sources=quality_domains,
            )

        filtered_recs = filter_result.get("recommendations", [])
        filtered_out = filter_result.get("filtered_out", {})

        # Calculate combined scores with multi-factor ranking
        domain_counts = {}
        for rec in filtered_recs:
            domain = rec.get("domain", "")

            # Calculate novelty bonus (never shown before)
            is_novel = rec.get("url") not in shown_urls
            rec_novelty = novelty_bonus if is_novel else 0.0

            # Calculate domain duplicate penalty
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            rec_penalty = (
                domain_penalty * (domain_counts[domain] - 1)
                if domain_counts[domain] > 1
                else 0.0
            )

            # Calculate combined score with mode-specific weights
            score_result = recommendation_filter.calculate_combined_score(
                rec, weights, novelty_bonus=rec_novelty, domain_penalty=rec_penalty
            )

            rec["combined_score"] = score_result["combined_score"]
            rec["final_score"] = score_result["final_score"]
            rec["score_breakdown"] = score_result["score_breakdown"]
            rec["ranking_adjustments"] = score_result["adjustments"]

        # Stochastic sampling for diversity (mode-specific temperature)
        sample_size = min(limit * 2, len(filtered_recs))
        sampled_recs = recommendation_filter.diversified_sample(
            filtered_recs,
            n=sample_size,
            temperature=temperature,
            score_key="final_score",
        )

        # Assign slots for variety (mode-specific slot config)
        slotted_recs = recommendation_filter.assign_slots(sampled_recs, slot_config)

        # Take final limit
        final_recs = slotted_recs[:limit]

        # Record shown recommendations (unless include_seen mode)
        if final_recs and not include_seen:
            record_result = firestore_client.record_shown_recommendations(
                user_id=user_id, recommendations=final_recs, ttl_days=shown_ttl
            )
            logger.info(
                f"Recorded {record_result.get('recorded_count', 0)} shown recommendations"
            )

        processing_time = round(time.time() - start_time, 1)
        logger.info(
            f"Recommendations complete: {len(final_recs)} recommendations "
            f"in {processing_time}s (mode={mode})"
        )

        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "processing_time_seconds": processing_time,
            "scope": scope,
            "mode": mode,
            "filters_applied": filters_applied,
            "days_analyzed": days,
            "queries_used": query_strings,
            "recommendations": final_recs,
            "filtered_out": filtered_out,
            "ranking_config": {
                "weights": weights,
                "mode": mode,
                "temperature": temperature,
                "tavily_days": tavily_days,
                "min_depth_score": min_depth_score,
                "slots": slot_config,
            },
        }

    except Exception as e:
        logger.error(f"Get reading recommendations failed: {e}")
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "processing_time_seconds": round(time.time() - start_time, 1),
            "scope": scope,
            "mode": mode,
            "error": str(e),
            "recommendations": [],
        }


def update_recommendation_domains(
    add_domains: Optional[List[str]] = None, remove_domains: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Update the domain whitelist for reading recommendations.

    Story 3.5: AI-Powered Reading Recommendations

    Args:
        add_domains: Domains to add to the quality whitelist
        remove_domains: Domains to remove from the whitelist

    Returns:
        Dictionary with:
        - success: Boolean
        - quality_domains: Updated list of whitelisted domains
        - excluded_domains: List of blocked domains
        - changes: Summary of changes made

    Example:
        >>> update_recommendation_domains(add_domains=["newsite.com"])
        {
            "success": true,
            "quality_domains": ["martinfowler.com", "newsite.com", ...],
            "changes": {"domains_added": ["newsite.com"]}
        }
    """
    try:
        logger.info(
            f"Updating recommendation domains: "
            f"+{len(add_domains or [])} -{len(remove_domains or [])}"
        )

        result = firestore_client.update_recommendation_config(
            add_domains=add_domains,
            remove_domains=remove_domains,
            updated_by="mcp_tool",
        )

        if result.get("success"):
            config = result.get("config", {})
            return {
                "success": True,
                "quality_domains": config.get("quality_domains", []),
                "excluded_domains": config.get("excluded_domains", []),
                "domain_count": len(config.get("quality_domains", [])),
                "changes": result.get("changes", {}),
            }
        else:
            return {"success": False, "error": result.get("error", "Unknown error")}

    except Exception as e:
        logger.error(f"Update recommendation domains failed: {e}")
        return {"success": False, "error": str(e)}


def get_recommendation_config() -> Dict[str, Any]:
    """
    Get current recommendation configuration including domain whitelist.

    Story 3.5: AI-Powered Reading Recommendations

    Returns:
        Dictionary with:
        - quality_domains: List of whitelisted domains
        - excluded_domains: List of blocked domains
        - domain_count: Number of whitelisted domains
        - last_updated: When config was last modified
    """
    try:
        logger.info("Getting recommendation config")

        config = firestore_client.get_recommendation_config()

        return {
            "quality_domains": config.get("quality_domains", []),
            "excluded_domains": config.get("excluded_domains", []),
            "domain_count": len(config.get("quality_domains", [])),
            "last_updated": str(config.get("last_updated", "")),
            "updated_by": config.get("updated_by", ""),
        }

    except Exception as e:
        logger.error(f"Get recommendation config failed: {e}")
        return {"error": str(e)}


# ============================================================================
# Story 3.8: Ranking Configuration Tools
# ============================================================================


def get_ranking_config() -> Dict[str, Any]:
    """
    Get current ranking configuration for recommendations.

    Story 3.8 AC#7: Configuration management

    Returns:
        Dictionary with:
        - weights: Factor weights (relevance, recency, depth, authority)
        - settings: Recency, diversity, and slot settings
        - weights_last_updated: When weights were last modified
        - settings_last_updated: When settings were last modified
    """
    try:
        logger.info("Getting ranking config")

        config = firestore_client.get_ranking_config()

        return {
            "weights": config.get("weights", {}),
            "settings": config.get("settings", {}),
            "weights_last_updated": config.get("weights_last_updated", ""),
            "settings_last_updated": config.get("settings_last_updated", ""),
            "error": config.get("error"),
        }

    except Exception as e:
        logger.error(f"Get ranking config failed: {e}")
        return {"error": str(e)}


# ============================================================================
# Story 3.9: Hot Sites Configuration Tools
# ============================================================================


def get_hot_sites_config() -> Dict[str, Any]:
    """
    Get hot sites configuration including all categories and their domains.

    Story 3.9 AC#4: MCP tool to view categories

    Returns:
        Dictionary with:
        - categories: Dict mapping category name to domain list
        - category_summary: List of category summaries with counts
        - total_domains: Total unique domains across all categories
    """
    try:
        logger.info("Getting hot sites config")

        config = firestore_client.get_hot_sites_config()

        categories = config.get("categories", {})
        descriptions = config.get("descriptions", {})

        # Build category summary
        category_summary = []
        all_domains = set()
        for cat_name, domains in categories.items():
            all_domains.update(domains)
            category_summary.append(
                {
                    "category": cat_name,
                    "description": descriptions.get(cat_name, ""),
                    "domain_count": len(domains),
                }
            )

        # Sort by domain count descending
        category_summary.sort(key=lambda x: x["domain_count"], reverse=True)

        return {
            "categories": categories,
            "descriptions": descriptions,
            "category_summary": category_summary,
            "total_domains": len(all_domains),
            "last_updated": str(config.get("last_updated", "")),
            "updated_by": config.get("updated_by", ""),
        }

    except Exception as e:
        logger.error(f"Get hot sites config failed: {e}")
        return {"error": str(e)}


def update_hot_sites_config(
    category: str,
    add_domains: Optional[List[str]] = None,
    remove_domains: Optional[List[str]] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update hot sites configuration for a specific category.

    Story 3.9 AC#4: MCP tool to modify categories

    Args:
        category: Category name (tech, tech_de, ai, devops, business, or new)
        add_domains: Domains to add to the category
        remove_domains: Domains to remove from the category
        description: Optional new description for the category

    Returns:
        Dictionary with:
        - success: Boolean
        - category: Category that was updated
        - domains: Updated domain list
        - domain_count: Number of domains in category
        - changes: Summary of changes made

    Example:
        >>> update_hot_sites_config(category="ai", add_domains=["newaisite.com"])
        {
            "success": true,
            "category": "ai",
            "domains": ["anthropic.com", "newaisite.com", ...],
            "domain_count": 18,
            "changes": {"domains_added": ["newaisite.com"]}
        }
    """
    try:
        logger.info(
            f"Updating hot sites config for {category}: "
            f"+{len(add_domains or [])} -{len(remove_domains or [])}"
        )

        result = firestore_client.update_hot_sites_config(
            category=category,
            add_domains=add_domains,
            remove_domains=remove_domains,
            description=description,
            updated_by="mcp_tool",
        )

        return result

    except Exception as e:
        logger.error(f"Update hot sites config failed: {e}")
        return {"success": False, "category": category, "error": str(e)}


def update_ranking_config(
    weights: Optional[Dict[str, float]] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Update ranking configuration for recommendations.

    Story 3.8 AC#7: Configuration management

    Args:
        weights: Factor weights dict with keys: relevance, recency, depth, authority
                 Values must sum to 1.0
        settings: Settings dict with optional keys:
                  - recency: {half_life_days, max_age_days, tavily_days_filter}
                  - diversity: {shown_ttl_days, novelty_bonus, domain_duplicate_penalty, max_per_domain, stochastic_temperature}
                  - slots: {relevance_count, serendipity_count, stale_refresh_count, trending_count}

    Returns:
        Dictionary with:
        - success: Boolean
        - config: Updated configuration
        - changes: Summary of changes made
        - error: Error message if failed

    Example:
        >>> update_ranking_config(weights={"relevance": 0.6, "recency": 0.2, "depth": 0.1, "authority": 0.1})
        {
            "success": true,
            "config": {...},
            "changes": {"weights_updated": true}
        }
    """
    try:
        logger.info("Updating ranking config")

        result = firestore_client.update_ranking_config(
            weights=weights, settings=settings, updated_by="mcp_tool"
        )

        return result

    except Exception as e:
        logger.error(f"Update ranking config failed: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Story 4.5: Unified Configuration Tool
# ============================================================================


def configure_kb(
    action: str, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Unified configuration tool for kx-hub.

    Story 4.5: Consolidates 4 configuration tools into single entry point.
    Replaces: get_recommendation_config, update_recommendation_domains,
              get_ranking_config, update_ranking_config,
              get_hot_sites_config, update_hot_sites_config

    Args:
        action: Action to perform (show_all, show_ranking, show_domains,
                show_hot_sites, update_ranking, update_domains, update_hot_sites)
        params: Action-specific parameters (optional)

    Returns:
        Dictionary with action-specific results

    Actions:
        - show_all: Display all configuration (no params)
        - show_ranking: Show ranking weights and settings (no params)
        - show_domains: Show domain whitelist (no params)
        - show_hot_sites: Show hot sites categories (no params)
        - update_ranking: Update ranking weights/settings (params: {weights, settings})
        - update_domains: Modify domain whitelist (params: {add, remove})
        - update_hot_sites: Modify hot sites (params: {category, add, remove, description})

    Examples:
        >>> configure_kb(action="show_all")
        {
            "ranking": {...},
            "domains": {...},
            "hot_sites": {...}
        }

        >>> configure_kb(action="update_domains", params={"add": ["newsite.com"]})
        {
            "success": true,
            "quality_domains": [...],
            "changes": {"domains_added": ["newsite.com"]}
        }
    """
    try:
        logger.info(f"configure_kb: action={action}, params={params}")

        params = params or {}

        # Validate action
        valid_actions = [
            "show_all",
            "show_ranking",
            "show_domains",
            "show_hot_sites",
            "update_ranking",
            "update_domains",
            "update_hot_sites",
        ]

        if action not in valid_actions:
            return {
                "error": f"Invalid action: {action}",
                "valid_actions": valid_actions,
            }

        # Route to appropriate handler
        if action == "show_all":
            # Return all configuration
            ranking = get_ranking_config()
            domains = get_recommendation_config()
            hot_sites = get_hot_sites_config()

            return {
                "action": "show_all",
                "ranking": ranking,
                "domains": domains,
                "hot_sites": hot_sites,
            }

        elif action == "show_ranking":
            # Return ranking configuration
            return {"action": "show_ranking", **get_ranking_config()}

        elif action == "show_domains":
            # Return domain whitelist
            return {"action": "show_domains", **get_recommendation_config()}

        elif action == "show_hot_sites":
            # Return hot sites configuration
            return {"action": "show_hot_sites", **get_hot_sites_config()}

        elif action == "update_ranking":
            # Update ranking configuration
            weights = params.get("weights")
            settings = params.get("settings")

            if not weights and not settings:
                return {
                    "error": "update_ranking requires weights or settings in params",
                    "example": {
                        "action": "update_ranking",
                        "params": {
                            "weights": {
                                "relevance": 0.5,
                                "recency": 0.25,
                                "depth": 0.15,
                                "authority": 0.1,
                            }
                        },
                    },
                }

            result = update_ranking_config(weights=weights, settings=settings)
            return {"action": "update_ranking", **result}

        elif action == "update_domains":
            # Update domain whitelist
            add_domains = params.get("add")
            remove_domains = params.get("remove")

            if not add_domains and not remove_domains:
                return {
                    "error": "update_domains requires add or remove in params",
                    "example": {
                        "action": "update_domains",
                        "params": {"add": ["newsite.com"], "remove": ["oldsite.com"]},
                    },
                }

            result = update_recommendation_domains(
                add_domains=add_domains, remove_domains=remove_domains
            )
            return {"action": "update_domains", **result}

        elif action == "update_hot_sites":
            # Update hot sites configuration
            category = params.get("category")
            add_domains = params.get("add")
            remove_domains = params.get("remove")
            description = params.get("description")

            if not category:
                return {
                    "error": "update_hot_sites requires category in params",
                    "example": {
                        "action": "update_hot_sites",
                        "params": {"category": "ai", "add": ["newaisite.com"]},
                    },
                }

            result = update_hot_sites_config(
                category=category,
                add_domains=add_domains,
                remove_domains=remove_domains,
                description=description,
            )
            return {"action": "update_hot_sites", **result}

    except Exception as e:
        logger.error(f"configure_kb failed: {e}")
        return {"action": action, "error": str(e)}


# ============================================================================
# Story 4.3: Source and Relationship Tools
# ============================================================================


def list_sources(limit: int = 50) -> Dict[str, Any]:
    """
    List all sources (books, articles) with metadata.

    Args:
        limit: Maximum sources to return (default 50)

    Returns:
        Dictionary with list of sources
    """
    try:
        logger.info(f"Listing sources (limit={limit})")
        sources = firestore_client.list_sources(limit=limit)

        return {"source_count": len(sources), "limit": limit, "sources": sources}

    except Exception as e:
        logger.error(f"Failed to list sources: {e}")
        return {"source_count": 0, "error": str(e), "sources": []}


def get_source(source_id: str, include_relationships: bool = True) -> Dict[str, Any]:
    """
    Get source details with chunks and cross-source relationships.

    Args:
        source_id: Source document ID
        include_relationships: Include relationships to other sources (default True)

    Returns:
        Dictionary with source details, chunks, and relationships
    """
    try:
        logger.info(
            f"Getting source {source_id} (include_relationships={include_relationships})"
        )

        source = firestore_client.get_source_by_id(source_id)
        if not source:
            raise ValueError(f"Source not found: {source_id}")

        result = {
            "source_id": source_id,
            "title": source.get("title"),
            "author": source.get("author"),
            "type": source.get("type"),
            "chunk_count": source.get("chunk_count"),
            "tags": source.get("tags", []),
            "chunks": source.get("chunks", []),
        }

        if include_relationships:
            relationships = firestore_client.get_source_relationships(source_id)
            result["relationships"] = relationships
            result["relationship_count"] = len(relationships)

        logger.info(
            f"Retrieved source {source_id} with {result.get('chunk_count', 0)} chunks"
        )
        return result

    except ValueError as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to get source {source_id}: {e}")
        raise RuntimeError(f"Failed to retrieve source: {str(e)}")


def get_contradictions(limit: int = 10) -> Dict[str, Any]:
    """
    Find contradicting ideas across sources.

    Args:
        limit: Maximum contradictions to return (default 10)

    Returns:
        Dictionary with list of contradictions
    """
    try:
        logger.info(f"Finding contradictions (limit={limit})")
        contradictions = firestore_client.find_contradictions(limit=limit)

        return {
            "contradiction_count": len(contradictions),
            "limit": limit,
            "contradictions": contradictions,
        }

    except Exception as e:
        logger.error(f"Failed to find contradictions: {e}")
        return {"contradiction_count": 0, "error": str(e), "contradictions": []}


def search_within_source(source_id: str, query: str, limit: int = 10) -> Dict[str, Any]:
    """
    Semantic search restricted to a specific source.

    Args:
        source_id: Source ID to search within
        query: Natural language search query
        limit: Maximum results (default 10)

    Returns:
        Dictionary with search results from the source
    """
    try:
        logger.info(f"Searching within source {source_id} for: '{query}'")

        # Get source to verify it exists and get chunk IDs
        source = firestore_client.get_source_by_id(source_id)
        if not source:
            return {
                "error": f"Source not found: {source_id}",
                "source_id": source_id,
                "query": query,
                "result_count": 0,
                "results": [],
            }

        chunk_ids = [c["chunk_id"] for c in source.get("chunks", [])]
        if not chunk_ids:
            return {
                "source_id": source_id,
                "source_title": source.get("title"),
                "query": query,
                "result_count": 0,
                "results": [],
            }

        # Generate embedding and search
        query_embedding = embeddings.generate_query_embedding(query)

        # Search all chunks and filter by source
        all_results = firestore_client.find_nearest(
            embedding_vector=query_embedding,
            limit=limit * 3,  # Get more to filter
        )

        # Filter to only chunks from this source
        results = []
        for chunk in all_results:
            chunk_id = chunk.get("id") or chunk.get("chunk_id")
            if chunk_id in chunk_ids:
                results.append(
                    {
                        "rank": len(results) + 1,
                        "chunk_id": chunk_id,
                        "title": chunk.get("title"),
                        "author": chunk.get("author"),
                        "snippet": chunk.get("content", "")[:300] + "...",
                        "knowledge_card": _format_knowledge_card(chunk),
                    }
                )
                if len(results) >= limit:
                    break

        return {
            "source_id": source_id,
            "source_title": source.get("title"),
            "query": query,
            "result_count": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error(f"Search within source failed: {e}")
        return {
            "source_id": source_id,
            "query": query,
            "result_count": 0,
            "error": str(e),
            "results": [],
        }


# ==================== Async Recommendations (Epic 7) ====================

import json as json_module


def _enqueue_cloud_task(job_id: str, job_type: str, params: Dict[str, Any]) -> None:
    """
    Enqueue a job to Cloud Tasks for async execution.

    Epic 7: Uses Cloud Tasks instead of in-process threading to ensure
    jobs survive Cloud Run instance restarts.

    Args:
        job_id: Unique job identifier
        job_type: Type of job (e.g., "recommendations")
        params: Job parameters
    """
    from google.cloud import tasks_v2

    # Get configuration from environment
    project_id = os.environ.get("GCP_PROJECT", "kx-hub")
    location = os.environ.get("GCP_REGION", "europe-west1")
    queue_name = os.environ.get("CLOUD_TASKS_QUEUE", "async-jobs")
    service_url = os.environ.get("MCP_SERVER_URL", "")
    cloud_tasks_sa = os.environ.get(
        "CLOUD_TASKS_SA_EMAIL",
        f"cloud-tasks-invoker@{project_id}.iam.gserviceaccount.com",
    )

    if not service_url:
        # Fallback: construct from Cloud Run service name
        service_name = os.environ.get("K_SERVICE", "kx-hub-mcp")
        service_url = f"https://{service_name}-{project_id}.{location}.run.app"

    # Create Cloud Tasks client
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project_id, location, queue_name)

    # Build the task
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{service_url}/jobs/run",
            "headers": {"Content-Type": "application/json"},
            "body": json_module.dumps(
                {
                    "job_id": job_id,
                    "job_type": job_type,
                    "params": params,
                }
            ).encode(),
            "oidc_token": {
                "service_account_email": cloud_tasks_sa,
            },
        },
    }

    # Enqueue the task
    response = client.create_task(request={"parent": parent, "task": task})
    logger.info(f"Enqueued Cloud Task: {response.name} for job {job_id}")


def execute_recommendations_job(job_id: str, params: Dict[str, Any]) -> None:
    """
    Execute a recommendations job. Called by /jobs/run endpoint.

    Epic 7: This is the actual job execution, called synchronously by Cloud Tasks.
    Updates job status in Firestore throughout execution.

    Args:
        job_id: Job identifier
        params: Job parameters (days, limit, hot_sites, mode, include_seen, tavily_days, topic, problems)
    """
    try:
        # Mark as running
        firestore_client.update_async_job(job_id, status="running", progress=0.1)

        # Execute the actual recommendations logic
        # Story 11.3: Added problems parameter
        result = _get_reading_recommendations(
            days=params.get("days", 14),
            limit=params.get("limit", 10),
            user_id=params.get("user_id", "default"),
            hot_sites=params.get("hot_sites"),
            mode=params.get("mode", "balanced"),
            include_seen=params.get("include_seen", False),
            predictable=params.get("predictable", False),
            tavily_days=params.get("tavily_days"),
            topic=params.get("topic"),
            problems=params.get("problems"),
        )

        # Check for error in result
        if result.get("error"):
            firestore_client.update_async_job(
                job_id, status="failed", error=result["error"]
            )
        else:
            firestore_client.update_async_job(
                job_id, status="completed", progress=1.0, result=result
            )

    except Exception as e:
        logger.error(f"Recommendations job {job_id} failed: {e}")
        firestore_client.update_async_job(job_id, status="failed", error=str(e))


def recommendations(
    job_id: Optional[str] = None,
    topic: Optional[str] = None,
    problems: Optional[List[str]] = None,
    mode: str = "balanced",
) -> Dict[str, Any]:
    """
    Async recommendations: start a new job or poll for results.

    Story 7.1: Async Recommendations
    Story 7.2: Simplified interface with config-based defaults
    Story 11.3: Problem-driven recommendations with mode selection

    Usage:
    - recommendations() - Start job with defaults (all active problems, balanced mode)
    - recommendations(problems=["prob_123"]) - Focus on specific problems
    - recommendations(mode="deepen") - Go deeper on well-researched topics
    - recommendations(mode="explore") - Fill knowledge gaps
    - recommendations(job_id="...") - Poll for results

    Args:
        job_id: Job ID to poll (if provided, returns status/results)
        topic: Optional topic override (deprecated, use problems instead)
        problems: Optional list of problem IDs to focus recommendations on.
                  If not provided, uses all active problems.
        mode: Discovery mode:
              - "balanced" (default): Mix of deepen and explore
              - "deepen": Go deeper on topics with existing evidence
              - "explore": Fill knowledge gaps, find new perspectives

    Returns:
        When starting (no job_id):
        - job_id: Unique job identifier
        - status: "pending"
        - poll_after_seconds: Suggested wait time before polling
        - config_used: Settings including problems and mode

        When polling (with job_id):
        - job_id: Job identifier
        - status: "pending" | "running" | "completed" | "failed"
        - progress: 0.0 - 1.0
        - result: Recommendations with graph context (when completed)
    """
    # Poll mode: get existing job status
    if job_id:
        logger.info(f"Polling recommendations job: {job_id}")
        job = firestore_client.get_async_job(job_id)

        if not job:
            return {"error": f"Job not found: {job_id}"}

        response = {
            "job_id": job["job_id"],
            "status": job["status"],
            "progress": job.get("progress", 0.0),
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }

        if job["status"] == "completed":
            response["completed_at"] = job["completed_at"]
            response["result"] = job["result"]
        elif job["status"] == "failed":
            response["error"] = job.get("error", "Unknown error")
        else:
            # Still running - suggest poll interval
            response["poll_after_seconds"] = 5

        return response

    # Start mode: load defaults from config
    defaults = firestore_client.get_recommendations_defaults()
    hot_sites = defaults.get("hot_sites", "tech")
    limit = defaults.get("limit", 10)
    tavily_days = defaults.get("tavily_days", 30)

    # Story 11.3: Validate mode
    valid_modes = ["deepen", "explore", "balanced"]
    if mode not in valid_modes:
        return {"error": f"Invalid mode: {mode}. Must be one of {valid_modes}"}

    logger.info(
        f"Starting recommendations job: mode={mode}, problems={problems}, "
        f"hot_sites={hot_sites}, limit={limit}"
    )

    params = {
        "days": 14,  # KB lookback always 14 days
        "limit": limit,
        "hot_sites": hot_sites,
        "mode": mode,  # Story 11.3: Use Epic 11 mode
        "include_seen": False,
        "tavily_days": tavily_days,
        "topic": topic,  # Deprecated, kept for backwards compatibility
        "problems": problems,  # Story 11.3: Problem filter
    }

    # Create job in Firestore
    job_info = firestore_client.create_async_job(
        job_type="recommendations",
        params=params,
    )
    new_job_id = job_info["job_id"]

    # Enqueue to Cloud Tasks for async execution
    _enqueue_cloud_task(new_job_id, "recommendations", params)

    return {
        "job_id": new_job_id,
        "status": "pending",
        "poll_after_seconds": 10,
        "estimated_duration_seconds": 60,
        "created_at": job_info["created_at"],
        "config_used": {
            "mode": mode,
            "problems": problems,
            "hot_sites": hot_sites,
            "limit": limit,
            "tavily_days": tavily_days,
        },
    }


def recommendations_history(days: int = 14) -> Dict[str, Any]:
    """
    Get all recommendations from the last N days.

    Story 7.1: Simple flat list of all recommendations.

    Args:
        days: Lookback period (default 14)

    Returns:
        Dictionary with:
        - days: Lookback period used
        - total_count: Number of recommendations
        - recommendations: List of recommendation objects with:
            - title, url, domain
            - recommended_at: Timestamp
            - params: {mode, hot_sites}
            - why_recommended: Explanation
    """
    logger.info(f"Getting recommendations history: days={days}")
    return firestore_client.get_recommendations_history(days=days)


# ==================== Problems Tool (Epic 10) ====================


def problems(
    action: str,
    problem: Optional[str] = None,
    description: Optional[str] = None,
    problem_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified tool for managing Feynman-style problems.

    Epic 10 Story 10.1: Implements the "12 Favorite Problems" method.
    Problems collect evidence automatically as new content is ingested.
    Claude generates article ideas based on the evidence in conversation.

    Args:
        action: One of "add", "list", "analyze", "archive"
        problem: Problem statement (required for "add")
        description: Optional context/motivation (for "add")
        problem_id: Problem ID (required for "analyze" single, "archive")

    Returns:
        Dictionary with action-specific results

    Actions:
        add: Create a new problem
            >>> problems(action="add", problem="Why do feature flags fail?",
            ...          description="Teams adopt them but still have issues")

        list: Show all active problems with evidence counts
            >>> problems(action="list")

        analyze: Get evidence + connections for a problem (or all)
            >>> problems(action="analyze", problem_id="prob_001")
            >>> problems(action="analyze")  # All active problems

        archive: Archive a resolved/inactive problem
            >>> problems(action="archive", problem_id="prob_001")
    """
    try:
        logger.info(f"problems: action={action}, problem_id={problem_id}")

        if action == "add":
            return _problems_add(problem, description)
        elif action == "list":
            return _problems_list()
        elif action == "analyze":
            return _problems_analyze(problem_id)
        elif action == "archive":
            return _problems_archive(problem_id)
        else:
            return {"error": f"Unknown action: {action}. Use: add, list, analyze, archive"}

    except Exception as e:
        logger.error(f"problems failed: {e}")
        return {"error": str(e)}


def _problems_add(
    problem: Optional[str],
    description: Optional[str],
) -> Dict[str, Any]:
    """
    Create a new problem.

    Generates an embedding from problem + description for matching.
    """
    if not problem:
        return {"error": "Problem statement is required for action='add'"}

    # Default description if not provided
    description = description or ""

    # Generate embedding from combined text
    embedding_text = f"{problem} {description}".strip()

    try:
        embedding = embeddings.generate_query_embedding(embedding_text)
        logger.info(f"Generated embedding for problem: {len(embedding)} dimensions")
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return {"error": f"Failed to generate embedding: {e}"}

    # Create the problem in Firestore
    result = firestore_client.create_problem(
        problem=problem,
        description=description,
        embedding=embedding,
    )

    return result


def _problems_list() -> Dict[str, Any]:
    """
    List all active problems with evidence counts.
    """
    # Get active problems
    active = firestore_client.list_problems(status="active")
    archived = firestore_client.list_problems(status="archived")

    return {
        "problems": active,
        "total": len(active) + len(archived),
        "active": len(active),
        "archived": len(archived),
    }


def _problems_analyze(problem_id: Optional[str]) -> Dict[str, Any]:
    """
    Analyze evidence for a problem or all problems.

    Returns evidence grouped by supporting/contradicting.
    """
    if problem_id:
        # Analyze single problem
        return _analyze_single_problem(problem_id)
    else:
        # Analyze all active problems
        return _analyze_all_problems()


def _analyze_single_problem(problem_id: str) -> Dict[str, Any]:
    """
    Analyze a single problem with its evidence.
    """
    problem_data = firestore_client.get_problem(problem_id)

    if not problem_data:
        return {"error": f"Problem not found: {problem_id}"}

    evidence = problem_data.get("evidence", [])

    # Group evidence by type
    supporting = []
    contradicting = []

    for ev in evidence:
        formatted_ev = {
            "source_title": ev.get("source_title", "Unknown"),
            "quote": ev.get("quote", ""),
            "chunk_id": ev.get("chunk_id"),
            "similarity": ev.get("similarity", 0.0),
        }

        # Add relationship if present
        if ev.get("relationship"):
            formatted_ev["relationship"] = {
                "type": ev["relationship"].get("type"),
                "target": ev["relationship"].get("target_source"),
            }

        if ev.get("is_contradiction", False):
            contradicting.append(formatted_ev)
        else:
            supporting.append(formatted_ev)

    # Extract unique source connections
    connections = []
    seen_connections = set()

    for ev in evidence:
        rel = ev.get("relationship")
        if rel:
            source = ev.get("source_title", "Unknown")
            target = rel.get("target_source", "Unknown")
            rel_type = rel.get("type", "related")
            key = f"{source}->{target}:{rel_type}"

            if key not in seen_connections:
                seen_connections.add(key)
                connections.append({
                    "from": source,
                    "to": target,
                    "type": rel_type,
                })

    # Get unique sources
    unique_sources = list(set(ev.get("source_title", "Unknown") for ev in evidence))

    return {
        "problem_id": problem_id,
        "problem": problem_data.get("problem", ""),
        "description": problem_data.get("description", ""),
        "evidence": {
            "supporting": supporting,
            "contradicting": contradicting,
        },
        "connections": connections,
        "summary": {
            "evidence_count": len(evidence),
            "contradiction_count": len(contradicting),
            "sources": unique_sources,
            "ready_for_article": len(evidence) >= 3 and len(contradicting) >= 1,
        },
    }


def _analyze_all_problems() -> Dict[str, Any]:
    """
    Analyze all active problems.
    """
    active_problems = firestore_client.list_problems(status="active")

    results = []
    for problem in active_problems:
        analysis = _analyze_single_problem(problem["problem_id"])
        if "error" not in analysis:
            results.append({
                "problem_id": analysis["problem_id"],
                "problem": analysis["problem"],
                "summary": analysis["summary"],
            })

    return {
        "problems": results,
        "total_analyzed": len(results),
    }


def _problems_archive(problem_id: Optional[str]) -> Dict[str, Any]:
    """
    Archive a problem.
    """
    if not problem_id:
        return {"error": "problem_id is required for action='archive'"}

    return firestore_client.archive_problem(problem_id)
