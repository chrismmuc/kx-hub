"""
Quality filtering and deduplication for reading recommendations.

Story 3.5: AI-Powered Reading Recommendations
Story 3.8: Enhanced Recommendation Ranking

Provides:
- LLM-based content depth scoring (1-5 scale) - supports Gemini, Claude
- "Why recommended" explanation generation
- Source diversity cap (max 2 per domain)
- KB deduplication via embedding similarity
- Recency scoring with exponential decay (Story 3.8)
- Multi-factor combined scoring (Story 3.8)
- Stochastic sampling with temperature (Story 3.8)
"""

import logging
import math
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict

# Add parent directory to path for llm module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import get_client, BaseLLMClient

import firestore_client
import embeddings

logger = logging.getLogger(__name__)

# Similarity threshold for deduplication
DEDUP_SIMILARITY_THRESHOLD = 0.85

# Maximum recommendations per domain
MAX_PER_DOMAIN = 2

# Minimum depth score required
MIN_DEPTH_SCORE = 3

# Global LLM client cache
_llm_client: Optional[BaseLLMClient] = None

# ============================================================================
# Story 3.8: Enhanced Ranking Functions
# ============================================================================

# Default ranking weights (sum must equal 1.0)
DEFAULT_RANKING_WEIGHTS = {
    'relevance': 0.50,  # Semantic similarity to KB content
    'recency': 0.25,    # Publication freshness
    'depth': 0.15,      # Content quality (Gemini score)
    'authority': 0.10   # Author recognition from KB
}

# Default recency settings
DEFAULT_RECENCY_HALF_LIFE_DAYS = 90
DEFAULT_MAX_AGE_DAYS = 365

# Default diversity settings
DEFAULT_NOVELTY_BONUS = 0.10
DEFAULT_DOMAIN_DUPLICATE_PENALTY = 0.05
DEFAULT_STOCHASTIC_TEMPERATURE = 0.3

# ============================================================================
# Story 3.9: Discovery Mode Presets
# ============================================================================

DISCOVERY_MODES = {
    "balanced": {
        "description": "Standard mix - good for daily use",
        "weights": {"relevance": 0.50, "recency": 0.25, "depth": 0.15, "authority": 0.10},
        "temperature": 0.3,
        "tavily_days": 180,
        "min_depth_score": 3,
        "slots": {"relevance_count": 2, "serendipity_count": 1, "stale_refresh_count": 1, "trending_count": 1}
    },
    "fresh": {
        "description": "Prioritize recent content - great for catching up",
        "weights": {"relevance": 0.25, "recency": 0.50, "depth": 0.15, "authority": 0.10},
        "temperature": 0.2,
        "tavily_days": 30,  # Recent content only
        "min_depth_score": 2,  # Lower quality bar for fresh content
        "slots": {"relevance_count": 1, "serendipity_count": 1, "stale_refresh_count": 0, "trending_count": 3}
    },
    "deep": {
        "description": "Prioritize in-depth content - weekend reading",
        "weights": {"relevance": 0.35, "recency": 0.15, "depth": 0.40, "authority": 0.10},
        "temperature": 0.2,
        "tavily_days": 365,  # Include older evergreen content
        "min_depth_score": 4,  # Higher quality bar
        "slots": {"relevance_count": 3, "serendipity_count": 1, "stale_refresh_count": 1, "trending_count": 0}
    },
    "surprise_me": {
        "description": "Break filter bubble - explore new topics",
        "weights": {"relevance": 0.30, "recency": 0.25, "depth": 0.25, "authority": 0.20},
        "temperature": 0.8,  # High randomization
        "tavily_days": 180,
        "min_depth_score": 3,
        "slots": {"relevance_count": 1, "serendipity_count": 3, "stale_refresh_count": 1, "trending_count": 0},
        "use_related_clusters": True  # Explore adjacent topics
    }
}


def get_mode_config(mode: str) -> Dict[str, Any]:
    """
    Get configuration for a discovery mode.

    Story 3.9 AC#6: Discovery modes

    Args:
        mode: Discovery mode name (balanced, fresh, deep, surprise_me)

    Returns:
        Mode configuration dict with weights, temperature, slots, etc.
    """
    return DISCOVERY_MODES.get(mode, DISCOVERY_MODES["balanced"])


