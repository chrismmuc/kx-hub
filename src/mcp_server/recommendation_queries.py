"""
Smart query generation for reading recommendations.

Story 3.5: AI-Powered Reading Recommendations
Story 3.8: Enhanced Query Variation

Generates search queries from KB context:
- Recent read themes
- Top cluster topics
- Knowledge card takeaways for "beyond what you know" queries
- Stale cluster detection for gap filling
- Cluster rotation based on time/session seed (Story 3.8)
- Synonym and perspective variation (Story 3.8)
"""

import logging
import hashlib
import random
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import Counter

from . import firestore_client

logger = logging.getLogger(__name__)


# ============================================================================
# Story 3.8: Query Variation Enhancements
# ============================================================================

# Synonym expansions for common terms
SYNONYM_MAP = {
    'architecture': ['system design', 'software architecture', 'design patterns'],
    'microservices': ['distributed systems', 'service mesh', 'containerization'],
    'platform': ['developer platform', 'internal platform', 'platform engineering'],
    'ai': ['artificial intelligence', 'machine learning', 'deep learning'],
    'ml': ['machine learning', 'predictive modeling', 'data science'],
    'devops': ['site reliability', 'infrastructure', 'CI/CD'],
    'security': ['cybersecurity', 'application security', 'zero trust'],
    'data': ['data engineering', 'data pipelines', 'analytics'],
    'cloud': ['cloud native', 'cloud computing', 'serverless'],
    'api': ['REST API', 'GraphQL', 'API design'],
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


def vary_query_perspective(
    topic: str,
    session_seed: Optional[int] = None
) -> str:
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


def rotate_clusters(
    clusters: List[Dict[str, Any]],
    session_seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Rotate cluster order based on session seed for variety.

    Story 3.8 AC#5: Cluster rotation based on session.

    Args:
        clusters: List of cluster dictionaries
        session_seed: Seed for rotation (default: time-based)

    Returns:
        Rotated list of clusters
    """
    if not clusters or len(clusters) <= 1:
        return clusters

    if session_seed is None:
        session_seed = get_session_seed()

    # Calculate rotation amount based on seed
    rotation = session_seed % len(clusters)

    # Rotate the list
    return clusters[rotation:] + clusters[:rotation]


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
            return {
                'themes': [],
                'authors': [],
                'sources': [],
                'takeaways': []
            }

        # Collect metadata
        authors = Counter()
        sources = Counter()
        tags = Counter()
        takeaways = []

        for chunk in chunks:
            # Count authors and sources
            if chunk.get('author'):
                authors[chunk['author']] += 1
            if chunk.get('source'):
                sources[chunk['source']] += 1

            # Collect tags
            for tag in chunk.get('tags', []):
                if tag:
                    tags[tag] += 1

            # Collect takeaways from knowledge cards
            knowledge_card = chunk.get('knowledge_card', {})
            if knowledge_card:
                card_takeaways = knowledge_card.get('takeaways', [])
                if card_takeaways:
                    takeaways.extend(card_takeaways[:2])  # Top 2 per chunk

        # Extract top themes from tags
        top_tags = [tag for tag, count in tags.most_common(10)]

        # Deduplicate takeaways (limit to 10)
        unique_takeaways = list(dict.fromkeys(takeaways))[:10]

        result = {
            'themes': top_tags,
            'authors': [author for author, _ in authors.most_common(5)],
            'sources': [source for source, _ in sources.most_common(5)],
            'takeaways': unique_takeaways,
            'chunk_count': len(chunks)
        }

        logger.info(
            f"Extracted {len(top_tags)} themes, {len(unique_takeaways)} takeaways "
            f"from {len(chunks)} chunks"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to extract recent read themes: {e}")
        return {
            'themes': [],
            'authors': [],
            'sources': [],
            'takeaways': [],
            'error': str(e)
        }


def get_top_cluster_themes(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Get themes from top clusters by size.

    Args:
        limit: Maximum clusters to include

    Returns:
        List of dictionaries with cluster info:
        - cluster_id: Cluster identifier
        - name: Cluster name (theme)
        - description: Cluster description
        - size: Number of chunks in cluster
    """
    try:
        logger.info(f"Getting top {limit} cluster themes")

        clusters = firestore_client.get_top_clusters(limit=limit)

        themes = []
        for cluster in clusters:
            cluster_id = cluster.get('id', '')
            name = cluster.get('name', '')

            # Skip noise or unnamed clusters
            if not name or 'noise' in name.lower():
                continue

            themes.append({
                'cluster_id': cluster_id,
                'name': name,
                'description': cluster.get('description', ''),
                'size': cluster.get('size', 0)
            })

        logger.info(f"Extracted {len(themes)} cluster themes")
        return themes

    except Exception as e:
        logger.error(f"Failed to get cluster themes: {e}")
        return []


def get_clusters_by_ids(cluster_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Get cluster themes for specific cluster IDs.

    Story 3.9 AC#1: Cluster filtering support

    Args:
        cluster_ids: List of cluster IDs to fetch

    Returns:
        List of dictionaries with cluster info:
        - cluster_id: Cluster identifier
        - name: Cluster name (theme)
        - description: Cluster description
        - size: Number of chunks in cluster
    """
    try:
        logger.info(f"Getting cluster themes for {len(cluster_ids)} specific clusters")

        themes = []
        for cid in cluster_ids:
            cluster = firestore_client.get_cluster_by_id(cid)

            if not cluster:
                logger.warning(f"Cluster not found: {cid}")
                continue

            name = cluster.get('name', '')

            # Skip noise or unnamed clusters
            if not name or 'noise' in name.lower():
                continue

            themes.append({
                'cluster_id': cid,
                'name': name,
                'description': cluster.get('description', ''),
                'size': cluster.get('size', 0)
            })

        logger.info(f"Fetched {len(themes)} cluster themes from specific IDs")
        return themes

    except Exception as e:
        logger.error(f"Failed to get clusters by IDs: {e}")
        return []


def get_stale_cluster_themes(
    stale_days: int = 30,
    min_size: int = 5
) -> List[Dict[str, Any]]:
    """
    Find clusters that haven't been updated recently for gap detection.

    Args:
        stale_days: Consider clusters stale if no new content in N days
        min_size: Minimum cluster size to consider "important"

    Returns:
        List of stale cluster dictionaries needing refresh
    """
    try:
        logger.info(f"Finding stale clusters (>{stale_days} days, min size {min_size})")

        # Get all clusters
        all_clusters = firestore_client.get_all_clusters()

        # For now, return clusters above minimum size
        # Future: Track last_updated_at per cluster for true staleness
        stale = []
        for cluster in all_clusters:
            name = cluster.get('name', '')
            size = cluster.get('size', 0)

            # Skip noise and small clusters
            if not name or 'noise' in name.lower() or size < min_size:
                continue

            stale.append({
                'cluster_id': cluster.get('id'),
                'name': name,
                'description': cluster.get('description', ''),
                'size': size
            })

        # Return bottom half by size (likely stale/neglected)
        stale.sort(key=lambda x: x['size'])
        result = stale[:len(stale) // 2]

        logger.info(f"Found {len(result)} potentially stale clusters")
        return result[:5]  # Limit to 5

    except Exception as e:
        logger.error(f"Failed to find stale clusters: {e}")
        return []


def generate_search_queries(
    scope: str = "both",
    days: int = 14,
    max_queries: int = 8,
    use_variation: bool = True,
    cluster_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Generate smart search queries for Tavily based on KB context.

    Story 3.5: Base query generation
    Story 3.8 AC#5: Enhanced query variation
    Story 3.9 AC#1: Cluster filtering support

    Args:
        scope: "recent" (recent reads), "clusters" (top clusters), or "both"
        days: Lookback period for recent reads
        max_queries: Maximum number of queries to generate
        use_variation: Enable Story 3.8 query variation (default True)
        cluster_ids: Optional list of specific cluster IDs to use (Story 3.9)

    Returns:
        List of query dictionaries:
        - query: Search query string
        - source: Where query came from (cluster, theme, takeaway, gap)
        - context: Additional context (cluster_id, etc.)
    """
    try:
        logger.info(
            f"Generating search queries: scope={scope}, days={days}, "
            f"variation={use_variation}, cluster_ids={cluster_ids}"
        )

        queries = []
        session_seed = get_session_seed() if use_variation else None

        # Get cluster themes if scope includes clusters
        if scope in ("clusters", "both"):
            # Story 3.9: Use specific clusters if provided, otherwise top clusters
            if cluster_ids:
                cluster_themes = get_clusters_by_ids(cluster_ids)
                logger.info(f"Using {len(cluster_themes)} specific clusters from cluster_ids")
            else:
                cluster_themes = get_top_cluster_themes(limit=5)

            # Story 3.8: Rotate clusters based on session
            if use_variation:
                cluster_themes = rotate_clusters(cluster_themes, session_seed)

            for cluster in cluster_themes:
                # Generate query from cluster name
                name = cluster['name']

                # Story 3.8: Use varied query perspective
                if use_variation:
                    query = vary_query_perspective(name, session_seed)
                else:
                    query = f"{name} latest developments 2024 2025"

                queries.append({
                    'query': query,
                    'source': 'cluster',
                    'context': {
                        'cluster_id': cluster['cluster_id'],
                        'cluster_name': name
                    }
                })

        # Get recent read themes if scope includes recent
        if scope in ("recent", "both"):
            recent = get_recent_read_themes(days=days)

            # Generate queries from themes
            for theme in recent.get('themes', [])[:3]:
                # Story 3.8: Use varied query perspective
                if use_variation:
                    query = vary_query_perspective(theme, session_seed)
                else:
                    query = f"{theme} best practices insights 2024 2025"

                queries.append({
                    'query': query,
                    'source': 'theme',
                    'context': {
                        'theme': theme
                    }
                })

            # Generate "beyond what you know" queries from takeaways
            for takeaway in recent.get('takeaways', [])[:2]:
                # Extract key concept from takeaway
                takeaway_short = takeaway[:100] if len(takeaway) > 100 else takeaway
                query = f"beyond {takeaway_short}"
                queries.append({
                    'query': query,
                    'source': 'takeaway',
                    'context': {
                        'takeaway': takeaway
                    }
                })

        # Add gap-filling queries for stale clusters
        if scope == "both":
            stale_clusters = get_stale_cluster_themes()
            for cluster in stale_clusters[:2]:
                query = f"{cluster['name']} new research findings"
                queries.append({
                    'query': query,
                    'source': 'gap',
                    'context': {
                        'cluster_id': cluster['cluster_id'],
                        'cluster_name': cluster['name'],
                        'reason': 'stale_cluster'
                    }
                })

        # Deduplicate and limit queries
        seen_queries = set()
        unique_queries = []
        for q in queries:
            query_lower = q['query'].lower()
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
    query = query_dict.get('query', '')

    # Tavily works best with natural language queries
    # Remove excessive punctuation but keep structure
    query = query.replace('"', '').replace("'", '')

    return query.strip()
