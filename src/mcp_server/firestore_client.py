"""
Firestore client wrapper for MCP server.

Provides read-only access to kb_items collection with support for:
- Listing all chunks
- Fetching chunks by ID
- Metadata filtering (tags, author, source)
- Vector similarity search (FIND_NEAREST)
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from google.cloud import firestore

# Try to import Vector types (might not be available in all versions)
try:
    from google.cloud.firestore_v1.vector import Vector
    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    HAS_VECTOR_SUPPORT = True
except ImportError:
    Vector = None  # type: ignore
    DistanceMeasure = None  # type: ignore
    HAS_VECTOR_SUPPORT = False

logger = logging.getLogger(__name__)

# Global Firestore client (lazy initialization)
_firestore_client = None


def get_firestore_client() -> firestore.Client:
    """
    Get or create Firestore client instance (cached).

    Returns:
        Initialized Firestore client
    """
    global _firestore_client

    if _firestore_client is None:
        project = os.getenv('GCP_PROJECT')
        logger.info(f"Initializing Firestore client for project: {project}")
        _firestore_client = firestore.Client(project=project)

    return _firestore_client


def list_all_chunks(limit: int = 100) -> List[Dict[str, Any]]:
    """
    List all chunks from kb_items collection.

    Args:
        limit: Maximum number of chunks to return (default 100)

    Returns:
        List of chunk dictionaries with metadata
    """
    try:
        db = get_firestore_client()
        collection = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

        logger.info(f"Listing chunks from {collection} (limit: {limit})")

        query = db.collection(collection).limit(limit)
        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data['id'] = doc.id  # Add document ID
            chunks.append(chunk_data)

        logger.info(f"Retrieved {len(chunks)} chunks")
        return chunks

    except Exception as e:
        logger.error(f"Failed to list chunks: {e}")
        return []


def get_chunk_by_id(chunk_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single chunk by ID from kb_items collection.

    Args:
        chunk_id: Chunk document ID

    Returns:
        Chunk dictionary with metadata and content, or None if not found
    """
    try:
        db = get_firestore_client()
        collection = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

        logger.info(f"Fetching chunk {chunk_id} from {collection}")

        doc_ref = db.collection(collection).document(chunk_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.warning(f"Chunk {chunk_id} not found")
            return None

        chunk_data = doc.to_dict()
        chunk_data['id'] = doc.id

        logger.info(f"Retrieved chunk {chunk_id}")
        return chunk_data

    except Exception as e:
        logger.error(f"Failed to fetch chunk {chunk_id}: {e}")
        return None


def query_by_metadata(
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Query chunks by metadata filters.

    Args:
        tags: Filter by tags (array-contains-any)
        author: Filter by exact author match
        source: Filter by exact source match
        limit: Maximum results to return

    Returns:
        List of matching chunks
    """
    try:
        db = get_firestore_client()
        collection = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

        logger.info(f"Querying {collection} with filters: tags={tags}, author={author}, source={source}")

        query = db.collection(collection)

        # Apply filters
        if tags:
            query = query.where('tags', 'array_contains_any', tags)
        if author:
            query = query.where('author', '==', author)
        if source:
            query = query.where('source', '==', source)

        # Sort by created_at descending (most recent first)
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data['id'] = doc.id
            chunks.append(chunk_data)

        logger.info(f"Found {len(chunks)} chunks matching filters")
        return chunks

    except Exception as e:
        logger.error(f"Failed to query by metadata: {e}")
        return []


def find_nearest(
    embedding_vector: List[float],
    limit: int = 10,
    filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Execute vector similarity search using Firestore FIND_NEAREST.

    Args:
        embedding_vector: Query embedding (768 dimensions)
        limit: Number of nearest neighbors to return
        filters: Optional metadata filters (tags, author, source)

    Returns:
        List of chunks ranked by cosine similarity
    """
    if not HAS_VECTOR_SUPPORT:
        logger.error("Vector search not supported - missing Firestore vector types")
        return []

    try:
        db = get_firestore_client()
        collection = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

        logger.info(f"Executing vector search in {collection} (limit: {limit})")

        # Create vector query
        vector_query = db.collection(collection).find_nearest(
            vector_field='embedding',
            query_vector=Vector(embedding_vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit
        )

        # TODO: Apply filters if provided (Firestore vector search filter support)
        # Note: Firestore vector search filtering is limited - may need post-processing

        docs = vector_query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data['id'] = doc.id
            chunks.append(chunk_data)

        logger.info(f"Found {len(chunks)} similar chunks")
        return chunks

    except Exception as e:
        logger.error(f"Failed to execute vector search: {e}")
        return []


def get_stats() -> Dict[str, Any]:
    """
    Get statistics about the knowledge base.

    Returns:
        Dictionary with counts and unique values
    """
    try:
        db = get_firestore_client()
        collection = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

        logger.info(f"Collecting stats from {collection}")

        # Count total documents
        docs = db.collection(collection).stream()

        total_chunks = 0
        unique_sources = set()
        unique_authors = set()
        unique_tags = set()
        unique_parent_docs = set()

        for doc in docs:
            total_chunks += 1
            data = doc.to_dict()

            # Only add non-None values to sets
            if 'source' in data and data['source'] is not None:
                unique_sources.add(data['source'])
            if 'author' in data and data['author'] is not None:
                unique_authors.add(data['author'])
            if 'tags' in data and data['tags'] is not None:
                # Filter out None values from tags list
                valid_tags = [tag for tag in data['tags'] if tag is not None]
                unique_tags.update(valid_tags)
            if 'parent_doc_id' in data and data['parent_doc_id'] is not None:
                unique_parent_docs.add(data['parent_doc_id'])

        stats = {
            'total_chunks': total_chunks,
            'total_documents': len(unique_parent_docs),
            'sources': sorted(list(unique_sources)),
            'source_count': len(unique_sources),
            'authors': sorted(list(unique_authors)),
            'author_count': len(unique_authors),
            'tags': sorted(list(unique_tags)),
            'tag_count': len(unique_tags),
            'avg_chunks_per_doc': round(total_chunks / len(unique_parent_docs), 1) if unique_parent_docs else 0
        }

        logger.info(f"Stats: {total_chunks} chunks, {len(unique_parent_docs)} documents")
        return stats

    except Exception as e:
        logger.error(f"Failed to collect stats: {e}")
        return {
            'total_chunks': 0,
            'total_documents': 0,
            'sources': [],
            'source_count': 0,
            'authors': [],
            'author_count': 0,
            'tags': [],
            'tag_count': 0,
            'avg_chunks_per_doc': 0,
            'error': str(e)
        }


def query_by_date_range(
    start_date: str,
    end_date: str,
    limit: int = 20,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query chunks by date range (created_at timestamp).

    Args:
        start_date: Start date in ISO format (YYYY-MM-DD)
        end_date: End date in ISO format (YYYY-MM-DD)
        limit: Maximum results to return
        tags: Optional tag filter (array-contains-any)
        author: Optional author filter (exact match)
        source: Optional source filter (exact match)

    Returns:
        List of matching chunks ordered by created_at DESC (most recent first)
    """
    try:
        db = get_firestore_client()
        collection = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

        # Parse dates
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        # End date is inclusive, so add 1 day and subtract microsecond
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1) - timedelta(microseconds=1)

        logger.info(f"Querying {collection} by date range: {start_date} to {end_date} (limit: {limit})")

        query = db.collection(collection)

        # Apply date range filter
        query = query.where('created_at', '>=', start_dt)
        query = query.where('created_at', '<=', end_dt)

        # Apply optional metadata filters
        if tags:
            query = query.where('tags', 'array_contains_any', tags)
        if author:
            query = query.where('author', '==', author)
        if source:
            query = query.where('source', '==', source)

        # Sort by created_at descending (most recent first)
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data['id'] = doc.id
            chunks.append(chunk_data)

        logger.info(f"Found {len(chunks)} chunks in date range {start_date} to {end_date}")
        return chunks

    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return []
    except Exception as e:
        logger.error(f"Failed to query by date range: {e}")
        return []


def query_by_relative_time(
    period: str,
    limit: int = 20,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query chunks using relative time periods.

    Args:
        period: One of "yesterday", "last_week", "last_month", "last_3_days", "last_7_days", "last_30_days"
        limit: Maximum results to return
        tags: Optional tag filter
        author: Optional author filter
        source: Optional source filter

    Returns:
        List of matching chunks ordered by created_at DESC
    """
    try:
        now = datetime.utcnow()

        # Map period to date range
        if period == "yesterday":
            start_dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
        elif period == "last_3_days":
            start_dt = (now - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = now
        elif period == "last_week" or period == "last_7_days":
            start_dt = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = now
        elif period == "last_month" or period == "last_30_days":
            start_dt = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = now
        else:
            logger.error(f"Unknown period: {period}")
            return []

        logger.info(f"Querying {period}: {start_dt} to {end_dt}")

        db = get_firestore_client()
        collection = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

        query = db.collection(collection)

        # Apply date range filter
        query = query.where('created_at', '>=', start_dt)
        query = query.where('created_at', '<=', end_dt)

        # Apply optional metadata filters
        if tags:
            query = query.where('tags', 'array_contains_any', tags)
        if author:
            query = query.where('author', '==', author)
        if source:
            query = query.where('source', '==', source)

        # Sort by created_at descending (most recent first)
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data['id'] = doc.id
            chunks.append(chunk_data)

        logger.info(f"Found {len(chunks)} chunks for period '{period}'")
        return chunks

    except Exception as e:
        logger.error(f"Failed to query by relative time: {e}")
        return []


def get_activity_summary(period: str = "last_7_days") -> Dict[str, Any]:
    """
    Get reading activity summary for a time period.

    Args:
        period: One of "today", "yesterday", "last_3_days", "last_7_days", "last_30_days", "last_month"

    Returns:
        Dictionary with activity stats: total_chunks_added, days_with_activity, chunks_by_day, top_sources, top_authors
    """
    try:
        now = datetime.utcnow()

        # Map period to start date
        if period == "today":
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "yesterday":
            start_dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            now = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "last_3_days":
            start_dt = (now - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "last_7_days" or period == "last_week":
            start_dt = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "last_30_days" or period == "last_month":
            start_dt = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            logger.error(f"Unknown period: {period}")
            return {'error': f'Unknown period: {period}'}

        logger.info(f"Collecting activity summary for {period}")

        db = get_firestore_client()
        collection = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

        # Query all chunks in period (no limit)
        query = db.collection(collection)
        query = query.where('created_at', '>=', start_dt)
        query = query.where('created_at', '<=', now)
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING)

        docs = query.stream()

        chunks_by_day = {}
        top_sources = {}
        top_authors = {}
        total_chunks = 0

        for doc in docs:
            data = doc.to_dict()
            total_chunks += 1

            # Group by day
            created_at = data.get('created_at')
            if created_at:
                day_key = created_at.strftime('%Y-%m-%d')
                chunks_by_day[day_key] = chunks_by_day.get(day_key, 0) + 1

            # Track sources
            source = data.get('source')
            if source:
                top_sources[source] = top_sources.get(source, 0) + 1

            # Track authors
            author = data.get('author')
            if author:
                top_authors[author] = top_authors.get(author, 0) + 1

        # Sort by count descending
        top_sources_sorted = sorted(top_sources.items(), key=lambda x: x[1], reverse=True)[:5]
        top_authors_sorted = sorted(top_authors.items(), key=lambda x: x[1], reverse=True)[:5]

        activity = {
            'period': period,
            'total_chunks_added': total_chunks,
            'days_with_activity': len(chunks_by_day),
            'chunks_by_day': dict(sorted(chunks_by_day.items())),  # Sort by date
            'top_sources': [{'source': s, 'count': c} for s, c in top_sources_sorted],
            'top_authors': [{'author': a, 'count': c} for a, c in top_authors_sorted]
        }

        logger.info(f"Activity summary: {total_chunks} chunks added in {len(chunks_by_day)} days")
        return activity

    except Exception as e:
        logger.error(f"Failed to collect activity summary: {e}")
        return {
            'error': str(e),
            'period': period,
            'total_chunks_added': 0,
            'days_with_activity': 0,
            'chunks_by_day': {},
            'top_sources': [],
            'top_authors': []
        }


def get_recently_added(limit: int = 10, days: int = 7) -> List[Dict[str, Any]]:
    """
    Get most recently added chunks.

    Args:
        limit: Maximum number of chunks to return
        days: Look back this many days

    Returns:
        List of chunks ordered by created_at DESC (most recent first)
    """
    try:
        db = get_firestore_client()
        collection = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

        now = datetime.utcnow()
        start_dt = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(f"Getting {limit} recently added chunks from last {days} days")

        query = db.collection(collection)
        query = query.where('created_at', '>=', start_dt)
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data['id'] = doc.id
            chunks.append(chunk_data)

        logger.info(f"Retrieved {len(chunks)} recently added chunks")
        return chunks

    except Exception as e:
        logger.error(f"Failed to get recently added chunks: {e}")
        return []
