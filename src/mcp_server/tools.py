"""
MCP Tool handlers for search and query operations.

Tools:
- search_semantic: Semantic search using query embeddings
- search_by_metadata: Filter by tags, author, source
- get_related_chunks: Find similar chunks to a given chunk
- get_stats: Get knowledge base statistics
- search_by_date_range: Query chunks by date range
- search_by_relative_time: Query chunks using relative time periods (yesterday, last week, etc.)
- get_reading_activity: Get reading activity summary and statistics
- get_recently_added: Get most recently added chunks
- get_related_clusters: Find clusters conceptually related to a given cluster (Story 3.4)
- get_reading_recommendations: AI-powered reading recommendations (Story 3.5)
- update_recommendation_domains: Update recommendation domain whitelist (Story 3.5)
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import firestore_client
import embeddings

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
        'readwise_url': chunk.get('readwise_url'),
        'source_url': chunk.get('source_url'),
        'highlight_url': chunk.get('highlight_url')
    }


def _format_knowledge_card(chunk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract and format knowledge card from chunk data.

    Args:
        chunk: Chunk dictionary from Firestore

    Returns:
        Formatted knowledge card dict or None if missing
    """
    knowledge_card = chunk.get('knowledge_card')
    if not knowledge_card:
        return None

    return {
        'summary': knowledge_card.get('summary', ''),
        'takeaways': knowledge_card.get('takeaways', [])
    }


