"""
Smart query generation for reading recommendations.

Story 3.5: AI-Powered Reading Recommendations
Story 3.8: Enhanced Query Variation
Story 4.4: Removed cluster dependency, uses sources and recent reads

Generates search queries from KB context:
- Recent read themes
- Top source topics
- Knowledge card takeaways for "beyond what you know" queries
"""

import hashlib
import logging
import random
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

import firestore_client

logger = logging.getLogger(__name__)


# ============================================================================
# Story 3.8: Query Variation Enhancements
# ============================================================================

# Synonym expansions for common terms
SYNONYM_MAP = {
    "architecture": ["system design", "software architecture", "design patterns"],
    "microservices": ["distributed systems", "service mesh", "containerization"],
    "platform": ["developer platform", "internal platform", "platform engineering"],
    "ai": ["artificial intelligence", "machine learning", "deep learning"],
    "ml": ["machine learning", "predictive modeling", "data science"],
    "devops": ["site reliability", "infrastructure", "CI/CD"],
    "security": ["cybersecurity", "application security", "zero trust"],
    "data": ["data engineering", "data pipelines", "analytics"],
    "cloud": ["cloud native", "cloud computing", "serverless"],
    "api": ["REST API", "GraphQL", "API design"],
}

# Query perspective templates
PERSPECTIVE_TEMPLATES = [
    "{topic} latest developments 2024 2025",
    "{topic} best practices insights",
    "advanced {topic} techniques",
    "future of {topic}",
    "{topic} case studies real world",
    "{topic} emerging trends",
    "beyond {topic} basics",
    "{topic} expert analysis",
]


def get_session_seed() -> int:
    """
    Generate a time-based seed for session-consistent randomization.

    Story 3.8 AC#5: Query variation with time-based seed.

    Uses current hour as seed so queries vary throughout the day
    but remain consistent within the same hour.

    Returns:
        Integer seed based on current time
    """
    now = datetime.utcnow()
    # Combine date and hour for daily rotation with hourly variation
    seed_str = f"{now.year}{now.month}{now.day}{now.hour}"
    return int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)


def expand_with_synonyms(term: str) -> List[str]:
    """
    Expand a term with synonyms for query variation.

    Story 3.8 AC#5: Synonym expansion.

    Args:
        term: Original search term

    Returns:
        List containing original term plus synonyms
    """
    term_lower = term.lower()
    expanded = [term]

    # Check each word in the term for synonyms
    for key, synonyms in SYNONYM_MAP.items():
        if key in term_lower:
            expanded.extend(synonyms[:2])  # Add up to 2 synonyms
            break

    return list(dict.fromkeys(expanded))  # Deduplicate while preserving order


def vary_query_perspective(topic: str, session_seed: Optional[int] = None) -> str:
    """
    Generate varied query using different perspective templates.

    Story 3.8 AC#5: Perspective variation in query phrasing.

    Args:
        topic: The topic to search for
        session_seed: Seed for consistent randomization (default: time-based)

    Returns:
        Query string with varied perspective
    """
    if session_seed is None:
        session_seed = get_session_seed()

    # Use seed to select template consistently within session
    random.seed(session_seed + hash(topic))
    template = random.choice(PERSPECTIVE_TEMPLATES)

    return template.format(topic=topic)


