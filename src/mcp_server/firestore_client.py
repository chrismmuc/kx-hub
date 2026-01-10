"""
Firestore client wrapper for MCP server.

Provides read-only access to kb_items collection with support for:
- Listing all chunks
- Fetching chunks by ID
- Metadata filtering (tags, author, source)
- Vector similarity search (FIND_NEAREST)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from google.cloud import firestore

# Try to import Vector types (might not be available in all versions)
try:
    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    from google.cloud.firestore_v1.vector import Vector

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
        project = os.getenv("GCP_PROJECT")
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
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        logger.info(f"Listing chunks from {collection} (limit: {limit})")

        query = db.collection(collection).limit(limit)
        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data["id"] = doc.id  # Add document ID
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
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        logger.info(f"Fetching chunk {chunk_id} from {collection}")

        doc_ref = db.collection(collection).document(chunk_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.warning(f"Chunk {chunk_id} not found")
            return None

        chunk_data = doc.to_dict()
        chunk_data["id"] = doc.id

        logger.info(f"Retrieved chunk {chunk_id}")
        return chunk_data

    except Exception as e:
        logger.error(f"Failed to fetch chunk {chunk_id}: {e}")
        return None


def get_chunks_batch(chunk_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Batch fetch multiple chunks by ID using Firestore get_all().

    Story 3.10: Fixes N+1 query problem - fetches up to 100 chunks in one read.

    Args:
        chunk_ids: List of chunk document IDs

    Returns:
        Dictionary mapping chunk_id to chunk data (missing chunks not included)
    """
    if not chunk_ids:
        return {}

    try:
        db = get_firestore_client()
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        # Limit to 100 for Firestore batch limits
        chunk_ids = chunk_ids[:100]
        logger.info(f"Batch fetching {len(chunk_ids)} chunks from {collection}")

        # Create document references
        doc_refs = [db.collection(collection).document(cid) for cid in chunk_ids]

        # Batch fetch using get_all
        docs = db.get_all(doc_refs)

        result = {}
        for doc in docs:
            if doc.exists:
                chunk_data = doc.to_dict()
                chunk_data["id"] = doc.id
                result[doc.id] = chunk_data

        logger.info(f"Batch retrieved {len(result)} of {len(chunk_ids)} chunks")
        return result

    except Exception as e:
        logger.error(f"Failed to batch fetch chunks: {e}")
        return {}


def get_chunks_by_source_id(source_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get all chunks for a given source ID.

    Args:
        source_id: The source ID to find chunks for
        limit: Maximum chunks to return

    Returns:
        List of chunk dictionaries with knowledge cards
    """
    try:
        db = get_firestore_client()
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = (
            db.collection("kb_items")
            .where(filter=FieldFilter("source_id", "==", source_id))
            .limit(limit)
        )

        chunks = []
        for doc in query.stream():
            chunk_data = doc.to_dict()
            chunk_data["chunk_id"] = doc.id
            chunks.append(chunk_data)

        logger.info(f"Found {len(chunks)} chunks for source {source_id}")
        return chunks

    except Exception as e:
        logger.error(f"Failed to get chunks for source {source_id}: {e}")
        return []


def query_by_metadata(
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 20,
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
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        logger.info(
            f"Querying {collection} with filters: tags={tags}, author={author}, source={source}"
        )

        query = db.collection(collection)

        # Apply filters
        if tags:
            query = query.where("tags", "array_contains_any", tags)
        if author:
            query = query.where("author", "==", author)
        if source:
            query = query.where("source", "==", source)

        # Sort by created_at descending (most recent first)
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data["id"] = doc.id
            chunks.append(chunk_data)

        logger.info(f"Found {len(chunks)} chunks matching filters")
        return chunks

    except Exception as e:
        logger.error(f"Failed to query by metadata: {e}")
        return []


def normalize_url(url: str) -> str:
    """
    Normalize URL for comparison.

    Removes www prefix, trailing slashes, and query parameters.

    Args:
        url: URL to normalize

    Returns:
        Normalized URL string
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url.lower())
        # Remove www prefix
        host = parsed.netloc.replace("www.", "")
        # Remove trailing slash from path
        path = parsed.path.rstrip("/")
        # Rebuild without query params and fragment
        return f"{parsed.scheme}://{host}{path}"
    except Exception:
        return url.lower()


def find_by_source_url(url: str) -> Optional[Dict[str, Any]]:
    """
    Find a chunk by its source URL.

    Checks both exact match and normalized URL match.

    Args:
        url: Source URL to search for

    Returns:
        Chunk data if found, None otherwise
    """
    if not url:
        return None

    try:
        db = get_firestore_client()
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        # Try exact match first
        query = db.collection(collection).where("source_url", "==", url).limit(1)
        docs = list(query.stream())

        if docs:
            chunk_data = docs[0].to_dict()
            chunk_data["id"] = docs[0].id
            logger.debug(f"Found chunk by exact URL match: {docs[0].id}")
            return chunk_data

        # Try normalized URL match
        normalized = normalize_url(url)
        if normalized != url:
            query = (
                db.collection(collection).where("source_url", "==", normalized).limit(1)
            )
            docs = list(query.stream())

            if docs:
                chunk_data = docs[0].to_dict()
                chunk_data["id"] = docs[0].id
                logger.debug(f"Found chunk by normalized URL match: {docs[0].id}")
                return chunk_data

        return None

    except Exception as e:
        logger.warning(f"Failed to find chunk by source URL: {e}")
        return None