def calculate_recency_score(
    published_date: Optional[datetime],
    half_life_days: int = DEFAULT_RECENCY_HALF_LIFE_DAYS,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS
) -> float:
    """
    Calculate recency score using exponential decay.

    Story 3.8 AC#1: Recency-aware scoring

    The score decays exponentially based on article age:
    - Score of 1.0 for articles published today
    - Score of 0.5 at half_life_days age
    - Score of 0.25 at 2x half_life_days
    - Score of 0.0 for articles older than max_age_days (filtered out)

    Args:
        published_date: Article publication datetime (None = neutral score)
        half_life_days: Days until score drops to 0.5 (default 90)
        max_age_days: Maximum age in days before filtering (default 365)

    Returns:
        Recency score between 0.0 and 1.0

    Examples:
        >>> calculate_recency_score(datetime.now())  # Today
        1.0
        >>> calculate_recency_score(datetime.now() - timedelta(days=90))  # 90 days
        0.5
        >>> calculate_recency_score(datetime.now() - timedelta(days=180))  # 180 days
        0.25
        >>> calculate_recency_score(datetime.now() - timedelta(days=400))  # >365 days
        0.0
    """
    # Handle missing publication date gracefully
    if published_date is None:
        logger.debug("No published_date provided, using neutral score 0.5")
        return 0.5

    now = datetime.utcnow()
    age_days = (now - published_date).days

    # Filter out articles older than max_age
    if age_days > max_age_days:
        return 0.0

    # Articles from the future or today get max score
    if age_days <= 0:
        return 1.0

    # Exponential decay: score = exp(-ln(2) * age / half_life)
    # This ensures score = 0.5 when age = half_life
    decay_rate = math.log(2) / half_life_days
    score = math.exp(-decay_rate * age_days)

    return round(score, 4)


def calculate_combined_score(
    result: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
    novelty_bonus: float = 0.0,
    domain_penalty: float = 0.0
) -> Dict[str, Any]:
    """
    Calculate combined ranking score from multiple weighted factors.

    Story 3.8 AC#2: Multi-factor ranking
    Story 3.8 AC#8: Transparent scoring

    Combines:
    - relevance_score: Semantic similarity (from Tavily or embedding)
    - recency_score: Publication freshness (exponential decay)
    - depth_score: Content quality (Gemini 1-5 scale normalized)
    - authority_score: Author/source credibility from KB

    Args:
        result: Recommendation dict with individual scores
        weights: Factor weights (default: 50/25/15/10 split)
        novelty_bonus: Bonus for never-shown recommendations
        domain_penalty: Penalty for domain duplicates

    Returns:
        Dictionary with:
        - combined_score: Final weighted score
        - score_breakdown: Individual factor scores
        - weights_used: Weights applied
        - adjustments: Novelty bonus and domain penalty applied
        - final_score: Combined score after adjustments
    """
    if weights is None:
        weights = DEFAULT_RANKING_WEIGHTS.copy()

    # Validate weights sum to 1.0
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 0.01:
        logger.warning(f"Ranking weights sum to {weight_sum}, expected 1.0")

    # Extract individual scores (normalize to 0-1 range)
    scores = {
        'relevance': min(1.0, max(0.0, result.get('relevance_score', 0.5))),
        'recency': min(1.0, max(0.0, result.get('recency_score', 0.5))),
        'depth': min(1.0, max(0.0, (result.get('depth_score', 3) / 5.0))),
        'authority': min(1.0, max(0.0, result.get('credibility_score', 0.0)))
    }

    # Calculate weighted combined score
    combined = sum(weights.get(k, 0) * scores[k] for k in scores)

    # Apply adjustments
    adjustments = {
        'novelty_bonus': novelty_bonus,
        'domain_penalty': domain_penalty
    }
    final_score = combined + novelty_bonus - domain_penalty
    final_score = min(1.0, max(0.0, final_score))  # Clamp to 0-1

    return {
        'combined_score': round(combined, 3),
        'score_breakdown': {k: round(v, 3) for k, v in scores.items()},
        'weights_used': weights,
        'adjustments': adjustments,
        'final_score': round(final_score, 3)
    }