def get_recent_read_themes(days: int = 14, limit: int = 50) -> Dict[str, Any]:
    """
    Extract themes from recent reads for query generation.

    Args:
        days: Lookback period
        limit: Maximum chunks to analyze

    Returns:
        Dictionary with:
        - themes: List of extracted theme strings
        - authors: List of authors from recent reads
        - sources: List of sources from recent reads
        - takeaways: Sample takeaways from knowledge cards
    """
    try:
        logger.info(f"Extracting themes from last {days} days of reading")

        chunks = firestore_client.get_recent_chunks_with_cards(days=days, limit=limit)

        if not chunks:
            logger.warning("No recent chunks found for theme extraction")
            return {"themes": [], "authors": [], "sources": [], "takeaways": []}

        # Collect metadata
        authors = Counter()
        sources = Counter()
        tags = Counter()
        takeaways = []

        for chunk in chunks:
            # Count authors and sources
            if chunk.get("author"):
                authors[chunk["author"]] += 1
            if chunk.get("source"):
                sources[chunk["source"]] += 1

            # Collect tags
            for tag in chunk.get("tags", []):
                if tag:
                    tags[tag] += 1

            # Collect takeaways from knowledge cards
            knowledge_card = chunk.get("knowledge_card", {})
            if knowledge_card:
                card_takeaways = knowledge_card.get("takeaways", [])
                if card_takeaways:
                    takeaways.extend(card_takeaways[:2])  # Top 2 per chunk

        # Extract top themes from tags
        top_tags = [tag for tag, count in tags.most_common(10)]

        # Deduplicate takeaways (limit to 10)
        unique_takeaways = list(dict.fromkeys(takeaways))[:10]

        result = {
            "themes": top_tags,
            "authors": [author for author, _ in authors.most_common(5)],
            "sources": [source for source, _ in sources.most_common(5)],
            "takeaways": unique_takeaways,
            "chunk_count": len(chunks),
        }

        logger.info(
            f"Extracted {len(top_tags)} themes, {len(unique_takeaways)} takeaways "
            f"from {len(chunks)} chunks"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to extract recent read themes: {e}")
        return {
            "themes": [],
            "authors": [],
            "sources": [],
            "takeaways": [],
            "error": str(e),
        }


def get_top_source_themes(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Get themes from top sources by chunk count.

    Story 4.4: Replaces get_top_cluster_themes

    Args:
        limit: Maximum sources to include

    Returns:
        List of dictionaries with source info:
        - source_id: Source identifier
        - title: Source title (theme)
        - author: Source author
        - chunk_count: Number of chunks in source
    """
    try:
        logger.info(f"Getting top {limit} source themes")

        sources = firestore_client.list_sources(limit=limit)

        themes = []
        for source in sources:
            source_id = source.get("source_id", "")
            title = source.get("title", "")
            author = source.get("author", "")

            # Skip unnamed sources
            if not title:
                continue

            themes.append(
                {
                    "source_id": source_id,
                    "title": title,
                    "author": author,
                    "chunk_count": source.get("chunk_count", 0),
                }
            )

        logger.info(f"Extracted {len(themes)} source themes")
        return themes

    except Exception as e:
        logger.error(f"Failed to get source themes: {e}")
        return []


def rotate_sources(
    sources: List[Dict[str, Any]], session_seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Rotate source order based on session seed for variety.

    Story 3.8 AC#5: Source rotation based on session.
    Story 4.4: Replaces rotate_clusters

    Args:
        sources: List of source dictionaries
        session_seed: Seed for rotation (default: time-based)

    Returns:
        Rotated list of sources
    """
    if not sources or len(sources) <= 1:
        return sources

    if session_seed is None:
        session_seed = get_session_seed()

    # Calculate rotation amount based on seed
    rotation = session_seed % len(sources)

    # Rotate the list
    return sources[rotation:] + sources[:rotation]


def generate_search_queries(
    days: int = 14,
    max_queries: int = 8,
    use_variation: bool = True,
) -> List[Dict[str, Any]]:
    """
    Generate smart search queries for Tavily based on KB context.

    Story 3.5: Base query generation
    Story 3.8 AC#5: Enhanced query variation
    Story 4.4: Simplified - removed cluster/scope parameters

    Args:
        days: Lookback period for recent reads
        max_queries: Maximum number of queries to generate
        use_variation: Enable Story 3.8 query variation (default True)

    Returns:
        List of query dictionaries:
        - query: Search query string
        - source: Where query came from (source, theme, takeaway)
        - context: Additional context
    """
    try:
        logger.info(
            f"Generating search queries: days={days}, variation={use_variation}"
        )

        queries = []
        session_seed = get_session_seed() if use_variation else None

        # Get top source themes
        source_themes = get_top_source_themes(limit=5)

        # Story 3.8: Rotate sources based on session
        if use_variation:
            source_themes = rotate_sources(source_themes, session_seed)

        for source in source_themes[:3]:
            # Generate query from source title
            title = source["title"]

            # Story 3.8: Use varied query perspective
            if use_variation:
                query = vary_query_perspective(title, session_seed)
            else:
                query = f"{title} latest developments 2024 2025"

            queries.append(
                {
                    "query": query,
                    "source": "source",
                    "context": {
                        "source_id": source["source_id"],
                        "source_title": title,
                    },
                }
            )

        # Get recent read themes
        recent = get_recent_read_themes(days=days)

        # Generate queries from themes (tags)
        for theme in recent.get("themes", [])[:3]:
            # Story 3.8: Use varied query perspective
            if use_variation:
                query = vary_query_perspective(theme, session_seed)
            else:
                query = f"{theme} best practices insights 2024 2025"

            queries.append(
                {"query": query, "source": "theme", "context": {"theme": theme}}
            )

        # Generate "beyond what you know" queries from takeaways
        for takeaway in recent.get("takeaways", [])[:2]:
            # Extract key concept from takeaway
            takeaway_short = takeaway[:100] if len(takeaway) > 100 else takeaway
            query = f"beyond {takeaway_short}"
            queries.append(
                {
                    "query": query,
                    "source": "takeaway",
                    "context": {"takeaway": takeaway},
                }
            )

        # Deduplicate and limit queries
        seen_queries = set()
        unique_queries = []
        for q in queries:
            query_lower = q["query"].lower()
            if query_lower not in seen_queries:
                seen_queries.add(query_lower)
                unique_queries.append(q)

        result = unique_queries[:max_queries]

        logger.info(f"Generated {len(result)} unique search queries")
        return result

    except Exception as e:
        logger.error(f"Failed to generate search queries: {e}")
        return []


def format_query_for_tavily(query_dict: Dict[str, Any]) -> str:
    """
    Format a query dictionary into a Tavily-optimized search string.

    Args:
        query_dict: Query dictionary from generate_search_queries()

    Returns:
        Formatted query string
    """
    query = query_dict.get("query", "")

    # Tavily works best with natural language queries
    # Remove excessive punctuation but keep structure
    query = query.replace('"', "").replace("'", "")

    return query.strip()