def find_chunks_by_title_prefix(
    title_prefix: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Find chunks whose title starts with the given prefix.

    Uses Firestore range query for efficient prefix matching.

    Args:
        title_prefix: Title prefix to search (case-insensitive)
        limit: Maximum results to return

    Returns:
        List of matching chunks
    """
    if not title_prefix or len(title_prefix) < 3:
        return []

    try:
        db = get_firestore_client()
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        # Firestore doesn't support case-insensitive queries directly
        # We'll fetch more results and filter client-side
        # This is acceptable for deduplication (not high-volume)

        # Get all chunks and filter by title (not ideal but necessary)
        # TODO: Add title_lower field to chunks for efficient querying
        query = db.collection(collection).limit(500)
        docs = query.stream()

        prefix_lower = title_prefix.lower()
        chunks = []

        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_title = chunk_data.get("title", "").lower()

            # Check if title contains the prefix or vice versa
            if prefix_lower in chunk_title or chunk_title in prefix_lower:
                chunk_data["id"] = doc.id
                chunks.append(chunk_data)

                if len(chunks) >= limit:
                    break

        logger.debug(
            f"Found {len(chunks)} chunks with title matching '{title_prefix[:20]}...'"
        )
        return chunks

    except Exception as e:
        logger.warning(f"Failed to find chunks by title prefix: {e}")
        return []


def find_nearest(
    embedding_vector: List[float],
    limit: int = 10,
    filters: Optional[Dict[str, Any]] = None,
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
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        logger.info(f"Executing vector search in {collection} (limit: {limit})")

        # Create vector query
        vector_query = db.collection(collection).find_nearest(
            vector_field="embedding",
            query_vector=Vector(embedding_vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
        )

        # TODO: Apply filters if provided (Firestore vector search filter support)
        # Note: Firestore vector search filtering is limited - may need post-processing

        docs = vector_query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data["id"] = doc.id
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
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

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
            if "source" in data and data["source"] is not None:
                unique_sources.add(data["source"])
            if "author" in data and data["author"] is not None:
                unique_authors.add(data["author"])
            if "tags" in data and data["tags"] is not None:
                # Filter out None values from tags list
                valid_tags = [tag for tag in data["tags"] if tag is not None]
                unique_tags.update(valid_tags)
            if "parent_doc_id" in data and data["parent_doc_id"] is not None:
                unique_parent_docs.add(data["parent_doc_id"])

        stats = {
            "total_chunks": total_chunks,
            "total_documents": len(unique_parent_docs),
            "sources": sorted(list(unique_sources)),
            "source_count": len(unique_sources),
            "authors": sorted(list(unique_authors)),
            "author_count": len(unique_authors),
            "tags": sorted(list(unique_tags)),
            "tag_count": len(unique_tags),
            "avg_chunks_per_doc": round(total_chunks / len(unique_parent_docs), 1)
            if unique_parent_docs
            else 0,
        }

        logger.info(
            f"Stats: {total_chunks} chunks, {len(unique_parent_docs)} documents"
        )
        return stats

    except Exception as e:
        logger.error(f"Failed to collect stats: {e}")
        return {
            "total_chunks": 0,
            "total_documents": 0,
            "sources": [],
            "source_count": 0,
            "authors": [],
            "author_count": 0,
            "tags": [],
            "tag_count": 0,
            "avg_chunks_per_doc": 0,
            "error": str(e),
        }


def query_by_date_range(
    start_date: str,
    end_date: str,
    limit: int = 20,
    tags: Optional[List[str]] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
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
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        # Parse dates
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        # End date is inclusive, so add 1 day and subtract microsecond
        end_dt = (
            datetime.strptime(end_date, "%Y-%m-%d")
            + timedelta(days=1)
            - timedelta(microseconds=1)
        )

        logger.info(
            f"Querying {collection} by date range: {start_date} to {end_date} (limit: {limit})"
        )

        query = db.collection(collection)

        # Apply date range filter
        query = query.where("created_at", ">=", start_dt)
        query = query.where("created_at", "<=", end_dt)

        # Apply optional metadata filters
        if tags:
            query = query.where("tags", "array_contains_any", tags)
        if author:
            query = query.where("author", "==", author)
        if source:
            query = query.where("source", "==", source)

        # Sort by created_at descending (most recent first)
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data["id"] = doc.id
            chunks.append(chunk_data)

        logger.info(
            f"Found {len(chunks)} chunks in date range {start_date} to {end_date}"
        )
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
    source: Optional[str] = None,
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
            start_dt = (now - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                microseconds=1
            )
        elif period == "last_3_days":
            start_dt = (now - timedelta(days=3)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end_dt = now
        elif period == "last_week" or period == "last_7_days":
            start_dt = (now - timedelta(days=7)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end_dt = now
        elif period == "last_month" or period == "last_30_days":
            start_dt = (now - timedelta(days=30)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end_dt = now
        else:
            logger.error(f"Unknown period: {period}")
            return []

        logger.info(f"Querying {period}: {start_dt} to {end_dt}")

        db = get_firestore_client()
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        query = db.collection(collection)

        # Apply date range filter
        query = query.where("created_at", ">=", start_dt)
        query = query.where("created_at", "<=", end_dt)

        # Apply optional metadata filters
        if tags:
            query = query.where("tags", "array_contains_any", tags)
        if author:
            query = query.where("author", "==", author)
        if source:
            query = query.where("source", "==", source)

        # Sort by created_at descending (most recent first)
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data["id"] = doc.id
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
            start_dt = (now - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            now = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "last_3_days":
            start_dt = (now - timedelta(days=3)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif period == "last_7_days" or period == "last_week":
            start_dt = (now - timedelta(days=7)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif period == "last_30_days" or period == "last_month":
            start_dt = (now - timedelta(days=30)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            logger.error(f"Unknown period: {period}")
            return {"error": f"Unknown period: {period}"}

        logger.info(f"Collecting activity summary for {period}")

        db = get_firestore_client()
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        # Query all chunks in period by actual reading time (last_highlighted_at)
        query = db.collection(collection)
        query = query.where("last_highlighted_at", ">=", start_dt)
        query = query.where("last_highlighted_at", "<=", now)
        query = query.order_by(
            "last_highlighted_at", direction=firestore.Query.DESCENDING
        )

        docs = query.stream()

        chunks_by_day = {}
        top_sources = {}
        top_authors = {}
        total_chunks = 0

        for doc in docs:
            data = doc.to_dict()
            total_chunks += 1

            # Group by day using last_highlighted_at (actual reading time)
            highlighted_at = data.get("last_highlighted_at")
            if highlighted_at:
                day_key = highlighted_at.strftime("%Y-%m-%d")
                chunks_by_day[day_key] = chunks_by_day.get(day_key, 0) + 1

            # Track sources
            source = data.get("source")
            if source:
                top_sources[source] = top_sources.get(source, 0) + 1

            # Track authors
            author = data.get("author")
            if author:
                top_authors[author] = top_authors.get(author, 0) + 1

        # Sort by count descending
        top_sources_sorted = sorted(
            top_sources.items(), key=lambda x: x[1], reverse=True
        )[:5]
        top_authors_sorted = sorted(
            top_authors.items(), key=lambda x: x[1], reverse=True
        )[:5]

        activity = {
            "period": period,
            "total_chunks_added": total_chunks,
            "days_with_activity": len(chunks_by_day),
            "chunks_by_day": dict(sorted(chunks_by_day.items())),  # Sort by date
            "top_sources": [{"source": s, "count": c} for s, c in top_sources_sorted],
            "top_authors": [{"author": a, "count": c} for a, c in top_authors_sorted],
        }

        logger.info(
            f"Activity summary: {total_chunks} chunks added in {len(chunks_by_day)} days"
        )
        return activity

    except Exception as e:
        logger.error(f"Failed to collect activity summary: {e}")
        return {
            "error": str(e),
            "period": period,
            "total_chunks_added": 0,
            "days_with_activity": 0,
            "chunks_by_day": {},
            "top_sources": [],
            "top_authors": [],
        }


def get_recently_added(limit: int = 10, days: int = 7) -> List[Dict[str, Any]]:
    """
    Get most recently added chunks (by ingestion time).

    Note: This queries by created_at (when chunk was added to KB), not by
    last_highlighted_at (when user actually read it). Use get_recently_read()
    for actual reading time.

    Args:
        limit: Maximum number of chunks to return
        days: Look back this many days

    Returns:
        List of chunks ordered by created_at DESC (most recent first)
    """
    try:
        db = get_firestore_client()
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        now = datetime.utcnow()
        start_dt = (now - timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        logger.info(f"Getting {limit} recently added chunks from last {days} days")

        query = db.collection(collection)
        query = query.where("created_at", ">=", start_dt)
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data["id"] = doc.id
            chunks.append(chunk_data)

        logger.info(f"Retrieved {len(chunks)} recently added chunks")
        return chunks

    except Exception as e:
        logger.error(f"Failed to get recently added chunks: {e}")
        return []


def get_recently_read(limit: int = 10, days: int = 7) -> List[Dict[str, Any]]:
    """
    Get most recently read chunks (by actual reading/highlight time).

    Queries by last_highlighted_at field which represents when the user
    actually made the highlight (reading time), not when it was synced.

    Args:
        limit: Maximum number of chunks to return
        days: Look back this many days

    Returns:
        List of chunks ordered by last_highlighted_at DESC (most recent first)
    """
    try:
        db = get_firestore_client()
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        now = datetime.utcnow()
        start_dt = (now - timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        logger.info(f"Getting {limit} recently read chunks from last {days} days")

        query = db.collection(collection)
        query = query.where("last_highlighted_at", ">=", start_dt)
        query = query.order_by(
            "last_highlighted_at", direction=firestore.Query.DESCENDING
        )
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            chunk_data["id"] = doc.id
            chunks.append(chunk_data)

        logger.info(f"Retrieved {len(chunks)} recently read chunks")
        return chunks

    except Exception as e:
        logger.error(f"Failed to get recently read chunks: {e}")
        # Fallback to created_at if last_highlighted_at not available
        logger.info("Falling back to get_recently_added")
        return get_recently_added(limit=limit, days=days)


# ============================================================================
# Configuration Management (Story 3.5)
# ============================================================================

# Default domain whitelist for reading recommendations
DEFAULT_QUALITY_DOMAINS = [
    "martinfowler.com",
    "infoq.com",
    "thoughtworks.com",
    "thenewstack.io",
    "oreilly.com",
    "acm.org",
    "anthropic.com",
    "openai.com",
    "huggingface.co",
    "hbr.org",
    "mckinsey.com",
    "heise.de",
    "golem.de",
    "arxiv.org",
]

# ============================================================================
# Story 3.9: Hot Sites Categories
# ============================================================================

# Curated source lists for focused discovery (research-based, Dec 2025)
DEFAULT_HOT_SITES = {
    "tech": {
        "description": "Software architecture, platform engineering, DevOps, and general tech",
        "domains": [
            "martinfowler.com",
            "thoughtworks.com",
            "infoq.com",
            "thenewstack.io",
            "dev.to",
            "news.ycombinator.com",
            "stackoverflow.blog",
            "github.blog",
            "netflixtechblog.com",
            "engineering.atspotify.com",
            "uber.com/blog",
            "eng.lyft.com",
            "slack.engineering",
            "stripe.com/blog/engineering",
            "cloudflare.com/blog",
            "blog.discord.com",
            "devops.com",
            "platformengineering.org",
            "humanitec.com/blog",
            "arstechnica.com",
            "wired.com",
            "theverge.com",
            "simonwillison.net",
            "newsletter.pragmaticengineer.com",
            "bytebytego.com",
        ],
    },
    "tech_de": {
        "description": "German tech news and professional IT sources",
        "domains": [
            "heise.de",
            "golem.de",
            "t3n.de",
            "the-decoder.de",
            "computerbase.de",
            "heise.de/ix",
        ],
    },
    "ai": {
        "description": "AI/ML research, LLMs, agents, and AI-powered development",
        "domains": [
            "anthropic.com",
            "openai.com",
            "huggingface.co",
            "deepmind.google",
            "ai.meta.com",
            "ai.google",
            "microsoft.com/en-us/research",
            "nvidia.com/blog",
            "lilianweng.github.io",
            "karpathy.ai",
            "simonwillison.net",
            "latent.space",
            "technologyreview.com",
            "unite.ai",
            "towardsdatascience.com",
            "thesequence.substack.com",
            "importai.substack.com",
        ],
    },
    "devops": {
        "description": "DevOps, SRE, platform engineering, and developer experience",
        "domains": [
            "devops.com",
            "thenewstack.io",
            "platformengineering.org",
            "humanitec.com/blog",
            "infoq.com",
            "martinfowler.com",
            "slack.engineering",
            "netflixtechblog.com",
            "aws.amazon.com/blogs/devops",
            "devblogs.microsoft.com/devops",
            "cloud.google.com/blog",
            "kubernetes.io/blog",
            "cncf.io/blog",
        ],
    },
    "business": {
        "description": "Business strategy, tech leadership, and product management",
        "domains": [
            "hbr.org",
            "mckinsey.com",
            "bcg.com",
            "stratechery.com",
            "a16z.com",
            "sequoiacap.com",
            "firstround.com/review",
            "nfx.com",
            "lennysnewsletter.com",
            "svpg.com",
            "productboard.com/blog",
            "intercom.com/blog",
            "exponentialview.co",
        ],
    },
}

DEFAULT_EXCLUDED_DOMAINS = ["medium.com"]


def get_recommendation_config() -> Dict[str, Any]:
    """
    Get reading recommendation configuration from Firestore.

    Fetches config/recommendation_domains document with domain whitelist.
    Creates default config if document doesn't exist.

    Story 3.5: AI-Powered Reading Recommendations

    Returns:
        Dictionary with:
        - quality_domains: List of whitelisted domains
        - excluded_domains: List of blocked domains
        - last_updated: Timestamp of last update
        - updated_by: Who made the last update
    """
    try:
        db = get_firestore_client()

        logger.info("Fetching recommendation config from config/recommendation_domains")

        doc_ref = db.collection("config").document("recommendation_domains")
        doc = doc_ref.get()

        if not doc.exists:
            logger.info("Config not found, creating default configuration")
            # Create default config
            default_config = {
                "quality_domains": DEFAULT_QUALITY_DOMAINS,
                "excluded_domains": DEFAULT_EXCLUDED_DOMAINS,
                "last_updated": datetime.utcnow(),
                "updated_by": "initial_setup",
            }
            doc_ref.set(default_config)
            return default_config

        config = doc.to_dict()
        logger.info(
            f"Retrieved recommendation config: {len(config.get('quality_domains', []))} domains"
        )
        return config

    except Exception as e:
        logger.error(f"Failed to get recommendation config: {e}")
        # Return defaults on error
        return {
            "quality_domains": DEFAULT_QUALITY_DOMAINS,
            "excluded_domains": DEFAULT_EXCLUDED_DOMAINS,
            "error": str(e),
        }


def update_recommendation_config(
    add_domains: Optional[List[str]] = None,
    remove_domains: Optional[List[str]] = None,
    add_excluded: Optional[List[str]] = None,
    remove_excluded: Optional[List[str]] = None,
    updated_by: str = "mcp_tool",
) -> Dict[str, Any]:
    """
    Update reading recommendation configuration in Firestore.

    Modifies config/recommendation_domains document.

    Story 3.5: AI-Powered Reading Recommendations

    Args:
        add_domains: Domains to add to quality_domains whitelist
        remove_domains: Domains to remove from quality_domains whitelist
        add_excluded: Domains to add to excluded_domains blocklist
        remove_excluded: Domains to remove from excluded_domains blocklist
        updated_by: Identifier for who made the update

    Returns:
        Dictionary with updated configuration and operation summary
    """
    try:
        db = get_firestore_client()

        logger.info("Updating recommendation config")

        # Get current config
        doc_ref = db.collection("config").document("recommendation_domains")
        doc = doc_ref.get()

        if doc.exists:
            current = doc.to_dict()
        else:
            current = {
                "quality_domains": DEFAULT_QUALITY_DOMAINS.copy(),
                "excluded_domains": DEFAULT_EXCLUDED_DOMAINS.copy(),
            }

        # Track changes
        changes = {
            "domains_added": [],
            "domains_removed": [],
            "excluded_added": [],
            "excluded_removed": [],
        }

        # Update quality_domains
        quality_domains = set(current.get("quality_domains", []))

        if add_domains:
            for domain in add_domains:
                domain = domain.lower().strip()
                if domain and domain not in quality_domains:
                    quality_domains.add(domain)
                    changes["domains_added"].append(domain)

        if remove_domains:
            for domain in remove_domains:
                domain = domain.lower().strip()
                if domain in quality_domains:
                    quality_domains.discard(domain)
                    changes["domains_removed"].append(domain)

        # Update excluded_domains
        excluded_domains = set(current.get("excluded_domains", []))

        if add_excluded:
            for domain in add_excluded:
                domain = domain.lower().strip()
                if domain and domain not in excluded_domains:
                    excluded_domains.add(domain)
                    changes["excluded_added"].append(domain)

        if remove_excluded:
            for domain in remove_excluded:
                domain = domain.lower().strip()
                if domain in excluded_domains:
                    excluded_domains.discard(domain)
                    changes["excluded_removed"].append(domain)

        # Prepare updated config
        updated_config = {
            "quality_domains": sorted(list(quality_domains)),
            "excluded_domains": sorted(list(excluded_domains)),
            "last_updated": datetime.utcnow(),
            "updated_by": updated_by,
        }

        # Save to Firestore
        doc_ref.set(updated_config)

        logger.info(
            f"Updated recommendation config: "
            f"+{len(changes['domains_added'])} -{len(changes['domains_removed'])} domains"
        )

        return {"success": True, "config": updated_config, "changes": changes}

    except Exception as e:
        logger.error(f"Failed to update recommendation config: {e}")
        return {"success": False, "error": str(e)}


def get_recent_chunks_with_cards(
    days: int = 14, limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get recent chunks that have knowledge cards for recommendation query generation.

    Story 3.5: AI-Powered Reading Recommendations

    Args:
        days: Look back this many days
        limit: Maximum chunks to return

    Returns:
        List of chunk dictionaries with knowledge_card field
    """
    try:
        db = get_firestore_client()
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        now = datetime.utcnow()
        start_dt = (now - timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        logger.info(f"Fetching recent chunks with knowledge cards (last {days} days)")

        query = db.collection(collection)
        query = query.where("created_at", ">=", start_dt)
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        docs = query.stream()

        chunks = []
        for doc in docs:
            chunk_data = doc.to_dict()
            # Only include chunks with knowledge cards
            if chunk_data.get("knowledge_card"):
                chunk_data["id"] = doc.id
                chunks.append(chunk_data)

        logger.info(f"Retrieved {len(chunks)} recent chunks with knowledge cards")
        return chunks

    except Exception as e:
        logger.error(f"Failed to get recent chunks with cards: {e}")
        return []


# ============================================================================
# Ranking Configuration (Story 3.8)
# ============================================================================

DEFAULT_RANKING_WEIGHTS = {
    "relevance": 0.50,
    "recency": 0.25,
    "depth": 0.15,
    "authority": 0.10,
}

DEFAULT_RANKING_SETTINGS = {
    "recency": {"half_life_days": 90, "max_age_days": 365, "tavily_days_filter": 180},
    "diversity": {
        "shown_ttl_days": 7,
        "novelty_bonus": 0.10,
        "domain_duplicate_penalty": 0.05,
        "max_per_domain": 2,
        "stochastic_temperature": 0.3,
    },
    "slots": {
        "relevance_count": 2,
        "serendipity_count": 1,
        "stale_refresh_count": 1,
        "trending_count": 1,
    },
}


def get_ranking_config() -> Dict[str, Any]:
    """
    Get ranking configuration from Firestore.

    Story 3.8 AC#7: Configuration management.

    Fetches config/ranking_weights and config/ranking_settings documents.
    Creates defaults if documents don't exist.

    Returns:
        Dictionary with:
        - weights: Factor weights (relevance, recency, depth, authority)
        - settings: Recency, diversity, and slot settings
        - last_updated: Timestamp of last update
    """
    try:
        db = get_firestore_client()

        # Fetch ranking weights
        weights_ref = db.collection("config").document("ranking_weights")
        weights_doc = weights_ref.get()

        if weights_doc.exists:
            weights = weights_doc.to_dict()
        else:
            # Create default weights
            logger.info("Creating default ranking weights config")
            weights = {
                **DEFAULT_RANKING_WEIGHTS,
                "last_updated": datetime.utcnow(),
                "updated_by": "initial_setup",
            }
            weights_ref.set(weights)

        # Fetch ranking settings
        settings_ref = db.collection("config").document("ranking_settings")
        settings_doc = settings_ref.get()

        if settings_doc.exists:
            settings = settings_doc.to_dict()
        else:
            # Create default settings
            logger.info("Creating default ranking settings config")
            settings = {
                **DEFAULT_RANKING_SETTINGS,
                "last_updated": datetime.utcnow(),
                "updated_by": "initial_setup",
            }
            settings_ref.set(settings)

        logger.info("Retrieved ranking configuration")

        return {
            "weights": {
                "relevance": weights.get(
                    "relevance", DEFAULT_RANKING_WEIGHTS["relevance"]
                ),
                "recency": weights.get("recency", DEFAULT_RANKING_WEIGHTS["recency"]),
                "depth": weights.get("depth", DEFAULT_RANKING_WEIGHTS["depth"]),
                "authority": weights.get(
                    "authority", DEFAULT_RANKING_WEIGHTS["authority"]
                ),
            },
            "settings": {
                "recency": settings.get("recency", DEFAULT_RANKING_SETTINGS["recency"]),
                "diversity": settings.get(
                    "diversity", DEFAULT_RANKING_SETTINGS["diversity"]
                ),
                "slots": settings.get("slots", DEFAULT_RANKING_SETTINGS["slots"]),
            },
            "weights_last_updated": str(weights.get("last_updated", "")),
            "settings_last_updated": str(settings.get("last_updated", "")),
        }

    except Exception as e:
        logger.error(f"Failed to get ranking config: {e}")
        # Return defaults on error
        return {
            "weights": DEFAULT_RANKING_WEIGHTS,
            "settings": DEFAULT_RANKING_SETTINGS,
            "error": str(e),
        }


# Default recommendations settings
DEFAULT_RECOMMENDATIONS_CONFIG = {
    "hot_sites": "tech",
    "tavily_days": 30,
    "limit": 10,
    "topics": ["AI agents", "platform engineering", "developer productivity"],
}


def get_recommendations_defaults() -> Dict[str, Any]:
    """
    Get recommendations defaults from Firestore.

    Story 7.2: Simplified recommendations interface.

    Fetches config/recommendations document with default settings.
    Creates defaults if document doesn't exist.

    Returns:
        Dictionary with:
        - hot_sites: Default hot_sites category (e.g., "tech")
        - tavily_days: Days to search back (e.g., 30)
        - limit: Max recommendations (e.g., 10)
        - topics: List of focus topics for LLM query generation
    """
    try:
        db = get_firestore_client()

        logger.info("Fetching recommendations defaults from config/recommendations")

        doc_ref = db.collection("config").document("recommendations")
        doc = doc_ref.get()

        if not doc.exists:
            logger.info("Recommendations config not found, creating defaults")
            default_config = {
                **DEFAULT_RECOMMENDATIONS_CONFIG,
                "last_updated": datetime.utcnow(),
                "updated_by": "initial_setup",
            }
            doc_ref.set(default_config)
            return default_config

        config = doc.to_dict()
        logger.info(
            f"Retrieved recommendations defaults: hot_sites={config.get('hot_sites')}, "
            f"tavily_days={config.get('tavily_days')}, topics={len(config.get('topics', []))}"
        )
        return config

    except Exception as e:
        logger.error(f"Failed to get recommendations defaults: {e}")
        return {**DEFAULT_RECOMMENDATIONS_CONFIG, "error": str(e)}


def update_ranking_config(
    weights: Optional[Dict[str, float]] = None,
    settings: Optional[Dict[str, Any]] = None,
    updated_by: str = "mcp_tool",
) -> Dict[str, Any]:
    """
    Update ranking configuration in Firestore.

    Story 3.8 AC#7: Configuration management.

    Args:
        weights: New factor weights (must sum to 1.0)
        settings: New ranking settings (recency, diversity, slots)
        updated_by: Identifier for who made the update

    Returns:
        Dictionary with:
        - success: Boolean
        - config: Updated configuration
        - error: Error message if failed
    """
    try:
        db = get_firestore_client()

        changes = {}

        # Update weights if provided
        if weights:
            # Validate weights sum to 1.0
            weight_sum = sum(weights.values())
            if abs(weight_sum - 1.0) > 0.01:
                return {
                    "success": False,
                    "error": f"Weights must sum to 1.0, got {weight_sum}",
                }

            weights_ref = db.collection("config").document("ranking_weights")
            weights_data = {
                **weights,
                "last_updated": datetime.utcnow(),
                "updated_by": updated_by,
            }
            weights_ref.set(weights_data, merge=True)
            changes["weights_updated"] = True
            logger.info(f"Updated ranking weights: {weights}")

        # Update settings if provided
        if settings:
            settings_ref = db.collection("config").document("ranking_settings")
            settings_data = {
                **settings,
                "last_updated": datetime.utcnow(),
                "updated_by": updated_by,
            }
            settings_ref.set(settings_data, merge=True)
            changes["settings_updated"] = True
            logger.info(f"Updated ranking settings")

        # Fetch updated config
        updated_config = get_ranking_config()

        return {"success": True, "config": updated_config, "changes": changes}

    except Exception as e:
        logger.error(f"Failed to update ranking config: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Shown Recommendations Tracking (Story 3.8)
# ============================================================================

DEFAULT_SHOWN_TTL_DAYS = 7


def record_shown_recommendations(
    user_id: str,
    recommendations: List[Dict[str, Any]],
    ttl_days: int = DEFAULT_SHOWN_TTL_DAYS,
) -> Dict[str, Any]:
    """
    Record shown recommendations to Firestore for deduplication.

    Story 3.8 AC#3, AC#6: Track shown URLs to avoid repetition.

    Creates documents in shown_recommendations/{user_id}/items collection
    with TTL-based expiration for automatic cleanup.

    Args:
        user_id: User identifier (or "default" for single-user)
        recommendations: List of recommendation dicts with url, slot, score
        ttl_days: Days until expiration (default 7)

    Returns:
        Dictionary with:
        - success: Boolean
        - recorded_count: Number of URLs recorded
        - error: Error message if failed
    """
    try:
        import hashlib
        from datetime import timedelta

        db = get_firestore_client()

        now = datetime.utcnow()
        expires_at = now + timedelta(days=ttl_days)

        recorded = 0
        batch = db.batch()

        for rec in recommendations:
            url = rec.get("url")
            if not url:
                continue

            # Create URL hash for document ID (Firestore-safe)
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
            doc_id = f"{url_hash}_{now.strftime('%Y%m%d%H%M%S')}"

            doc_ref = (
                db.collection("shown_recommendations")
                .document(user_id)
                .collection("items")
                .document(doc_id)
            )

            doc_data = {
                "url": url,
                "url_hash": url_hash,
                "shown_at": now,
                "expires_at": expires_at,
                "slot_type": rec.get("slot", "UNKNOWN"),
                "combined_score": rec.get("combined_score", 0),
                "final_score": rec.get("final_score", 0),
            }

            batch.set(doc_ref, doc_data)
            recorded += 1

        # Commit batch
        if recorded > 0:
            batch.commit()
            logger.info(f"Recorded {recorded} shown recommendations for user {user_id}")

        return {
            "success": True,
            "recorded_count": recorded,
            "expires_at": expires_at.isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to record shown recommendations: {e}")
        return {"success": False, "recorded_count": 0, "error": str(e)}


def get_shown_urls(user_id: str, ttl_days: int = DEFAULT_SHOWN_TTL_DAYS) -> List[str]:
    """
    Get URLs shown to user within TTL period.

    Story 3.8 AC#6: Exclude previously shown recommendations.

    Args:
        user_id: User identifier (or "default" for single-user)
        ttl_days: Look back this many days (default 7)

    Returns:
        List of URLs shown within TTL period
    """
    try:
        from datetime import timedelta

        db = get_firestore_client()

        now = datetime.utcnow()
        cutoff = now - timedelta(days=ttl_days)

        logger.info(f"Fetching shown URLs for user {user_id} since {cutoff}")

        # Query items collection for non-expired entries
        query = (
            db.collection("shown_recommendations").document(user_id).collection("items")
        )
        query = query.where("shown_at", ">=", cutoff)

        docs = query.stream()

        urls = []
        for doc in docs:
            data = doc.to_dict()
            url = data.get("url")
            if url:
                urls.append(url)

        logger.info(f"Found {len(urls)} shown URLs for user {user_id}")
        return urls

    except Exception as e:
        logger.error(f"Failed to get shown URLs: {e}")
        return []


def cleanup_expired_shown_recommendations(user_id: str = "default") -> Dict[str, Any]:
    """
    Clean up expired shown recommendation records.

    Story 3.8: TTL-based cleanup (alternative to Firestore TTL policy).

    Note: If using Firestore TTL policy (recommended), this is not needed.
    This function provides manual cleanup for development/testing.

    Args:
        user_id: User identifier (or "default" for single-user)

    Returns:
        Dictionary with cleanup results
    """
    try:
        db = get_firestore_client()

        now = datetime.utcnow()

        # Query expired items
        query = (
            db.collection("shown_recommendations").document(user_id).collection("items")
        )
        query = query.where("expires_at", "<", now)

        docs = query.stream()

        deleted = 0
        batch = db.batch()

        for doc in docs:
            batch.delete(doc.reference)
            deleted += 1

            # Commit in batches of 500 (Firestore limit)
            if deleted % 500 == 0:
                batch.commit()
                batch = db.batch()

        # Final commit
        if deleted % 500 != 0:
            batch.commit()

        logger.info(
            f"Cleaned up {deleted} expired shown recommendations for user {user_id}"
        )

        return {"success": True, "deleted_count": deleted}

    except Exception as e:
        logger.error(f"Failed to cleanup expired recommendations: {e}")
        return {"success": False, "deleted_count": 0, "error": str(e)}


# ============================================================================
# Hot Sites Configuration (Story 3.9)
# ============================================================================


def get_hot_sites_config() -> Dict[str, Any]:
    """
    Get hot sites configuration from Firestore.

    Story 3.9 AC#4: Hot site categories stored in Firestore

    Fetches config/hot_sites document with category→domain mappings.
    Creates default config if document doesn't exist.

    Returns:
        Dictionary with:
        - categories: Dict mapping category name to domain list
        - descriptions: Dict mapping category name to description
        - last_updated: Timestamp of last update
        - updated_by: Who made the last update
    """
    try:
        db = get_firestore_client()

        logger.info("Fetching hot sites config from config/hot_sites")

        doc_ref = db.collection("config").document("hot_sites")
        doc = doc_ref.get()

        if not doc.exists:
            logger.info("Hot sites config not found, creating default configuration")
            # Create default config from DEFAULT_HOT_SITES
            categories = {}
            descriptions = {}
            for cat_name, cat_data in DEFAULT_HOT_SITES.items():
                categories[cat_name] = cat_data["domains"]
                descriptions[cat_name] = cat_data["description"]

            default_config = {
                "categories": categories,
                "descriptions": descriptions,
                "last_updated": datetime.utcnow(),
                "updated_by": "initial_setup",
            }
            doc_ref.set(default_config)
            return default_config

        config = doc.to_dict()

        # Calculate total domains
        total_domains = sum(
            len(domains) for domains in config.get("categories", {}).values()
        )
        logger.info(
            f"Retrieved hot sites config: {len(config.get('categories', {}))} categories, {total_domains} total domains"
        )

        return config

    except Exception as e:
        logger.error(f"Failed to get hot sites config: {e}")
        # Return defaults on error
        categories = {}
        descriptions = {}
        for cat_name, cat_data in DEFAULT_HOT_SITES.items():
            categories[cat_name] = cat_data["domains"]
            descriptions[cat_name] = cat_data["description"]
        return {"categories": categories, "descriptions": descriptions, "error": str(e)}


def update_hot_sites_config(
    category: str,
    add_domains: Optional[List[str]] = None,
    remove_domains: Optional[List[str]] = None,
    description: Optional[str] = None,
    updated_by: str = "mcp_tool",
) -> Dict[str, Any]:
    """
    Update hot sites configuration for a specific category.

    Story 3.9 AC#4: MCP tool to modify categories

    Args:
        category: Category name (tech, tech_de, ai, devops, business)
        add_domains: Domains to add to the category
        remove_domains: Domains to remove from the category
        description: Optional new description for the category
        updated_by: Identifier for who made the update

    Returns:
        Dictionary with:
        - success: Boolean
        - category: Category that was updated
        - domains: Updated domain list for this category
        - changes: Summary of changes made
    """
    try:
        db = get_firestore_client()

        logger.info(f"Updating hot sites config for category: {category}")

        # Get current config
        doc_ref = db.collection("config").document("hot_sites")
        doc = doc_ref.get()

        if doc.exists:
            current = doc.to_dict()
        else:
            # Initialize from defaults
            categories = {}
            descriptions = {}
            for cat_name, cat_data in DEFAULT_HOT_SITES.items():
                categories[cat_name] = cat_data["domains"]
                descriptions[cat_name] = cat_data["description"]
            current = {"categories": categories, "descriptions": descriptions}

        # Get current category domains (or empty list for new category)
        categories = current.get("categories", {})
        descriptions = current.get("descriptions", {})

        domain_set = set(categories.get(category, []))

        # Track changes
        changes = {
            "domains_added": [],
            "domains_removed": [],
            "description_updated": False,
        }

        # Add domains
        if add_domains:
            for domain in add_domains:
                domain = domain.lower().strip()
                if domain and domain not in domain_set:
                    domain_set.add(domain)
                    changes["domains_added"].append(domain)

        # Remove domains
        if remove_domains:
            for domain in remove_domains:
                domain = domain.lower().strip()
                if domain in domain_set:
                    domain_set.discard(domain)
                    changes["domains_removed"].append(domain)

        # Update description
        if description is not None:
            descriptions[category] = description
            changes["description_updated"] = True

        # Update category
        categories[category] = sorted(list(domain_set))

        # Prepare updated config
        updated_config = {
            "categories": categories,
            "descriptions": descriptions,
            "last_updated": datetime.utcnow(),
            "updated_by": updated_by,
        }

        # Save to Firestore
        doc_ref.set(updated_config)

        logger.info(
            f"Updated hot sites category '{category}': "
            f"+{len(changes['domains_added'])} -{len(changes['domains_removed'])} domains"
        )

        return {
            "success": True,
            "category": category,
            "domains": categories[category],
            "domain_count": len(categories[category]),
            "description": descriptions.get(category, ""),
            "changes": changes,
        }

    except Exception as e:
        logger.error(f"Failed to update hot sites config: {e}")
        return {"success": False, "category": category, "error": str(e)}


def get_hot_sites_domains(category: str) -> List[str]:
    """
    Get domain list for a hot sites category.

    Story 3.9 AC#2: Map hot_sites parameter to domain list

    Args:
        category: Category name or "all" for union of all categories

    Returns:
        List of domains for the category (empty list if not found)
    """
    try:
        config = get_hot_sites_config()
        categories = config.get("categories", {})

        if category == "all":
            # Union of all category domains
            all_domains = set()
            for domains in categories.values():
                all_domains.update(domains)
            return sorted(list(all_domains))

        return categories.get(category, [])

    except Exception as e:
        logger.error(f"Failed to get hot sites domains for {category}: {e}")
        return []


def get_kb_credibility_signals() -> Dict[str, Any]:
    """
    Get all authors and source domains from the KB for credibility scoring.

    Story 3.5: AI-Powered Reading Recommendations

    Extracts unique authors and domains from source_url to identify
    trusted sources based on user's reading history.

    Returns:
        Dictionary with:
        - authors: List of unique author names (sorted by frequency)
        - domains: List of unique domains from source_url (sorted by frequency)
        - author_count: Total unique authors
        - domain_count: Total unique domains
    """
    try:
        from collections import Counter
        from urllib.parse import urlparse

        db = get_firestore_client()
        collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

        logger.info("Fetching KB credibility signals (all authors and source domains)")

        docs = db.collection(collection).stream()

        authors = Counter()
        domains = Counter()

        for doc in docs:
            data = doc.to_dict()

            # Count authors
            author = data.get("author")
            if author and author.strip():
                authors[author.strip()] += 1

            # Extract domain from source_url
            source_url = data.get("source_url")
            if source_url:
                try:
                    parsed = urlparse(source_url)
                    domain = parsed.netloc.replace("www.", "")
                    if domain and domain not in ("readwise.io",):  # Skip meta-sources
                        domains[domain] += 1
                except Exception:
                    pass

        # Get top authors and domains (limit to reasonable size for matching)
        top_authors = [author for author, _ in authors.most_common(100)]
        top_domains = [domain for domain, _ in domains.most_common(50)]

        result = {
            "authors": top_authors,
            "domains": top_domains,
            "author_count": len(authors),
            "domain_count": len(domains),
        }

        logger.info(
            f"KB credibility signals: {len(top_authors)} authors, "
            f"{len(top_domains)} domains"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to get KB credibility signals: {e}")
        return {
            "authors": [],
            "domains": [],
            "author_count": 0,
            "domain_count": 0,
            "error": str(e),
        }


# ============================================================================
# Relationship Functions (Story 4.3)
# ============================================================================


def get_chunk_relationships(chunk_id: str) -> List[Dict[str, Any]]:
    """
    Get all relationships for a specific chunk (both as source and target).

    Args:
        chunk_id: The chunk ID to find relationships for

    Returns:
        List of relationships with type, confidence, explanation, and connected chunk info
    """
    try:
        db = get_firestore_client()
        relationships = []

        # Get relationships where this chunk is the source
        source_query = db.collection("relationships").where(
            "source_chunk_id", "==", chunk_id
        )
        for doc in source_query.stream():
            data = doc.to_dict()
            relationships.append(
                {
                    "relationship_id": doc.id,
                    "direction": "outgoing",
                    "connected_chunk_id": data.get("target_chunk_id"),
                    "type": data.get("type"),
                    "confidence": data.get("confidence"),
                    "explanation": data.get("explanation"),
                    "source_context": data.get("source_context", {}),
                }
            )

        # Get relationships where this chunk is the target
        target_query = db.collection("relationships").where(
            "target_chunk_id", "==", chunk_id
        )
        for doc in target_query.stream():
            data = doc.to_dict()
            relationships.append(
                {
                    "relationship_id": doc.id,
                    "direction": "incoming",
                    "connected_chunk_id": data.get("source_chunk_id"),
                    "type": data.get("type"),
                    "confidence": data.get("confidence"),
                    "explanation": data.get("explanation"),
                    "source_context": data.get("source_context", {}),
                }
            )

        logger.info(f"Found {len(relationships)} relationships for chunk {chunk_id}")
        return relationships

    except Exception as e:
        logger.error(f"Failed to get relationships for chunk {chunk_id}: {e}")
        return []


def get_source_relationships(source_id: str) -> List[Dict[str, Any]]:
    """
    Get all relationships for chunks belonging to a specific source.

    Args:
        source_id: The source ID to find relationships for

    Returns:
        List of cross-source relationships aggregated by target source
    """
    try:
        db = get_firestore_client()

        # Get source document to find chunk IDs
        source_doc = db.collection("sources").document(source_id).get()
        if not source_doc.exists:
            logger.warning(f"Source not found: {source_id}")
            return []

        source_data = source_doc.to_dict()
        chunk_ids = source_data.get("chunk_ids", [])

        if not chunk_ids:
            return []

        # Collect all relationships for this source's chunks
        relationships_by_target_source = {}

        for chunk_id in chunk_ids:
            chunk_rels = get_chunk_relationships(chunk_id)
            for rel in chunk_rels:
                # Get target chunk to find its source
                target_chunk_id = rel["connected_chunk_id"]
                target_chunk = get_chunk_by_id(target_chunk_id)
                if not target_chunk:
                    continue

                target_source_id = target_chunk.get("source_id", "unknown")

                # Skip same-source relationships
                if target_source_id == source_id:
                    continue

                # Aggregate by target source
                if target_source_id not in relationships_by_target_source:
                    relationships_by_target_source[target_source_id] = {
                        "target_source_id": target_source_id,
                        "target_title": target_chunk.get("title", "Unknown"),
                        "target_author": target_chunk.get("author", "Unknown"),
                        "relationship_types": {},
                        "examples": [],
                    }

                # Count relationship types
                rel_type = rel["type"]
                if (
                    rel_type
                    not in relationships_by_target_source[target_source_id][
                        "relationship_types"
                    ]
                ):
                    relationships_by_target_source[target_source_id][
                        "relationship_types"
                    ][rel_type] = 0
                relationships_by_target_source[target_source_id]["relationship_types"][
                    rel_type
                ] += 1

                # Keep first few examples
                if (
                    len(relationships_by_target_source[target_source_id]["examples"])
                    < 3
                ):
                    relationships_by_target_source[target_source_id]["examples"].append(
                        {"type": rel_type, "explanation": rel["explanation"]}
                    )

        result = list(relationships_by_target_source.values())
        logger.info(
            f"Found relationships to {len(result)} other sources for {source_id}"
        )
        return result

    except Exception as e:
        logger.error(f"Failed to get source relationships for {source_id}: {e}")
        return []


def list_sources(limit: int = 50) -> List[Dict[str, Any]]:
    """
    List all sources with metadata.

    Args:
        limit: Maximum sources to return

    Returns:
        List of sources with title, author, chunk count
    """
    try:
        db = get_firestore_client()

        sources = []
        for doc in db.collection("sources").limit(limit).stream():
            data = doc.to_dict()
            sources.append(
                {
                    "source_id": doc.id,
                    "title": data.get("title", "Untitled"),
                    "author": data.get("author", "Unknown"),
                    "type": data.get("type", "unknown"),
                    "chunk_count": data.get(
                        "chunk_count", len(data.get("chunk_ids", []))
                    ),
                    "tags": data.get("tags", []),
                }
            )

        logger.info(f"Listed {len(sources)} sources")
        return sources

    except Exception as e:
        logger.error(f"Failed to list sources: {e}")
        return []


def get_source_by_id(source_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific source with its chunks.

    Story 3.10: Uses batch read for chunks (1 Firestore read instead of N).

    Args:
        source_id: Source document ID

    Returns:
        Source data with chunk details including full knowledge cards, or None if not found
    """
    try:
        db = get_firestore_client()

        doc = db.collection("sources").document(source_id).get()
        if not doc.exists:
            return None

        data = doc.to_dict()

        # Story 3.10: Batch fetch chunks (fixes N+1 query problem)
        chunk_ids = data.get("chunk_ids", [])
        chunk_ids_to_fetch = chunk_ids[:20]  # Limit to first 20 chunks
        chunks_data = get_chunks_batch(chunk_ids_to_fetch)

        # Format chunks with full knowledge cards
        chunks = []
        for chunk_id in chunk_ids_to_fetch:
            chunk = chunks_data.get(chunk_id)
            if chunk:
                kc = chunk.get("knowledge_card", {})
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "chunk_index": chunk.get("chunk_index", 0),
                        # Story 3.10: Return full knowledge card, not just summary
                        "knowledge_card": {
                            "summary": kc.get("summary", "") if kc else "",
                            "takeaways": kc.get("takeaways", []) if kc else [],
                        },
                    }
                )

        return {
            "source_id": doc.id,
            "title": data.get("title", "Untitled"),
            "author": data.get("author", "Unknown"),
            "type": data.get("type", "unknown"),
            "chunk_count": len(chunk_ids),
            "tags": data.get("tags", []),
            "chunks": sorted(chunks, key=lambda x: x["chunk_index"]),
            "created_at": data.get("created_at"),
        }

    except Exception as e:
        logger.error(f"Failed to get source {source_id}: {e}")
        return None


def find_contradictions(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Find chunks with contradicting relationships.

    Args:
        limit: Maximum contradictions to return

    Returns:
        List of contradiction pairs with explanations
    """
    try:
        db = get_firestore_client()

        contradictions = []
        query = (
            db.collection("relationships")
            .where("type", "==", "contradicts")
            .limit(limit)
        )

        for doc in query.stream():
            data = doc.to_dict()

            source_chunk = get_chunk_by_id(data.get("source_chunk_id"))
            target_chunk = get_chunk_by_id(data.get("target_chunk_id"))

            if source_chunk and target_chunk:
                contradictions.append(
                    {
                        "chunk_a": {
                            "chunk_id": data.get("source_chunk_id"),
                            "title": source_chunk.get("title"),
                            "author": source_chunk.get("author"),
                            "summary": source_chunk.get("knowledge_card", {}).get(
                                "summary", ""
                            ),
                        },
                        "chunk_b": {
                            "chunk_id": data.get("target_chunk_id"),
                            "title": target_chunk.get("title"),
                            "author": target_chunk.get("author"),
                            "summary": target_chunk.get("knowledge_card", {}).get(
                                "summary", ""
                            ),
                        },
                        "explanation": data.get("explanation"),
                        "confidence": data.get("confidence"),
                    }
                )

        logger.info(f"Found {len(contradictions)} contradictions")
        return contradictions

    except Exception as e:
        logger.error(f"Failed to find contradictions: {e}")
        return []


def get_relationship_stats() -> Dict[str, Any]:
    """
    Get statistics about relationships in the knowledge base.

    Returns:
        Dictionary with relationship counts by type
    """
    try:
        db = get_firestore_client()

        # Count by type
        type_counts = {}
        for doc in db.collection("relationships").stream():
            rel_type = doc.to_dict().get("type", "unknown")
            type_counts[rel_type] = type_counts.get(rel_type, 0) + 1

        total = sum(type_counts.values())

        return {"total_relationships": total, "by_type": type_counts}

    except Exception as e:
        logger.error(f"Failed to get relationship stats: {e}")
        return {"total_relationships": 0, "by_type": {}, "error": str(e)}


# ==================== Async Jobs (Epic 7) ====================

import hashlib
import uuid


def create_async_job(
    job_type: str,
    params: Dict[str, Any],
    user_id: str = "default",
    ttl_days: int = 14,
) -> Dict[str, Any]:
    """
    Create a new async job document.

    Story 7.1: Async Recommendations

    Args:
        job_type: Type of job (e.g., "recommendations")
        params: Job parameters
        user_id: User identifier
        ttl_days: Days until job expires (default 14)

    Returns:
        Dictionary with job_id, status, created_at
    """
    try:
        db = get_firestore_client()

        # Generate unique job ID
        job_id = f"{job_type[:3]}-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        expires_at = now + timedelta(days=ttl_days)

        job_doc = {
            "job_id": job_id,
            "job_type": job_type,
            "status": "pending",
            "progress": 0.0,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "expires_at": expires_at,
            "params": params,
            "result": None,
            "error": None,
            "user_id": user_id,
        }

        db.collection("async_jobs").document(job_id).set(job_doc)
        logger.info(f"Created async job {job_id} of type {job_type}")

        return {
            "job_id": job_id,
            "status": "pending",
            "created_at": now.isoformat() + "Z",
        }

    except Exception as e:
        logger.error(f"Failed to create async job: {e}")
        raise


def get_async_job(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get async job by ID.

    Args:
        job_id: Job identifier

    Returns:
        Job document or None if not found
    """
    try:
        db = get_firestore_client()
        doc = db.collection("async_jobs").document(job_id).get()

        if not doc.exists:
            return None

        data = doc.to_dict()
        # Convert timestamps to ISO strings
        for field in ["created_at", "updated_at", "completed_at", "expires_at"]:
            if data.get(field):
                data[field] = data[field].isoformat() + "Z"

        return data

    except Exception as e:
        logger.error(f"Failed to get async job {job_id}: {e}")
        return None


def update_async_job(
    job_id: str,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> bool:
    """
    Update async job status and/or result.

    Args:
        job_id: Job identifier
        status: New status (pending, running, completed, failed)
        progress: Progress percentage (0.0 - 1.0)
        result: Job result (when completed)
        error: Error message (when failed)

    Returns:
        True if updated successfully
    """
    try:
        db = get_firestore_client()
        now = datetime.utcnow()

        update_data = {"updated_at": now}

        if status is not None:
            update_data["status"] = status
            if status in ("completed", "failed"):
                update_data["completed_at"] = now

        if progress is not None:
            update_data["progress"] = progress

        if result is not None:
            update_data["result"] = result

        if error is not None:
            update_data["error"] = error

        db.collection("async_jobs").document(job_id).update(update_data)
        logger.info(f"Updated async job {job_id}: status={status}, progress={progress}")
        return True

    except Exception as e:
        logger.error(f"Failed to update async job {job_id}: {e}")
        return False


def list_async_jobs(
    job_type: str,
    user_id: str = "default",
    status: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    List async jobs for a user.

    Args:
        job_type: Filter by job type
        user_id: User identifier
        status: Optional status filter
        limit: Maximum jobs to return

    Returns:
        List of job documents
    """
    try:
        db = get_firestore_client()

        query = db.collection("async_jobs")
        query = query.where("job_type", "==", job_type)
        query = query.where("user_id", "==", user_id)

        if status:
            query = query.where("status", "==", status)

        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        jobs = []
        for doc in query.stream():
            data = doc.to_dict()
            # Convert timestamps
            for field in ["created_at", "updated_at", "completed_at", "expires_at"]:
                if data.get(field):
                    data[field] = data[field].isoformat() + "Z"
            jobs.append(data)

        return jobs

    except Exception as e:
        logger.error(f"Failed to list async jobs: {e}")
        return []


def get_recommendations_history(
    user_id: str = "default",
    days: int = 14,
) -> Dict[str, Any]:
    """
    Get all recommendations from completed jobs in the last N days.

    Story 7.1: Flat list of all recommendations with metadata.

    Args:
        user_id: User identifier
        days: Lookback period (default 14)

    Returns:
        Dictionary with total_count and recommendations list
    """
    try:
        db = get_firestore_client()
        cutoff = datetime.utcnow() - timedelta(days=days)

        query = db.collection("async_jobs")
        query = query.where("job_type", "==", "recommendations")
        query = query.where("user_id", "==", user_id)
        query = query.where("status", "==", "completed")
        query = query.where("created_at", ">=", cutoff)
        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)

        all_recommendations = []

        for doc in query.stream():
            data = doc.to_dict()
            job_params = data.get("params", {})
            completed_at = data.get("completed_at")
            if completed_at:
                completed_at = completed_at.isoformat() + "Z"

            result = data.get("result", {})
            recommendations = result.get("recommendations", [])

            for rec in recommendations:
                all_recommendations.append(
                    {
                        "title": rec.get("title"),
                        "url": rec.get("url"),
                        "domain": rec.get("domain"),
                        "recommended_at": completed_at,
                        "params": {
                            "mode": job_params.get("mode"),
                            "hot_sites": job_params.get("hot_sites"),
                        },
                        "why_recommended": rec.get("why_recommended"),
                    }
                )

        return {
            "days": days,
            "total_count": len(all_recommendations),
            "recommendations": all_recommendations,
        }

    except Exception as e:
        logger.error(f"Failed to get recommendations history: {e}")
        return {"days": days, "total_count": 0, "recommendations": [], "error": str(e)}