def diversified_sample(
    results: List[Dict[str, Any]],
    n: int,
    temperature: float = DEFAULT_STOCHASTIC_TEMPERATURE,
    score_key: str = 'combined_score'
) -> List[Dict[str, Any]]:
    """
    Sample results with controlled randomness using softmax temperature.

    Story 3.8 AC#3: Result diversity via stochastic sampling

    Temperature controls randomness:
    - temperature=0: Deterministic (always returns top-N by score)
    - temperature=0.3: Mild randomization (default, favors high scores)
    - temperature=1.0: High randomization (more uniform distribution)

    Args:
        results: List of recommendations with combined_score
        n: Number of samples to return
        temperature: Softmax temperature (0=deterministic, 1=random)
        score_key: Key to use for scoring (default: combined_score)

    Returns:
        List of n sampled recommendations
    """
    if not results:
        return []

    if len(results) <= n:
        return results

    # Temperature 0 = deterministic top-N
    if temperature == 0:
        return sorted(results, key=lambda x: x.get(score_key, 0), reverse=True)[:n]

    try:
        import numpy as np

        # Extract scores
        scores = np.array([r.get(score_key, 0) for r in results])

        # Handle edge case of all-zero scores
        if np.sum(scores) == 0:
            scores = np.ones(len(results))

        # Softmax with temperature
        exp_scores = np.exp(scores / temperature)
        probabilities = exp_scores / exp_scores.sum()

        # Sample without replacement
        indices = np.random.choice(
            len(results),
            size=min(n, len(results)),
            replace=False,
            p=probabilities
        )

        # Return sampled results (preserve order by score)
        sampled = [results[i] for i in sorted(indices)]
        return sampled

    except ImportError:
        logger.warning("NumPy not available, falling back to deterministic sampling")
        return sorted(results, key=lambda x: x.get(score_key, 0), reverse=True)[:n]


def parse_published_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse publication date string into datetime.

    Handles multiple formats from Tavily and other sources.

    Args:
        date_str: Date string in various formats

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    formats = [
        '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%dT%H:%M:%S%z',
    ]

    for fmt in formats:
        try:
            # Truncate to format length for timezone-aware formats
            return datetime.strptime(date_str[:len(date_str)], fmt)
        except (ValueError, TypeError):
            continue

    logger.debug(f"Could not parse date: {date_str}")
    return None


# ============================================================================
# Story 3.8: Slot-Based Rotation
# ============================================================================

class SlotType:
    """Slot types for recommendation rotation strategy."""
    RELEVANCE = "RELEVANCE"       # Top combined score from active clusters
    SERENDIPITY = "SERENDIPITY"   # From related but unexplored cluster
    STALE_REFRESH = "STALE_REFRESH"  # From clusters with oldest content
    TRENDING = "TRENDING"         # Highest recency score