def _format_cluster_info(chunk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract and format cluster information from chunk data.
    Fetches cluster metadata from Firestore if cluster_id exists.

    Args:
        chunk: Chunk dictionary from Firestore

    Returns:
        Formatted cluster dict or None if no cluster assignment
    """
    cluster_ids = chunk.get('cluster_id', [])

    # Handle edge cases
    if not cluster_ids:
        return None

    # Get primary cluster (first in array)
    primary_cluster_id = cluster_ids[0] if isinstance(cluster_ids, list) else cluster_ids

    # Handle noise cluster
    if primary_cluster_id == 'noise':
        return {
            'cluster_id': 'noise',
            'name': 'Outliers / Noise',
            'description': 'Chunks that do not fit well into any semantic cluster'
        }

    # Fetch cluster metadata from Firestore
    try:
        cluster_metadata = firestore_client.get_cluster_by_id(primary_cluster_id)
        if cluster_metadata:
            return {
                'cluster_id': primary_cluster_id,
                'name': cluster_metadata.get('name', f'Cluster {primary_cluster_id}'),
                'description': cluster_metadata.get('description', '')
            }
        else:
            # Cluster metadata not found
            return {
                'cluster_id': primary_cluster_id,
                'name': f'Cluster {primary_cluster_id}',
                'description': 'Cluster metadata not available'
            }
    except Exception as e:
        logger.warning(f"Failed to fetch cluster metadata for {primary_cluster_id}: {e}")
        return {
            'cluster_id': primary_cluster_id,
            'name': f'Cluster {primary_cluster_id}',
            'description': 'Error fetching cluster metadata'
        }


def search_semantic(
    query: str,
    limit: int = 10,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None
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
            filters={'tags': tags, 'author': author, 'source': source} if (tags or author or source) else None
        )

        # Format results
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
            title = chunk.get('title', 'Untitled')
            author_name = chunk.get('author', 'Unknown')
            source_name = chunk.get('source', 'unknown')
            tags_list = chunk.get('tags', [])
            content = chunk.get('content', '')
            chunk_index = chunk.get('chunk_index', 0)
            total_chunks = chunk.get('total_chunks', 1)

            # Content snippet (first 500 chars)
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract knowledge card, cluster info, and URLs
            knowledge_card = _format_knowledge_card(chunk)
            cluster_info = _format_cluster_info(chunk)
            urls = _format_urls(chunk)

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content,
                'knowledge_card': knowledge_card,
                'cluster': cluster_info,
                **urls  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} results for query")

        return {
            'query': query,
            'result_count': len(results),
            'limit': limit,
            'filters': {'tags': tags, 'author': author, 'source': source} if (tags or author or source) else None,
            'results': results
        }

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return {
            'query': query,
            'result_count': 0,
            'error': str(e),
            'results': []
        }


def search_by_metadata(
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 20
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
                'error': 'At least one filter (tags, author, or source) is required',
                'result_count': 0,
                'results': []
            }

        # Query Firestore
        chunks = firestore_client.query_by_metadata(
            tags=tags,
            author=author,
            source=source,
            limit=limit
        )

        # Format results
        results = []
        for chunk in chunks:
            chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
            title = chunk.get('title', 'Untitled')
            author_name = chunk.get('author', 'Unknown')
            source_name = chunk.get('source', 'unknown')
            tags_list = chunk.get('tags', [])
            content = chunk.get('content', '')
            chunk_index = chunk.get('chunk_index', 0)
            total_chunks = chunk.get('total_chunks', 1)

            # Content snippet
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract knowledge card, cluster info, and URLs
            knowledge_card = _format_knowledge_card(chunk)
            cluster_info = _format_cluster_info(chunk)
            urls = _format_urls(chunk)

            result = {
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content,
                'knowledge_card': knowledge_card,
                'cluster': cluster_info,
                **urls  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} results matching metadata filters")

        return {
            'result_count': len(results),
            'filters': {'tags': tags, 'author': author, 'source': source},
            'limit': limit,
            'results': results
        }

    except Exception as e:
        logger.error(f"Metadata search failed: {e}")
        return {
            'result_count': 0,
            'error': str(e),
            'results': []
        }


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
                'error': f'Chunk not found: {chunk_id}',
                'result_count': 0,
                'results': []
            }

        # Get embedding from source chunk
        embedding = source_chunk.get('embedding')

        if not embedding:
            return {
                'error': f'Chunk {chunk_id} has no embedding vector',
                'result_count': 0,
                'results': []
            }

        # Convert Firestore Vector to list if needed
        if hasattr(embedding, 'to_map_value'):
            # It's a Firestore Vector object
            embedding_vector = list(embedding.to_map_value()['value'])
        else:
            embedding_vector = list(embedding)

        logger.info(f"Source chunk embedding: {len(embedding_vector)} dimensions")

        # Find similar chunks (limit + 1 to account for source chunk)
        similar_chunks = firestore_client.find_nearest(
            embedding_vector=embedding_vector,
            limit=limit + 1
        )

        # Filter out the source chunk
        related_chunks = [c for c in similar_chunks if c.get('id') != chunk_id][:limit]

        # Format results
        results = []
        for chunk in related_chunks:
            related_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
            title = chunk.get('title', 'Untitled')
            author = chunk.get('author', 'Unknown')
            source = chunk.get('source', 'unknown')
            content = chunk.get('content', '')
            chunk_index = chunk.get('chunk_index', 0)
            total_chunks = chunk.get('total_chunks', 1)

            # Content snippet
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract knowledge card, cluster info, and URLs
            knowledge_card = _format_knowledge_card(chunk)
            cluster_info = _format_cluster_info(chunk)
            urls = _format_urls(chunk)

            result = {
                'chunk_id': related_id,
                'title': title,
                'author': author,
                'source': source,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content,
                'knowledge_card': knowledge_card,
                'cluster': cluster_info,
                **urls  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} related chunks")

        return {
            'source_chunk_id': chunk_id,
            'source_title': source_chunk.get('title', 'Untitled'),
            'result_count': len(results),
            'limit': limit,
            'results': results
        }

    except Exception as e:
        logger.error(f"Get related chunks failed: {e}")
        return {
            'source_chunk_id': chunk_id,
            'result_count': 0,
            'error': str(e),
            'results': []
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
        return {
            'error': str(e),
            'total_chunks': 0,
            'total_documents': 0
        }


def search_by_date_range(
    start_date: str,
    end_date: str,
    limit: int = 20,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None
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
            source=source
        )

        # Format results
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
            title = chunk.get('title', 'Untitled')
            author_name = chunk.get('author', 'Unknown')
            source_name = chunk.get('source', 'unknown')
            tags_list = chunk.get('tags', [])
            content = chunk.get('content', '')
            chunk_index = chunk.get('chunk_index', 0)
            total_chunks = chunk.get('total_chunks', 1)

            # Content snippet (first 500 chars)
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract URLs (Story 2.7)
            urls = _format_urls(chunk)

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content,
                **urls  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} chunks in date range")

        return {
            'start_date': start_date,
            'end_date': end_date,
            'result_count': len(results),
            'limit': limit,
            'filters': {'tags': tags, 'author': author, 'source': source} if (tags or author or source) else None,
            'results': results
        }

    except Exception as e:
        logger.error(f"Date range search failed: {e}")
        return {
            'start_date': start_date,
            'end_date': end_date,
            'result_count': 0,
            'error': str(e),
            'results': []
        }


def search_by_relative_time(
    period: str,
    limit: int = 20,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None
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
            period=period,
            limit=limit,
            tags=tags,
            author=author,
            source=source
        )

        # Format results
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
            title = chunk.get('title', 'Untitled')
            author_name = chunk.get('author', 'Unknown')
            source_name = chunk.get('source', 'unknown')
            tags_list = chunk.get('tags', [])
            content = chunk.get('content', '')
            chunk_index = chunk.get('chunk_index', 0)
            total_chunks = chunk.get('total_chunks', 1)

            # Content snippet (first 500 chars)
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract URLs (Story 2.7)
            urls = _format_urls(chunk)

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content,
                **urls  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} chunks for period '{period}'")

        return {
            'period': period,
            'result_count': len(results),
            'limit': limit,
            'filters': {'tags': tags, 'author': author, 'source': source} if (tags or author or source) else None,
            'results': results
        }

    except Exception as e:
        logger.error(f"Relative time search failed: {e}")
        return {
            'period': period,
            'result_count': 0,
            'error': str(e),
            'results': []
        }


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

        logger.info(f"Activity collected: {activity.get('total_chunks_added', 0)} chunks added")

        return activity

    except Exception as e:
        logger.error(f"Get reading activity failed: {e}")
        return {
            'error': str(e),
            'period': period,
            'total_chunks_added': 0,
            'days_with_activity': 0,
            'chunks_by_day': {},
            'top_sources': [],
            'top_authors': []
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
            chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
            title = chunk.get('title', 'Untitled')
            author_name = chunk.get('author', 'Unknown')
            source_name = chunk.get('source', 'unknown')
            tags_list = chunk.get('tags', [])
            content = chunk.get('content', '')
            chunk_index = chunk.get('chunk_index', 0)
            total_chunks = chunk.get('total_chunks', 1)

            # Content snippet (first 500 chars)
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract URLs (Story 2.7)
            urls = _format_urls(chunk)

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content,
                **urls  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Retrieved {len(results)} recently added chunks")

        return {
            'result_count': len(results),
            'limit': limit,
            'days': days,
            'results': results
        }

    except Exception as e:
        logger.error(f"Get recently added failed: {e}")
        return {
            'result_count': 0,
            'error': str(e),
            'results': []
        }


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
            return {
                'error': f'Chunk not found: {chunk_id}',
                'chunk_id': chunk_id
            }

        # Extract knowledge card
        knowledge_card = chunk.get('knowledge_card')

        if not knowledge_card:
            return {
                'error': f'Knowledge card not available for chunk {chunk_id}',
                'chunk_id': chunk_id,
                'title': chunk.get('title', 'Untitled'),
                'source': chunk.get('source', 'unknown')
            }

        logger.info(f"Retrieved knowledge card for {chunk_id}")

        # Extract URLs (Story 2.7)
        urls = _format_urls(chunk)

        return {
            'chunk_id': chunk_id,
            'title': chunk.get('title', 'Untitled'),
            'author': chunk.get('author', 'Unknown'),
            'source': chunk.get('source', 'unknown'),
            'knowledge_card': {
                'summary': knowledge_card.get('summary', ''),
                'takeaways': knowledge_card.get('takeaways', [])
            },
            **urls  # Story 2.7: Include URL fields
        }

    except Exception as e:
        logger.error(f"Get knowledge card failed: {e}")
        return {
            'error': str(e),
            'chunk_id': chunk_id
        }


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
            embedding_vector=query_embedding,
            limit=limit
        )

        # Format results - return only knowledge card summaries
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
            title = chunk.get('title', 'Untitled')
            author = chunk.get('author', 'Unknown')
            source = chunk.get('source', 'unknown')

            # Extract knowledge card
            knowledge_card = chunk.get('knowledge_card')

            # Extract URLs (Story 2.7)
            urls = _format_urls(chunk)

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author,
                'source': source,
                'knowledge_card': {
                    'summary': knowledge_card.get('summary', '') if knowledge_card else 'Knowledge card not available',
                    'takeaways': knowledge_card.get('takeaways', []) if knowledge_card else []
                },
                **urls  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} knowledge card results")

        return {
            'query': query,
            'result_count': len(results),
            'limit': limit,
            'results': results
        }

    except Exception as e:
        logger.error(f"Search knowledge cards failed: {e}")
        return {
            'query': query,
            'result_count': 0,
            'error': str(e),
            'results': []
        }


def list_clusters() -> Dict[str, Any]:
    """
    List all semantic clusters with metadata.

    Returns:
        Dictionary with list of clusters sorted by size
    """
    try:
        logger.info("Listing all clusters")

        clusters = firestore_client.get_all_clusters()

        # Format results
        results = []
        for cluster in clusters:
            cluster_id = cluster.get('id', 'unknown')

            # Skip noise cluster or handle specially
            if cluster_id == 'noise':
                result = {
                    'cluster_id': cluster_id,
                    'name': 'Outliers / Noise',
                    'description': 'Chunks that do not fit well into any semantic cluster',
                    'size': cluster.get('size', 0)
                }
            else:
                result = {
                    'cluster_id': cluster_id,
                    'name': cluster.get('name', f'Cluster {cluster_id}'),
                    'description': cluster.get('description', ''),
                    'size': cluster.get('size', 0),
                    'created_at': str(cluster.get('created_at', ''))
                }

            results.append(result)

        logger.info(f"Retrieved {len(results)} clusters")

        return {
            'cluster_count': len(results),
            'clusters': results
        }

    except Exception as e:
        logger.error(f"List clusters failed: {e}")
        return {
            'cluster_count': 0,
            'error': str(e),
            'clusters': []
        }


def get_cluster(cluster_id: str, include_chunks: bool = True, limit: int = 20) -> Dict[str, Any]:
    """
    Get cluster details with member chunks.

    Args:
        cluster_id: Cluster ID to fetch
        include_chunks: Whether to include member chunks (default True)
        limit: Maximum member chunks to return (default 20)

    Returns:
        Dictionary with cluster metadata and member chunks
    """
    try:
        logger.info(f"Fetching cluster {cluster_id} (include_chunks: {include_chunks})")

        # Fetch cluster metadata
        cluster = firestore_client.get_cluster_by_id(cluster_id)

        if not cluster:
            return {
                'error': f'Cluster not found: {cluster_id}',
                'cluster_id': cluster_id
            }

        # Build response with metadata
        response = {
            'cluster_id': cluster_id,
            'name': cluster.get('name', f'Cluster {cluster_id}'),
            'description': cluster.get('description', ''),
            'size': cluster.get('size', 0),
            'created_at': str(cluster.get('created_at', ''))
        }

        # Fetch member chunks if requested
        if include_chunks:
            member_chunks = firestore_client.get_chunks_by_cluster(cluster_id, limit=limit)

            # Format member chunks with knowledge cards and URLs
            members = []
            for chunk in member_chunks:
                chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
                knowledge_card = _format_knowledge_card(chunk)
                urls = _format_urls(chunk)

                member = {
                    'chunk_id': chunk_id,
                    'title': chunk.get('title', 'Untitled'),
                    'author': chunk.get('author', 'Unknown'),
                    'source': chunk.get('source', 'unknown'),
                    'knowledge_card': knowledge_card,
                    **urls  # Story 2.7: Include URL fields
                }

                members.append(member)

            response['member_count'] = len(members)
            response['members'] = members

        logger.info(f"Retrieved cluster {cluster_id} with {response.get('member_count', 0)} members")

        return response

    except Exception as e:
        logger.error(f"Get cluster failed: {e}")
        return {
            'error': str(e),
            'cluster_id': cluster_id
        }


def search_within_cluster_tool(cluster_id: str, query: str, limit: int = 10) -> Dict[str, Any]:
    """
    Semantic search restricted to a specific cluster.

    Args:
        cluster_id: Cluster ID to search within
        query: Natural language search query
        limit: Maximum number of results (default 10)

    Returns:
        Dictionary with search results from the cluster
    """
    try:
        logger.info(f"Searching within cluster {cluster_id} for query: '{query}' (limit: {limit})")

        # Verify cluster exists
        cluster = firestore_client.get_cluster_by_id(cluster_id)

        if not cluster:
            return {
                'error': f'Cluster not found: {cluster_id}',
                'cluster_id': cluster_id,
                'query': query,
                'result_count': 0,
                'results': []
            }

        # Generate embedding for query
        query_embedding = embeddings.generate_query_embedding(query)

        # Execute filtered vector search
        chunks = firestore_client.search_within_cluster(
            cluster_id=cluster_id,
            embedding_vector=query_embedding,
            limit=limit
        )

        # Format results
        results = []
        for rank, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
            title = chunk.get('title', 'Untitled')
            author = chunk.get('author', 'Unknown')
            source = chunk.get('source', 'unknown')
            content = chunk.get('content', '')

            # Content snippet
            snippet = content[:500] + "..." if len(content) > 500 else content

            # Extract knowledge card and URLs
            knowledge_card = _format_knowledge_card(chunk)
            urls = _format_urls(chunk)

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author,
                'source': source,
                'snippet': snippet,
                'knowledge_card': knowledge_card,
                **urls  # Story 2.7: Include URL fields
            }

            results.append(result)

        logger.info(f"Found {len(results)} results in cluster {cluster_id}")

        return {
            'cluster_id': cluster_id,
            'cluster_name': cluster.get('name', f'Cluster {cluster_id}'),
            'query': query,
            'result_count': len(results),
            'limit': limit,
            'results': results
        }

    except Exception as e:
        logger.error(f"Search within cluster failed: {e}")
        return {
            'cluster_id': cluster_id,
            'query': query,
            'result_count': 0,
            'error': str(e),
            'results': []
        }


def get_related_clusters(
    cluster_id: str,
    limit: int = 5,
    distance_measure: str = "COSINE"
) -> Dict[str, Any]:
    """
    Find clusters conceptually related to the given cluster using Firestore vector search.

    Story 3.4: Cluster Relationship Discovery via Vector Search

    Uses Firestore vector search on cluster centroids to find nearest neighbors.
    Enables concept chaining and emergent idea discovery across the knowledge base.

    Args:
        cluster_id: Source cluster ID to find relations for
        limit: Maximum number of related clusters (default 5, max 20)
        distance_measure: COSINE (default), EUCLIDEAN, or DOT_PRODUCT

    Returns:
        Dictionary with related clusters list and metadata

    Example:
        >>> get_related_clusters("cluster_12", limit=3)
        {
            'source_cluster': {
                'cluster_id': 'cluster_12',
                'name': 'Semantic Search & Embeddings',
                'description': '...'
            },
            'result_count': 3,
            'results': [
                {
                    'cluster_id': 'cluster_18',
                    'name': 'Personal Knowledge Management',
                    'description': 'Systems for organizing personal knowledge...',
                    'similarity_score': 0.872,
                    'distance': 0.256,
                    'chunk_count': 31
                },
                ...
            ]
        }
    """
    try:
        logger.info(f"Finding related clusters for {cluster_id} (limit: {limit}, distance: {distance_measure})")

        # Validate limit parameter
        if limit < 1 or limit > 20:
            return {
                'cluster_id': cluster_id,
                'error': 'Limit must be between 1 and 20',
                'result_count': 0,
                'results': []
            }

        # Get source cluster
        source_cluster = firestore_client.get_cluster_by_id(cluster_id)
        if not source_cluster:
            return {
                'cluster_id': cluster_id,
                'error': f'Cluster not found: {cluster_id}',
                'result_count': 0,
                'results': []
            }

        # Get centroid from source cluster
        source_centroid = source_cluster.get('centroid_768d')
        if not source_centroid:
            return {
                'cluster_id': cluster_id,
                'error': f'Cluster {cluster_id} has no centroid_768d (vector search not possible)',
                'result_count': 0,
                'results': []
            }

        # Import Firestore vector search types
        from google.cloud.firestore_v1.vector import Vector
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure

        # Map distance measure string to enum
        measure_map = {
            'COSINE': DistanceMeasure.COSINE,
            'EUCLIDEAN': DistanceMeasure.EUCLIDEAN,
            'DOT_PRODUCT': DistanceMeasure.DOT_PRODUCT
        }
        distance = measure_map.get(distance_measure, DistanceMeasure.COSINE)

        # Perform Firestore vector search
        db = firestore_client.get_firestore_client()
        logger.info(f"Executing vector search on centroid_768d...")

        vector_query = db.collection('clusters').find_nearest(
            vector_field='centroid_768d',
            query_vector=Vector(source_centroid),
            distance_measure=distance,
            limit=limit + 1,  # +1 because source cluster will be in results
            distance_result_field='vector_distance'  # Store distance in result
        )

        # Format results
        results = []
        for doc in vector_query.stream():
            # Skip source cluster itself
            if doc.id == cluster_id:
                continue

            # Skip noise clusters (various naming conventions)
            # Noise clusters don't represent coherent concepts
            doc_data = doc.to_dict()
            cluster_name = doc_data.get('name', '')
            if doc.id in ('-1', 'cluster_-1', 'noise', 'cluster-noise') or 'noise' in cluster_name.lower() or 'noise' in doc.id.lower():
                continue

            # Extract distance (lower = more similar)
            distance_value = doc_data.get('vector_distance', 0)

            # Convert distance to similarity score (1 = identical, 0 = opposite)
            # For COSINE: distance is 0-2 range (0=identical, 2=opposite)
            if distance_measure == 'COSINE':
                similarity = 1 - (distance_value / 2)
            else:
                # For EUCLIDEAN/DOT_PRODUCT: use normalized similarity
                similarity = 1 / (1 + distance_value)

            results.append({
                'cluster_id': doc.id,
                'name': doc_data.get('name', f'Cluster {doc.id}'),
                'description': doc_data.get('description', ''),
                'similarity_score': round(similarity, 3),
                'distance': round(distance_value, 3),
                'size': doc_data.get('size', 0)
            })

            if len(results) >= limit:
                break

        logger.info(f"Found {len(results)} related clusters for {cluster_id}")

        return {
            'source_cluster': {
                'cluster_id': cluster_id,
                'name': source_cluster.get('name', f'Cluster {cluster_id}'),
                'description': source_cluster.get('description', ''),
                'size': source_cluster.get('size', 0)
            },
            'distance_measure': distance_measure,
            'result_count': len(results),
            'limit': limit,
            'results': results
        }

    except ImportError as e:
        logger.error(f"Firestore vector search not available: {e}")
        return {
            'cluster_id': cluster_id,
            'error': 'Firestore vector search requires google-cloud-firestore >= 2.16.0',
            'result_count': 0,
            'results': []
        }
    except Exception as e:
        logger.error(f"Get related clusters failed: {e}")
        return {
            'cluster_id': cluster_id,
            'error': str(e),
            'result_count': 0,
            'results': []
        }


# ============================================================================
# Reading Recommendations (Story 3.5)
# ============================================================================

def get_reading_recommendations(
    scope: str = "both",
    days: int = 14,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Get AI-powered reading recommendations based on KB content.

    Story 3.5: AI-Powered Reading Recommendations

    Analyzes recent reads and top clusters, searches Tavily with domain
    whitelisting, filters for quality, and deduplicates against KB.

    Args:
        scope: "recent" (recent reads), "clusters" (top clusters), or "both" (default)
        days: Lookback period for recent reads (default 14)
        limit: Maximum recommendations to return (default 10)

    Returns:
        Dictionary with:
        - generated_at: Timestamp
        - processing_time_seconds: Total time taken
        - scope: Scope used
        - days_analyzed: Days lookback
        - queries_used: List of search queries
        - recommendations: List of recommendation objects
        - filtered_out: Counts of filtered items

    Example:
        >>> get_reading_recommendations(scope="clusters", days=7, limit=5)
        {
            "generated_at": "2025-12-10T10:00:00Z",
            "processing_time_seconds": 35,
            "recommendations": [
                {
                    "title": "Platform Engineering in 2025",
                    "url": "https://martinfowler.com/...",
                    "domain": "martinfowler.com",
                    "depth_score": 4,
                    "why_recommended": "Connects to your reading cluster: Platform Engineering"
                }
            ]
        }
    """
    start_time = time.time()

    try:
        logger.info(f"Generating reading recommendations: scope={scope}, days={days}, limit={limit}")

        # Validate scope
        if scope not in ("recent", "clusters", "both"):
            return {
                'error': f"Invalid scope: {scope}. Must be 'recent', 'clusters', or 'both'",
                'recommendations': []
            }

        # Import recommendation modules
        import recommendation_queries
        import recommendation_filter
        import tavily_client

        # Step 1: Get recommendation config (domain whitelist)
        config = firestore_client.get_recommendation_config()
        quality_domains = config.get('quality_domains', [])
        excluded_domains = config.get('excluded_domains', [])

        logger.info(f"Using {len(quality_domains)} whitelisted domains")

        # Step 2: Generate smart search queries
        queries = recommendation_queries.generate_search_queries(
            scope=scope,
            days=days,
            max_queries=8
        )

        if not queries:
            return {
                'generated_at': datetime.utcnow().isoformat() + 'Z',
                'processing_time_seconds': round(time.time() - start_time, 1),
                'scope': scope,
                'days_analyzed': days,
                'error': 'No queries generated - insufficient KB content',
                'queries_used': [],
                'recommendations': [],
                'filtered_out': {}
            }

        query_strings = [q['query'] for q in queries]
        logger.info(f"Generated {len(queries)} search queries")

        # Step 3: Search Tavily
        all_results = []
        all_contexts = []

        for query_dict in queries:
            query_str = recommendation_queries.format_query_for_tavily(query_dict)

            try:
                search_result = tavily_client.search(
                    query=query_str,
                    include_domains=quality_domains if quality_domains else None,
                    exclude_domains=excluded_domains if excluded_domains else None,
                    days=30,  # Last 30 days for recency
                    max_results=5
                )

                for result in search_result.get('results', []):
                    all_results.append(result)
                    all_contexts.append(query_dict)

            except Exception as e:
                logger.warning(f"Tavily search failed for query '{query_str[:50]}...': {e}")
                continue

        logger.info(f"Tavily returned {len(all_results)} total results")

        if not all_results:
            return {
                'generated_at': datetime.utcnow().isoformat() + 'Z',
                'processing_time_seconds': round(time.time() - start_time, 1),
                'scope': scope,
                'days_analyzed': days,
                'queries_used': query_strings,
                'recommendations': [],
                'filtered_out': {'no_results': True}
            }

        # Step 4: Filter for quality and deduplicate
        filter_result = recommendation_filter.filter_recommendations(
            recommendations=all_results,
            query_contexts=all_contexts,
            min_depth_score=3,
            max_per_domain=2,
            check_duplicates=True
        )

        filtered_recs = filter_result.get('recommendations', [])
        filtered_out = filter_result.get('filtered_out', {})

        # Step 5: Sort by depth score and limit
        filtered_recs.sort(key=lambda x: x.get('depth_score', 0), reverse=True)
        final_recs = filtered_recs[:limit]

        processing_time = round(time.time() - start_time, 1)
        logger.info(
            f"Recommendations complete: {len(final_recs)} recommendations "
            f"in {processing_time}s"
        )

        return {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'processing_time_seconds': processing_time,
            'scope': scope,
            'days_analyzed': days,
            'queries_used': query_strings,
            'recommendations': final_recs,
            'filtered_out': filtered_out
        }

    except Exception as e:
        logger.error(f"Get reading recommendations failed: {e}")
        return {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'processing_time_seconds': round(time.time() - start_time, 1),
            'scope': scope,
            'error': str(e),
            'recommendations': []
        }


def update_recommendation_domains(
    add_domains: Optional[List[str]] = None,
    remove_domains: Optional[List[str]] = None
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
            updated_by="mcp_tool"
        )

        if result.get('success'):
            config = result.get('config', {})
            return {
                'success': True,
                'quality_domains': config.get('quality_domains', []),
                'excluded_domains': config.get('excluded_domains', []),
                'domain_count': len(config.get('quality_domains', [])),
                'changes': result.get('changes', {})
            }
        else:
            return {
                'success': False,
                'error': result.get('error', 'Unknown error')
            }

    except Exception as e:
        logger.error(f"Update recommendation domains failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


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
            'quality_domains': config.get('quality_domains', []),
            'excluded_domains': config.get('excluded_domains', []),
            'domain_count': len(config.get('quality_domains', [])),
            'last_updated': str(config.get('last_updated', '')),
            'updated_by': config.get('updated_by', '')
        }

    except Exception as e:
        logger.error(f"Get recommendation config failed: {e}")
        return {
            'error': str(e)
        }
