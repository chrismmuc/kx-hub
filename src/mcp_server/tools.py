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
"""

import logging
from typing import List, Dict, Any, Optional
import firestore_client
import embeddings

logger = logging.getLogger(__name__)


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

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content
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

            result = {
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content
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

            result = {
                'chunk_id': related_id,
                'title': title,
                'author': author,
                'source': source,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content
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

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content
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

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content
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

            result = {
                'rank': rank,
                'chunk_id': chunk_id,
                'title': title,
                'author': author_name,
                'source': source_name,
                'tags': tags_list,
                'chunk_info': f"{chunk_index + 1}/{total_chunks}",
                'snippet': snippet,
                'full_content': content
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