def assign_slots(
    recommendations: List[Dict[str, Any]],
    slot_config: Optional[Dict[str, int]] = None
) -> List[Dict[str, Any]]:
    """
    Assign slot types to recommendations for strategic variety.

    Story 3.8 AC#4: Slot-based rotation

    Slot Strategy:
    - Slots 1-2 (RELEVANCE): Highest combined score from user's interests
    - Slot 3 (SERENDIPITY): Discovery pick from related cluster
    - Slot 4 (STALE_REFRESH): From cluster needing fresh content
    - Slot 5 (TRENDING): Highest recency score, may sacrifice relevance

    Args:
        recommendations: List of scored recommendations
        slot_config: Dict with slot counts per type (default: 2,1,1,1)

    Returns:
        Recommendations with 'slot' and 'slot_reason' fields added
    """
    if not recommendations:
        return []

    # Default slot configuration (total = 5)
    if slot_config is None:
        slot_config = {
            'relevance_count': 2,
            'serendipity_count': 1,
            'stale_refresh_count': 1,
            'trending_count': 1
        }

    # Sort by different criteria for slot assignment
    by_combined = sorted(
        recommendations,
        key=lambda x: x.get('final_score', x.get('combined_score', 0)),
        reverse=True
    )
    by_recency = sorted(
        recommendations,
        key=lambda x: x.get('recency_score', 0),
        reverse=True
    )

    # Track assigned URLs to avoid duplicates
    assigned_urls = set()
    result = []

    # Slot 1-2: RELEVANCE (top combined scores)
    relevance_count = slot_config.get('relevance_count', 2)
    for rec in by_combined:
        if len([r for r in result if r.get('slot') == SlotType.RELEVANCE]) >= relevance_count:
            break
        if rec.get('url') not in assigned_urls:
            rec['slot'] = SlotType.RELEVANCE
            rec['slot_reason'] = f"Top combined score ({rec.get('final_score', rec.get('combined_score', 0)):.2f})"
            result.append(rec)
            assigned_urls.add(rec.get('url'))

    # Slot 3: SERENDIPITY (from different clusters than RELEVANCE)
    serendipity_count = slot_config.get('serendipity_count', 1)
    relevance_clusters = set()
    for rec in result:
        cluster = rec.get('related_to', {}).get('cluster_id')
        if cluster:
            relevance_clusters.add(cluster)

    for rec in by_combined:
        if len([r for r in result if r.get('slot') == SlotType.SERENDIPITY]) >= serendipity_count:
            break
        if rec.get('url') in assigned_urls:
            continue
        # Prefer recommendations from different clusters
        rec_cluster = rec.get('related_to', {}).get('cluster_id')
        if rec_cluster and rec_cluster not in relevance_clusters:
            rec['slot'] = SlotType.SERENDIPITY
            rec['slot_reason'] = f"Discovery from cluster: {rec.get('related_to', {}).get('cluster_name', 'related topic')}"
            result.append(rec)
            assigned_urls.add(rec.get('url'))
            break

    # If no serendipity from different cluster, take next best
    if len([r for r in result if r.get('slot') == SlotType.SERENDIPITY]) < serendipity_count:
        for rec in by_combined:
            if len([r for r in result if r.get('slot') == SlotType.SERENDIPITY]) >= serendipity_count:
                break
            if rec.get('url') not in assigned_urls:
                rec['slot'] = SlotType.SERENDIPITY
                rec['slot_reason'] = "Broadens your reading perspective"
                result.append(rec)
                assigned_urls.add(rec.get('url'))

    # Slot 4: STALE_REFRESH (lower relevance but good quality)
    stale_count = slot_config.get('stale_refresh_count', 1)
    # Use recommendations from the middle of the combined list
    mid_start = len(result)
    for rec in by_combined[mid_start:]:
        if len([r for r in result if r.get('slot') == SlotType.STALE_REFRESH]) >= stale_count:
            break
        if rec.get('url') not in assigned_urls and rec.get('depth_score', 0) >= 3:
            rec['slot'] = SlotType.STALE_REFRESH
            rec['slot_reason'] = "Refreshes an area of interest"
            result.append(rec)
            assigned_urls.add(rec.get('url'))

    # Slot 5: TRENDING (highest recency)
    trending_count = slot_config.get('trending_count', 1)
    for rec in by_recency:
        if len([r for r in result if r.get('slot') == SlotType.TRENDING]) >= trending_count:
            break
        if rec.get('url') not in assigned_urls:
            rec['slot'] = SlotType.TRENDING
            recency = rec.get('recency_score', 0)
            rec['slot_reason'] = f"Fresh content (recency: {recency:.2f})"
            result.append(rec)
            assigned_urls.add(rec.get('url'))

    # Fill remaining slots with best available
    total_slots = sum(slot_config.values())
    for rec in by_combined:
        if len(result) >= total_slots:
            break
        if rec.get('url') not in assigned_urls:
            rec['slot'] = SlotType.RELEVANCE
            rec['slot_reason'] = "Additional relevant content"
            result.append(rec)
            assigned_urls.add(rec.get('url'))

    logger.info(f"Assigned slots to {len(result)} recommendations")
    return result


def get_llm_client() -> BaseLLMClient:
    """
    Get or create cached LLM client instance.

    Model selection via environment variables:
        LLM_MODEL: Model name (e.g., "gemini-2.5-flash", "claude-haiku")
        LLM_PROVIDER: Provider preference ("gemini" or "claude")

    Returns:
        Initialized LLM client
    """
    global _llm_client

    if _llm_client is None:
        _llm_client = get_client()  # Uses LLM_MODEL env var or default
        logger.info(f"Initialized LLM client: {_llm_client}")

    return _llm_client


def score_content_depth(
    title: str,
    content: str,
    url: str
) -> Dict[str, Any]:
    """
    Score article depth using configured LLM.

    Args:
        title: Article title
        content: Article snippet/content
        url: Article URL

    Returns:
        Dictionary with:
        - depth_score: 1-5 scale (5=most in-depth)
        - reasoning: Brief explanation of score
    """
    try:
        client = get_llm_client()

        prompt = f"""Rate the depth and quality of this article on a scale of 1-5:

Title: {title}
URL: {url}
Content preview: {content[:500]}

Scoring criteria:
1 = Surface-level, listicle, clickbait
2 = Brief overview, lacks detail
3 = Solid coverage, some insights
4 = In-depth analysis, expert perspective
5 = Comprehensive, authoritative, original research

Respond with ONLY a JSON object:
{{"score": <1-5>, "reasoning": "<brief 1-sentence explanation>"}}"""

        result = client.generate_json(prompt)

        score = int(result.get('score', 3))
        score = max(1, min(5, score))  # Clamp to 1-5

        return {
            'depth_score': score,
            'reasoning': result.get('reasoning', '')
        }

    except Exception as e:
        logger.warning(f"Failed to score content depth: {e}")
        # Default to middle score on error
        return {
            'depth_score': 3,
            'reasoning': 'Unable to assess depth',
            'error': str(e)
        }


def generate_why_recommended(
    recommendation: Dict[str, Any],
    query_context: Dict[str, Any]
) -> str:
    """
    Generate "why recommended" explanation linking to user's existing content.

    Args:
        recommendation: The recommendation being explained
        query_context: Context about why this query was generated

    Returns:
        Human-readable explanation string
    """
    try:
        source = query_context.get('source', 'search')
        context = query_context.get('context', {})

        if source == 'cluster':
            cluster_name = context.get('cluster_name', 'your interests')
            return f"Connects to your reading cluster: {cluster_name}"

        elif source == 'theme':
            theme = context.get('theme', 'recent topics')
            return f"Related to your recent reading on: {theme}"

        elif source == 'takeaway':
            takeaway = context.get('takeaway', '')
            if takeaway:
                short_takeaway = takeaway[:50] + "..." if len(takeaway) > 50 else takeaway
                return f"Builds on concept: {short_takeaway}"
            return "Extends your recent learning"

        elif source == 'gap':
            cluster_name = context.get('cluster_name', 'an area')
            return f"Refreshes knowledge in: {cluster_name}"

        else:
            return "Matches your reading interests"

    except Exception as e:
        logger.warning(f"Failed to generate why_recommended: {e}")
        return "Recommended based on your reading history"


def check_kb_duplicate(
    title: str,
    content: str,
    url: str = None,
    author: str = None
) -> Dict[str, Any]:
    """
    Check if recommendation content already exists in KB.

    Story 3.10: Enhanced deduplication with multiple strategies:
    1. URL-based matching (most reliable)
    2. Title containment check (handles subtitles, editions)
    3. Author + topic matching
    4. Embedding similarity fallback

    Args:
        title: Recommendation title
        content: Recommendation snippet
        url: Recommendation URL (optional but recommended)
        author: Recommendation author (optional)

    Returns:
        Dictionary with:
        - is_duplicate: Boolean
        - match_type: How duplicate was detected (url, title, author, embedding, None)
        - similarity_score: Confidence score (0-1)
        - similar_chunk_id: ID of matching chunk if duplicate
        - similar_title: Title of matching chunk if duplicate
    """
    try:
        # 1. URL-based check (most reliable)
        if url:
            existing = firestore_client.find_by_source_url(url)
            if existing:
                logger.debug(f"Duplicate detected by URL: {url}")
                return {
                    'is_duplicate': True,
                    'match_type': 'url',
                    'similarity_score': 1.0,
                    'similar_chunk_id': existing.get('id'),
                    'similar_title': existing.get('title')
                }

        # 2. Title containment check (handles "Vibe Coding" vs "Beyond Vibe Coding")
        title_lower = title.lower()

        # Extract core title (before colon/dash for subtitles)
        core_title = title_lower.split(':')[0].split(' - ')[0].strip()

        # Remove common prefixes that don't change the content
        prefixes_to_strip = ['beyond ', 'the ', 'a ', 'an ', 'introduction to ', 'guide to ']
        stripped_title = core_title
        for prefix in prefixes_to_strip:
            if stripped_title.startswith(prefix):
                stripped_title = stripped_title[len(prefix):]
                break

        # Search for similar titles in KB
        if len(stripped_title) >= 3:
            similar_by_title = firestore_client.find_chunks_by_title_prefix(stripped_title, limit=5)

            for chunk in similar_by_title:
                kb_title = chunk.get('title', '').lower()
                kb_core = kb_title.split(':')[0].split(' - ')[0].strip()

                # Check bidirectional containment
                if (stripped_title in kb_core or
                    kb_core in stripped_title or
                    stripped_title in kb_title or
                    kb_title in title_lower):
                    logger.debug(f"Duplicate detected by title containment: '{title}' ~ '{kb_title}'")
                    return {
                        'is_duplicate': True,
                        'match_type': 'title_containment',
                        'similarity_score': 0.9,
                        'similar_chunk_id': chunk.get('id'),
                        'similar_title': chunk.get('title')
                    }

        # 3. Author + topic matching (if author provided)
        if author and len(author) > 2:
            author_lower = author.lower()
            # Check if this author exists in KB with similar topic
            author_chunks = firestore_client.find_chunks_by_title_prefix(stripped_title[:10], limit=20)

            for chunk in author_chunks:
                chunk_author = chunk.get('author', '').lower()
                # Check if any author name matches (handles "Gene Kim" in "Gene Kim, Steve Yegge")
                if author_lower in chunk_author or chunk_author in author_lower:
                    # Same author + similar title = very likely duplicate
                    chunk_title = chunk.get('title', '').lower()
                    # Check for topic overlap (shared significant words)
                    title_words = set(w for w in stripped_title.split() if len(w) > 3)
                    chunk_words = set(w for w in chunk_title.split() if len(w) > 3)
                    overlap = title_words & chunk_words

                    if len(overlap) >= 1:  # At least one significant word in common
                        logger.debug(f"Duplicate detected by author match: {author} wrote '{chunk_title}'")
                        return {
                            'is_duplicate': True,
                            'match_type': 'author_topic',
                            'similarity_score': 0.85,
                            'similar_chunk_id': chunk.get('id'),
                            'similar_title': chunk.get('title')
                        }

        # 4. Embedding similarity fallback
        text_to_embed = f"{title}. {content[:300]}"
        embedding = embeddings.generate_query_embedding(text_to_embed)

        similar_chunks = firestore_client.find_nearest(
            embedding_vector=embedding,
            limit=1
        )

        if similar_chunks:
            top_chunk = similar_chunks[0]
            top_title = top_chunk.get('title', '').lower()

            # Use combined heuristic: title word overlap + position in results
            # If it's the #1 result AND has significant word overlap, it's likely a duplicate
            title_words = set(w for w in title_lower.split() if len(w) > 2)
            top_words = set(w for w in top_title.split() if len(w) > 2)
            common_words = title_words & top_words

            # Calculate Jaccard similarity for word sets
            union_words = title_words | top_words
            word_similarity = len(common_words) / max(len(union_words), 1)

            # More lenient threshold: 40% word overlap indicates likely duplicate
            # (The embedding search already filtered for semantic similarity)
            if word_similarity > 0.4:
                logger.debug(f"Duplicate detected by embedding+title: similarity={word_similarity:.2f}")
                return {
                    'is_duplicate': True,
                    'match_type': 'embedding',
                    'similarity_score': word_similarity,
                    'similar_chunk_id': top_chunk.get('id'),
                    'similar_title': top_chunk.get('title')
                }

        # No duplicate found
        return {
            'is_duplicate': False,
            'match_type': None,
            'similarity_score': 0.0,
            'similar_chunk_id': None,
            'similar_title': None
        }

    except Exception as e:
        logger.warning(f"Failed to check KB duplicate: {e}")
        return {
            'is_duplicate': False,
            'match_type': None,
            'similarity_score': 0.0,
            'error': str(e)
        }


def filter_recommendations(
    recommendations: List[Dict[str, Any]],
    query_contexts: List[Dict[str, Any]],
    min_depth_score: int = MIN_DEPTH_SCORE,
    max_per_domain: int = MAX_PER_DOMAIN,
    check_duplicates: bool = True,
    known_authors: Optional[List[str]] = None,
    known_sources: Optional[List[str]] = None,
    trusted_sources: Optional[List[str]] = None,
    max_age_days: int = 90
) -> Dict[str, Any]:
    """
    Filter and score recommendations for quality.

    Applies:
    - Recency filter (max_age_days)
    - Gemini depth scoring (with author/source credibility boost)
    - Source diversity cap
    - KB deduplication
    - Trusted source boost for public credibility

    Args:
        recommendations: List of raw recommendations from Tavily
        query_contexts: Query context for each recommendation
        min_depth_score: Minimum depth score to include (default 3)
        max_per_domain: Max recommendations per domain (default 2)
        check_duplicates: Whether to check KB for duplicates
        known_authors: Authors from user's KB (credibility signal)
        known_sources: Sources/domains from user's KB (credibility signal)
        trusted_sources: Publicly credible sources whitelist to boost ranking
        max_age_days: Maximum age in days for articles (default 90, 0=no limit)

    Returns:
        Dictionary with:
        - recommendations: Filtered and scored recommendations
        - filtered_out: Counts of filtered items by reason
    """
    try:
        logger.info(f"Filtering {len(recommendations)} recommendations")

        filtered_out = {
            'duplicate_count': 0,
            'low_quality_count': 0,
            'diversity_cap_count': 0,
            'too_old_count': 0
        }

        domain_counts = defaultdict(int)
        filtered_recommendations = []

        # Create a mapping from URL to query context
        url_to_context = {}
        for rec, ctx in zip(recommendations, query_contexts):
            url = rec.get('url', '')
            if url:
                url_to_context[url] = ctx

        from datetime import datetime, timedelta

        # Calculate cutoff date for recency filter
        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=max_age_days) if max_age_days > 0 else None

        for rec in recommendations:
            url = rec.get('url', '')
            domain = rec.get('domain', '')
            title = rec.get('title', '')
            content = rec.get('content', '')
            published_date_str = rec.get('published_date')
            domain_clean = domain.replace('www.', '').lower()

            # 1. Check recency (filter out old articles)
            recency_score = 0.0
            article_date = None
            if published_date_str:
                try:
                    # Parse various date formats from Tavily
                    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ'):
                        try:
                            article_date = datetime.strptime(published_date_str[:19], fmt[:len(published_date_str)])
                            break
                        except ValueError:
                            continue

                    if article_date and cutoff_date and article_date < cutoff_date:
                        filtered_out['too_old_count'] += 1
                        logger.debug(f"Filtered (too old {published_date_str}): {title[:50]}...")
                        continue

                    # Calculate recency score (0-1, higher = more recent)
                    if article_date:
                        days_old = (now - article_date).days
                        recency_score = max(0, 1 - (days_old / 90))  # Linear decay over 90 days
                except Exception as e:
                    logger.debug(f"Could not parse date '{published_date_str}': {e}")

            # 2. Check domain diversity cap
            if domain_counts[domain] >= max_per_domain:
                filtered_out['diversity_cap_count'] += 1
                logger.debug(f"Filtered (diversity): {title[:50]}...")
                continue

            # 2. Check for KB duplicates (Story 3.10: enhanced with URL + title + author)
            if check_duplicates:
                dup_check = check_kb_duplicate(title, content, url=url)
                if dup_check.get('is_duplicate'):
                    filtered_out['duplicate_count'] += 1
                    match_type = dup_check.get('match_type', 'unknown')
                    similar_title = dup_check.get('similar_title', '')[:30]
                    logger.debug(f"Filtered (duplicate via {match_type}): '{title[:40]}' ~ '{similar_title}'")
                    continue

            # 3. Score content depth
            depth_result = score_content_depth(title, content, url)
            depth_score = depth_result.get('depth_score', 3)

            if depth_score < min_depth_score:
                filtered_out['low_quality_count'] += 1
                logger.debug(f"Filtered (low quality {depth_score}): {title[:50]}...")
                continue

            # 4. Calculate KB credibility score
            credibility_score = 0.0
            credibility_reasons = []

            # Check if author matches known authors (case-insensitive partial match)
            if known_authors:
                title_lower = title.lower()
                content_lower = content.lower()
                for author in known_authors:
                    author_lower = author.lower()
                    if author_lower in title_lower or author_lower in content_lower:
                        credibility_score += 0.5
                        credibility_reasons.append(f"Author: {author}")
                        break

            # Check if domain matches known source domains from KB
            if known_sources:
                for known_domain in known_sources:
                    known_clean = known_domain.replace('www.', '').lower()
                    # Match exact domain or subdomain (e.g., s.hbr.org matches hbr.org)
                    if domain_clean == known_clean or domain_clean.endswith('.' + known_clean):
                        credibility_score += 0.3
                        credibility_reasons.append(f"Source: {known_domain}")
                        break

            # Boost if domain is in trusted public sources (whitelist), even if not in KB yet
            if trusted_sources:
                for trusted_domain in trusted_sources:
                    trusted_clean = trusted_domain.replace('www.', '').lower()
                    if domain_clean == trusted_clean or domain_clean.endswith('.' + trusted_clean):
                        credibility_score += 0.5
                        credibility_reasons.append(f"Trusted: {trusted_domain}")
                        break

            # 5. Generate "why recommended"
            query_context = url_to_context.get(url, {'source': 'search', 'context': {}})
            why_recommended = generate_why_recommended(rec, query_context)

            # Add credibility info to why_recommended if present
            if credibility_reasons:
                why_recommended += f" (Trusted: {', '.join(credibility_reasons)})"

            # Build filtered recommendation
            filtered_rec = {
                'title': title,
                'url': url,
                'domain': domain,
                'snippet': content,
                'published_date': rec.get('published_date'),
                'relevance_score': rec.get('score', 0.0),
                'depth_score': depth_score,
                'depth_reasoning': depth_result.get('reasoning', ''),
                'credibility_score': credibility_score,
                'recency_score': round(recency_score, 2),
                'why_recommended': why_recommended,
                'related_to': query_context.get('context', {})
            }

            filtered_recommendations.append(filtered_rec)
            domain_counts[domain] += 1

        logger.info(
            f"Filtering complete: {len(filtered_recommendations)} passed, "
            f"{sum(filtered_out.values())} filtered"
        )

        return {
            'recommendations': filtered_recommendations,
            'filtered_out': filtered_out
        }

    except Exception as e:
        logger.error(f"Failed to filter recommendations: {e}")
        return {
            'recommendations': [],
            'filtered_out': {'error': str(e)},
            'error': str(e)
        }


def batch_score_content(
    items: List[Dict[str, Any]],
    batch_size: int = 5
) -> List[Dict[str, Any]]:
    """
    Score multiple items efficiently using batched LLM calls.

    Args:
        items: List of items with title, content, url
        batch_size: Number of items to score per API call

    Returns:
        List of items with depth_score added
    """
    try:
        client = get_llm_client()
        results = []

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]

            # Build batch prompt
            batch_prompt = "Rate the depth and quality of these articles on a scale of 1-5:\n\n"

            for idx, item in enumerate(batch):
                batch_prompt += f"""Article {idx + 1}:
Title: {item.get('title', '')}
URL: {item.get('url', '')}
Preview: {item.get('content', '')[:300]}

"""

            batch_prompt += """
Scoring criteria:
1 = Surface-level, listicle, clickbait
2 = Brief overview, lacks detail
3 = Solid coverage, some insights
4 = In-depth analysis, expert perspective
5 = Comprehensive, authoritative, original research

Respond with a JSON array of scores:
[{"article": 1, "score": <1-5>}, {"article": 2, "score": <1-5>}, ...]"""

            try:
                scores = client.generate_json(batch_prompt)

                # Handle both array and object responses
                if isinstance(scores, dict):
                    scores = scores.get('scores', [scores])

                # Apply scores to items
                for score_item in scores:
                    idx = score_item.get('article', 1) - 1
                    if 0 <= idx < len(batch):
                        batch[idx]['depth_score'] = max(1, min(5, score_item.get('score', 3)))

            except Exception as e:
                logger.warning(f"Batch scoring failed: {e}")
                # Apply default scores
                for item in batch:
                    if 'depth_score' not in item:
                        item['depth_score'] = 3

            results.extend(batch)

        return results

    except Exception as e:
        logger.error(f"Batch scoring failed: {e}")
        # Return items with default scores
        for item in items:
            if 'depth_score' not in item:
                item['depth_score'] = 3
        return items
