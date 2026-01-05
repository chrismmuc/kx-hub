"""
Article Ideas Engine for Blog Content Generation.

Story 6.1: Blog Idea Extraction from Knowledge Base

Generates article ideas from KB sources by analyzing:
- Source relationships and cross-source themes
- Knowledge card content and takeaways
- Content density (chunk count)
- Recency of highlights

Calculates medium scores for publication suitability:
- linkedin_post, linkedin_article, blog, newsletter, twitter_thread, substack
"""

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import firestore_client

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

# Supported publication mediums with characteristics
MEDIUMS = {
    "linkedin_post": {
        "max_length": 1300,  # characters
        "ideal_sources": (1, 2),
        "ideal_chunks": (1, 3),
        "description": "Short, hook-driven, personal insights",
    },
    "linkedin_article": {
        "max_length": 10000,  # ~2000 words
        "ideal_sources": (2, 5),
        "ideal_chunks": (5, 15),
        "description": "Professional deep-dives, 800-2000 words",
    },
    "blog": {
        "max_length": 15000,  # ~3000 words
        "ideal_sources": (3, 10),
        "ideal_chunks": (8, 30),
        "description": "SEO-optimized, permanent reference, 1000-3000 words",
    },
    "newsletter": {
        "max_length": 7500,  # ~1500 words
        "ideal_sources": (2, 5),
        "ideal_chunks": (4, 12),
        "description": "Curated, personal voice, 500-1500 words",
    },
    "twitter_thread": {
        "max_length": 4200,  # ~15 tweets
        "ideal_sources": (1, 3),
        "ideal_chunks": (2, 8),
        "description": "Punchy, numbered takeaways, 5-15 tweets",
    },
    "substack": {
        "max_length": 12500,  # ~2500 words
        "ideal_sources": (2, 6),
        "ideal_chunks": (5, 20),
        "description": "Essay-style, analytical, 1000-2500 words",
    },
}

# Idea types based on source patterns
IDEA_TYPES = {
    "deep_dive": "Deep analysis of a single topic",
    "comparison": "Comparing two related concepts or approaches",
    "synthesis": "Combining insights from multiple sources",
    "contradiction": "Exploring conflicting viewpoints",
    "practical": "Actionable takeaways and how-tos",
}


# ============================================================================
# Source Scoring Algorithm
# ============================================================================


def calculate_source_score(source: Dict[str, Any]) -> float:
    """
    Calculate article potential score for a source.

    Factors:
    - Chunk count (more content = more to write about)
    - Has relationships to other sources
    - Quality of knowledge cards

    Args:
        source: Source data from Firestore

    Returns:
        Score between 0.0 and 1.0
    """
    score = 0.0

    # Chunk count score (0-0.3)
    chunk_count = source.get("chunk_count", 0)
    if chunk_count >= 10:
        score += 0.3
    elif chunk_count >= 5:
        score += 0.2
    elif chunk_count >= 3:
        score += 0.15
    elif chunk_count >= 1:
        score += 0.05

    # Has tags (indicates categorization) (0-0.1)
    tags = source.get("tags", [])
    if len(tags) >= 3:
        score += 0.1
    elif len(tags) >= 1:
        score += 0.05

    return min(score, 1.0)


def calculate_chunk_score(chunks: List[Dict[str, Any]]) -> float:
    """
    Calculate content depth score from chunks.

    Args:
        chunks: List of chunk data

    Returns:
        Score between 0.0 and 1.0
    """
    if not chunks:
        return 0.0

    chunk_count = len(chunks)

    # Base score from chunk count
    if chunk_count >= 15:
        base_score = 1.0
    elif chunk_count >= 10:
        base_score = 0.85
    elif chunk_count >= 5:
        base_score = 0.7
    elif chunk_count >= 3:
        base_score = 0.5
    else:
        base_score = 0.3

    # Bonus for knowledge cards with takeaways
    cards_with_takeaways = 0
    for chunk in chunks:
        kc = chunk.get("knowledge_card", {})
        if kc and kc.get("takeaways"):
            cards_with_takeaways += 1

    takeaway_ratio = cards_with_takeaways / chunk_count if chunk_count > 0 else 0
    bonus = takeaway_ratio * 0.15

    return min(base_score + bonus, 1.0)


def calculate_relationship_score(
    source_id: str, relationships: Optional[List[Dict[str, Any]]] = None
) -> float:
    """
    Calculate cross-source connection score.

    Args:
        source_id: Source to check relationships for
        relationships: Pre-fetched relationships (optional)

    Returns:
        Score between 0.0 and 1.0
    """
    if relationships is None:
        relationships = firestore_client.get_source_relationships(source_id)

    if not relationships:
        return 0.0

    rel_count = len(relationships)

    # Base score from relationship count
    if rel_count >= 5:
        base_score = 1.0
    elif rel_count >= 3:
        base_score = 0.8
    elif rel_count >= 2:
        base_score = 0.6
    elif rel_count >= 1:
        base_score = 0.4
    else:
        base_score = 0.0

    return base_score


def calculate_recency_score(
    created_at: Optional[datetime], half_life_days: int = 30
) -> float:
    """
    Calculate recency score with exponential decay.

    Args:
        created_at: When the source/chunk was added
        half_life_days: Days until score halves

    Returns:
        Score between 0.0 and 1.0
    """
    if created_at is None:
        return 0.5  # Default for unknown dates

    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return 0.5

    now = datetime.now(created_at.tzinfo) if created_at.tzinfo else datetime.now()
    age_days = (now - created_at).days

    if age_days <= 0:
        return 1.0

    # Exponential decay
    import math

    decay_rate = math.log(2) / half_life_days
    score = math.exp(-decay_rate * age_days)

    return max(0.0, min(1.0, score))


def calculate_contradiction_bonus(source_ids: List[str]) -> float:
    """
    Check if sources have contradicting relationships (good for discussion articles).

    Args:
        source_ids: List of source IDs to check

    Returns:
        Bonus score (0.0 or 0.15)
    """
    try:
        contradictions = firestore_client.find_contradictions(limit=50)

        for contradiction in contradictions:
            chunk_a_source = contradiction.get("chunk_a", {}).get("title", "")
            chunk_b_source = contradiction.get("chunk_b", {}).get("title", "")

            # Check if any of our sources are involved in contradictions
            for source_id in source_ids:
                if (
                    source_id in chunk_a_source.lower()
                    or source_id in chunk_b_source.lower()
                ):
                    return 0.15

        return 0.0
    except Exception as e:
        logger.warning(f"Failed to check contradictions: {e}")
        return 0.0


# ============================================================================
# Medium Score Calculation
# ============================================================================


def calculate_medium_scores(
    source_count: int,
    chunk_count: int,
    tag_count: int,
    has_contradictions: bool = False,
) -> Dict[str, float]:
    """
    Calculate suitability scores for each publication medium.

    Based on primary signals:
    - Source count: Few → Post, Many → Article/Blog
    - Chunk count: Few → short, Many → long
    - Topic breadth (tags): Narrow → Post, Broad → Blog
    - Contradictions: Good for discussion/essay formats

    Args:
        source_count: Number of sources involved
        chunk_count: Total chunks available
        tag_count: Number of distinct tags
        has_contradictions: Whether contradictions exist

    Returns:
        Dict mapping medium name to score (0.0-1.0)
    """
    scores = {}

    for medium, config in MEDIUMS.items():
        ideal_sources = config["ideal_sources"]
        ideal_chunks = config["ideal_chunks"]

        # Source fit score
        if ideal_sources[0] <= source_count <= ideal_sources[1]:
            source_fit = 1.0
        elif source_count < ideal_sources[0]:
            source_fit = source_count / ideal_sources[0]
        else:
            # Penalty for too many sources (harder to synthesize)
            overage = source_count - ideal_sources[1]
            source_fit = max(0.3, 1.0 - (overage * 0.1))

        # Chunk fit score
        if ideal_chunks[0] <= chunk_count <= ideal_chunks[1]:
            chunk_fit = 1.0
        elif chunk_count < ideal_chunks[0]:
            chunk_fit = chunk_count / ideal_chunks[0] if ideal_chunks[0] > 0 else 0.5
        else:
            overage = chunk_count - ideal_chunks[1]
            chunk_fit = max(0.4, 1.0 - (overage * 0.05))

        # Tag breadth bonus for longer formats
        tag_bonus = 0.0
        if medium in ["blog", "substack", "linkedin_article"]:
            if tag_count >= 3:
                tag_bonus = 0.1
            elif tag_count >= 2:
                tag_bonus = 0.05

        # Contradiction bonus for essay/discussion formats
        contradiction_bonus = 0.0
        if has_contradictions and medium in ["substack", "blog", "linkedin_article"]:
            contradiction_bonus = 0.1

        # Combined score
        base_score = (source_fit * 0.4) + (chunk_fit * 0.6)
        final_score = min(1.0, base_score + tag_bonus + contradiction_bonus)

        scores[medium] = round(final_score, 2)

    return scores


# ============================================================================
# Idea Generation
# ============================================================================


def generate_idea_id(title: str, source_ids: List[str]) -> str:
    """
    Generate a deterministic idea ID from title and sources.

    Args:
        title: Idea title
        source_ids: Related source IDs

    Returns:
        Short hash-based ID
    """
    content = f"{title.lower()}:{'|'.join(sorted(source_ids))}"
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def determine_idea_type(
    source_count: int, has_contradictions: bool, relationship_types: List[str]
) -> str:
    """
    Determine the type of article idea based on source patterns.

    Args:
        source_count: Number of sources
        has_contradictions: Whether contradictions exist
        relationship_types: Types of relationships found

    Returns:
        Idea type key
    """
    if has_contradictions:
        return "contradiction"

    if source_count == 1:
        return "deep_dive"

    if source_count == 2:
        return "comparison"

    if "extends" in relationship_types or "supports" in relationship_types:
        return "synthesis"

    return "practical"


def extract_themes_from_sources(sources: List[Dict[str, Any]]) -> List[str]:
    """
    Extract common themes/tags from multiple sources.

    Args:
        sources: List of source data

    Returns:
        List of common themes
    """
    all_tags = []
    for source in sources:
        all_tags.extend(source.get("tags", []))

    # Count occurrences
    from collections import Counter

    tag_counts = Counter(all_tags)

    # Return tags that appear in multiple sources
    common_tags = [tag for tag, count in tag_counts.items() if count >= 2]

    if not common_tags:
        # Fallback to most common tags
        common_tags = [tag for tag, _ in tag_counts.most_common(3)]

    return common_tags


def generate_idea_title(
    idea_type: str, sources: List[Dict[str, Any]], themes: List[str]
) -> str:
    """
    Generate a suggested title for the article idea.

    Args:
        idea_type: Type of idea (deep_dive, comparison, etc.)
        sources: Source data
        themes: Common themes

    Returns:
        Generated title
    """
    if not sources:
        return "Untitled Idea"

    primary_source = sources[0]
    source_title = primary_source.get("title", "Unknown")

    if idea_type == "deep_dive":
        return f"Deep Dive: {source_title}"

    if idea_type == "comparison" and len(sources) >= 2:
        return f"{sources[0].get('title', 'A')} vs {sources[1].get('title', 'B')}"

    if idea_type == "contradiction":
        return (
            f"The Debate: Conflicting Views on {themes[0] if themes else source_title}"
        )

    if idea_type == "synthesis" and themes:
        return f"What I Learned About {themes[0].title()}"

    if themes:
        return f"Insights on {themes[0].title()}"

    return f"Reflections on {source_title}"


def score_idea(
    sources: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Calculate comprehensive scores for an article idea.

    Args:
        sources: Source data
        chunks: Related chunks
        relationships: Cross-source relationships

    Returns:
        Dict with strength score and reasoning_details
    """
    source_ids = [s.get("source_id", "") for s in sources]

    # Individual scores
    source_score = (
        sum(calculate_source_score(s) for s in sources) / len(sources) if sources else 0
    )
    chunk_score = calculate_chunk_score(chunks)
    relationship_score = (
        len(relationships) / 5.0 if relationships else 0
    )  # Normalize to 0-1
    relationship_score = min(1.0, relationship_score)

    # Recency: use most recent source
    recency_scores = []
    for source in sources:
        created_at = source.get("created_at")
        if created_at:
            recency_scores.append(calculate_recency_score(created_at))
    recency_score = max(recency_scores) if recency_scores else 0.5

    # Contradiction bonus
    contradiction_bonus = calculate_contradiction_bonus(source_ids)

    # Combined strength
    strength = (
        source_score * 0.2
        + chunk_score * 0.35
        + relationship_score * 0.2
        + recency_score * 0.25
        + contradiction_bonus
    )

    return {
        "strength": round(min(1.0, strength), 2),
        "reasoning_details": {
            "source_score": round(source_score, 2),
            "chunk_score": round(chunk_score, 2),
            "relationship_score": round(relationship_score, 2),
            "recency_score": round(recency_score, 2),
            "contradiction_bonus": round(contradiction_bonus, 2),
        },
    }


# ============================================================================
# Firestore Operations
# ============================================================================


def save_article_idea(idea: Dict[str, Any]) -> str:
    """
    Save an article idea to Firestore.

    Args:
        idea: Idea data to save

    Returns:
        Idea ID
    """
    db = firestore_client.get_firestore_client()

    idea_id = idea.get("idea_id") or generate_idea_id(
        idea.get("title", ""), idea.get("source_ids", [])
    )

    doc_data = {
        "title": idea.get("title"),
        "description": idea.get("description", ""),
        "type": idea.get("type", "deep_dive"),
        "source_ids": idea.get("source_ids", []),
        "strength": idea.get("strength", 0.0),
        "reasoning_details": idea.get("reasoning_details", {}),
        "medium_scores": idea.get("medium_scores", {}),
        "status": idea.get("status", "suggested"),
        "reason": idea.get("reason", ""),
        "suggested_at": idea.get("suggested_at") or datetime.utcnow(),
        "article_id": None,
    }

    db.collection("article_ideas").document(idea_id).set(doc_data, merge=True)
    logger.info(f"Saved article idea: {idea_id}")

    return idea_id


def get_article_idea(idea_id: str) -> Optional[Dict[str, Any]]:
    """
    Get an article idea by ID.

    Args:
        idea_id: Idea document ID

    Returns:
        Idea data or None
    """
    db = firestore_client.get_firestore_client()

    doc = db.collection("article_ideas").document(idea_id).get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    data["idea_id"] = doc.id

    return data


def list_article_ideas(
    status: Optional[str] = None, limit: int = 20
) -> List[Dict[str, Any]]:
    """
    List article ideas with optional status filter.

    Args:
        status: Filter by status (suggested, accepted, rejected)
        limit: Maximum ideas to return

    Returns:
        List of ideas
    """
    db = firestore_client.get_firestore_client()

    query = db.collection("article_ideas")

    if status:
        query = query.where("status", "==", status)

    query = query.order_by(
        "suggested_at", direction=firestore_client.firestore.Query.DESCENDING
    )
    query = query.limit(limit)

    ideas = []
    for doc in query.stream():
        data = doc.to_dict()
        data["idea_id"] = doc.id
        ideas.append(data)

    logger.info(f"Listed {len(ideas)} article ideas (status={status})")
    return ideas


def update_idea_status(idea_id: str, status: str, reason: Optional[str] = None) -> bool:
    """
    Update the status of an article idea.

    Args:
        idea_id: Idea document ID
        status: New status (accepted, rejected)
        reason: Optional reason for status change

    Returns:
        True if successful
    """
    db = firestore_client.get_firestore_client()

    update_data = {
        "status": status,
        f"{status}_at": datetime.utcnow(),
    }

    if reason:
        update_data["status_reason"] = reason

    try:
        db.collection("article_ideas").document(idea_id).update(update_data)
        logger.info(f"Updated idea {idea_id} status to {status}")
        return True
    except Exception as e:
        logger.error(f"Failed to update idea status: {e}")
        return False


def check_idea_duplicate(title: str, source_ids: List[str]) -> Optional[Dict[str, Any]]:
    """
    Check if a similar idea already exists.

    Checks:
    1. Same source_ids combination
    2. Similar title (normalized comparison)

    Args:
        title: Idea title
        source_ids: Related source IDs

    Returns:
        Existing idea if duplicate found, None otherwise
    """
    db = firestore_client.get_firestore_client()

    # Normalize title for comparison
    normalized_title = re.sub(r"[^a-z0-9\s]", "", title.lower()).strip()

    # Check existing ideas
    for doc in db.collection("article_ideas").limit(100).stream():
        data = doc.to_dict()
        existing_sources = set(data.get("source_ids", []))
        candidate_sources = set(source_ids)

        # Same sources = duplicate
        if existing_sources == candidate_sources and existing_sources:
            data["idea_id"] = doc.id
            return data

        # Similar title = duplicate
        existing_title = data.get("title", "")
        normalized_existing = re.sub(r"[^a-z0-9\s]", "", existing_title.lower()).strip()

        # Check for high similarity
        if normalized_title and normalized_existing:
            # Simple containment check
            if (
                normalized_title in normalized_existing
                or normalized_existing in normalized_title
            ):
                data["idea_id"] = doc.id
                return data

    return None


# ============================================================================
# Main Idea Generation Functions
# ============================================================================


def suggest_ideas_from_sources(
    min_sources: int = 2,
    focus_tags: Optional[List[str]] = None,
    limit: int = 5,
    save: bool = True,
) -> List[Dict[str, Any]]:
    """
    Generate article ideas by analyzing KB sources.

    Algorithm:
    1. Get sources, optionally filtered by tags
    2. Score each source for article potential
    3. Identify cross-source themes and relationships
    4. Generate idea candidates
    5. Calculate medium scores
    6. Deduplicate against existing ideas

    Args:
        min_sources: Minimum sources per idea
        focus_tags: Optional tag filter
        limit: Maximum ideas to generate
        save: Whether to save ideas to Firestore

    Returns:
        List of generated ideas
    """
    logger.info(
        f"Generating article ideas (min_sources={min_sources}, tags={focus_tags})"
    )

    # Get all sources
    all_sources = firestore_client.list_sources(limit=100)

    if not all_sources:
        logger.warning("No sources found in KB")
        return []

    # Filter by tags if specified
    if focus_tags:
        all_sources = [
            s
            for s in all_sources
            if any(tag in s.get("tags", []) for tag in focus_tags)
        ]

    if len(all_sources) < min_sources:
        logger.warning(f"Only {len(all_sources)} sources available, need {min_sources}")
        return []

    ideas = []

    # Strategy 1: High-value single sources (deep dives)
    high_value_sources = sorted(
        all_sources, key=lambda s: s.get("chunk_count", 0), reverse=True
    )[:3]

    for source in high_value_sources:
        if len(ideas) >= limit:
            break

        source_id = source.get("source_id")
        source_detail = firestore_client.get_source_by_id(source_id)

        if not source_detail:
            continue

        chunks = source_detail.get("chunks", [])
        if len(chunks) < 3:
            continue

        # Check for duplicate
        title = f"Deep Dive: {source.get('title')}"
        if check_idea_duplicate(title, [source_id]):
            continue

        scores = score_idea([source], chunks, [])
        themes = source.get("tags", [])

        idea = {
            "title": title,
            "description": f"Comprehensive analysis of key insights from {source.get('title')}",
            "type": "deep_dive",
            "source_ids": [source_id],
            "sources": [source],
            "strength": scores["strength"],
            "reasoning_details": scores["reasoning_details"],
            "medium_scores": calculate_medium_scores(
                source_count=1,
                chunk_count=len(chunks),
                tag_count=len(themes),
                has_contradictions=False,
            ),
            "reason": f"High-value source with {len(chunks)} chunks and strong knowledge cards",
            "suggested_at": datetime.utcnow().isoformat(),
        }

        if save:
            idea["idea_id"] = save_article_idea(idea)
        else:
            idea["idea_id"] = generate_idea_id(title, [source_id])

        ideas.append(idea)

    # Strategy 2: Related source pairs (synthesis)
    for i, source_a in enumerate(all_sources[:10]):
        if len(ideas) >= limit:
            break

        source_a_id = source_a.get("source_id")
        relationships = firestore_client.get_source_relationships(source_a_id)

        for rel in relationships[:3]:
            if len(ideas) >= limit:
                break

            target_source_id = rel.get("target_source_id")
            target_source = next(
                (s for s in all_sources if s.get("source_id") == target_source_id), None
            )

            if not target_source:
                continue

            source_ids = [source_a_id, target_source_id]

            # Check for duplicate
            title = f"{source_a.get('title')} meets {target_source.get('title')}"
            if check_idea_duplicate(title, source_ids):
                continue

            # Get chunks from both sources
            source_a_detail = firestore_client.get_source_by_id(source_a_id)
            source_b_detail = firestore_client.get_source_by_id(target_source_id)

            all_chunks = []
            if source_a_detail:
                all_chunks.extend(source_a_detail.get("chunks", []))
            if source_b_detail:
                all_chunks.extend(source_b_detail.get("chunks", []))

            sources = [source_a, target_source]
            themes = extract_themes_from_sources(sources)

            rel_types = rel.get("relationship_types", [])
            has_contradictions = "contradicts" in rel_types

            idea_type = determine_idea_type(2, has_contradictions, rel_types)
            title = generate_idea_title(idea_type, sources, themes)

            scores = score_idea(sources, all_chunks, [rel])

            idea = {
                "title": title,
                "description": f"Exploring connections between {source_a.get('title')} and {target_source.get('title')}",
                "type": idea_type,
                "source_ids": source_ids,
                "sources": sources,
                "strength": scores["strength"],
                "reasoning_details": scores["reasoning_details"],
                "medium_scores": calculate_medium_scores(
                    source_count=2,
                    chunk_count=len(all_chunks),
                    tag_count=len(themes),
                    has_contradictions=has_contradictions,
                ),
                "reason": f"Related sources with {rel.get('relationship_types', ['connection'])} relationship",
                "suggested_at": datetime.utcnow().isoformat(),
            }

            if save:
                idea["idea_id"] = save_article_idea(idea)
            else:
                idea["idea_id"] = generate_idea_id(title, source_ids)

            ideas.append(idea)

    logger.info(f"Generated {len(ideas)} article ideas")
    return ideas[:limit]


# ============================================================================
# Web Enrichment (Tavily)
# ============================================================================


def enrich_idea_with_web(idea: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich an article idea with web research via Tavily.

    Provides market analysis:
    - How many similar articles exist
    - Is the topic trending
    - Suggested unique angle
    - Competition level

    Args:
        idea: Article idea to enrich

    Returns:
        Web analysis dict
    """
    try:
        import tavily_client

        title = idea.get("title", "")
        themes = []

        # Extract themes from sources
        for source in idea.get("sources", []):
            themes.extend(source.get("tags", []))

        # Build search query
        search_query = title
        if themes:
            search_query = f"{title} {' '.join(themes[:2])}"

        logger.info(f"Web enrichment search: {search_query}")

        # Search for existing articles
        results = tavily_client.search(
            query=search_query,
            days=365,  # Look back 1 year
            max_results=20,
            search_depth="basic",
        )

        existing_articles = results.get("result_count", 0)
        articles = results.get("results", [])

        # Analyze recency for trending detection
        recent_count = 0
        for article in articles:
            pub_date = article.get("published_date")
            if pub_date:
                try:
                    from datetime import datetime

                    date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    if (datetime.now(date.tzinfo) - date).days <= 30:
                        recent_count += 1
                except (ValueError, TypeError):
                    pass

        trending = recent_count >= 5  # 5+ articles in last month = trending

        # Determine competition level
        if existing_articles >= 15:
            competition = "high"
        elif existing_articles >= 8:
            competition = "medium"
        else:
            competition = "low"

        # Generate suggested angle based on analysis
        suggested_angle = _generate_suggested_angle(idea, articles, competition)

        return {
            "existing_articles": existing_articles,
            "trending": trending,
            "recent_articles_30d": recent_count,
            "suggested_angle": suggested_angle,
            "competition": competition,
            "top_existing": [
                {"title": a.get("title"), "url": a.get("url")} for a in articles[:3]
            ],
        }

    except Exception as e:
        logger.warning(f"Web enrichment failed: {e}")
        return {
            "error": str(e),
            "existing_articles": 0,
            "trending": False,
            "suggested_angle": "Unable to analyze - try again later",
            "competition": "unknown",
        }


def _generate_suggested_angle(
    idea: Dict[str, Any], existing_articles: List[Dict[str, Any]], competition: str
) -> str:
    """
    Generate a suggested unique angle for the article.

    Args:
        idea: The article idea
        existing_articles: Found existing articles
        competition: Competition level

    Returns:
        Suggested angle text
    """
    idea_type = idea.get("type", "deep_dive")
    source_count = len(idea.get("source_ids", []))

    if competition == "low":
        return "Low competition - you can be comprehensive and establish authority"

    if competition == "high":
        if idea_type == "contradiction":
            return "High competition but controversy angle is underexplored"
        if source_count >= 3:
            return "Focus on synthesis across multiple perspectives - most articles cover single viewpoints"
        return "High competition - focus on personal experience and unique insights"

    # Medium competition
    if idea_type == "comparison":
        return "Compare with real-world examples from your experience"
    if idea_type == "practical":
        return "Focus on actionable takeaways with code/templates"

    return "Add personal insights and practical applications to stand out"


def suggest_idea_for_topic(
    topic: str, source_ids: Optional[List[str]] = None, save: bool = True
) -> Dict[str, Any]:
    """
    Generate and score an idea for a specific topic.

    Used when user has a specific idea in mind and wants it evaluated.

    Args:
        topic: The article topic/title
        source_ids: Optional specific sources to use
        save: Whether to save to Firestore

    Returns:
        Generated idea with scores
    """
    logger.info(f"Evaluating topic idea: {topic}")

    # Check for duplicate first
    existing = check_idea_duplicate(topic, source_ids or [])
    if existing:
        logger.info(f"Found existing idea: {existing.get('idea_id')}")
        return {
            "idea": existing,
            "is_duplicate": True,
            "duplicate_of": existing.get("idea_id"),
        }

    # If no source_ids provided, search for relevant sources
    if not source_ids:
        # Use semantic search to find relevant chunks
        try:
            import embeddings

            query_embedding = embeddings.generate_query_embedding(topic)
            results = firestore_client.find_nearest(query_embedding, limit=10)

            # Extract unique source_ids from results
            found_sources = set()
            for result in results:
                source_id = result.get("source_id")
                if source_id:
                    found_sources.add(source_id)

            source_ids = list(found_sources)[:5]
        except Exception as e:
            logger.warning(f"Failed to find sources via search: {e}")
            source_ids = []

    if not source_ids:
        return {
            "error": "No relevant sources found for topic",
            "topic": topic,
            "suggestion": "Try adding focus_tags or source_ids parameter",
        }

    # Get source details
    sources = []
    all_chunks = []
    all_relationships = []

    for source_id in source_ids:
        source = firestore_client.get_source_by_id(source_id)
        if source:
            sources.append(source)
            all_chunks.extend(source.get("chunks", []))

            rels = firestore_client.get_source_relationships(source_id)
            all_relationships.extend(rels)

    if not sources:
        return {"error": "Could not load source details", "source_ids": source_ids}

    # Score the idea
    themes = extract_themes_from_sources(sources)
    rel_types = [r.get("type", "") for r in all_relationships]
    has_contradictions = "contradicts" in rel_types

    idea_type = determine_idea_type(len(sources), has_contradictions, rel_types)
    scores = score_idea(sources, all_chunks, all_relationships)

    idea = {
        "title": topic,
        "description": f"Article exploring {topic} based on {len(sources)} sources",
        "type": idea_type,
        "source_ids": source_ids,
        "sources": [
            {
                "source_id": s.get("source_id"),
                "title": s.get("title"),
                "author": s.get("author"),
            }
            for s in sources
        ],
        "strength": scores["strength"],
        "reasoning_details": scores["reasoning_details"],
        "medium_scores": calculate_medium_scores(
            source_count=len(sources),
            chunk_count=len(all_chunks),
            tag_count=len(themes),
            has_contradictions=has_contradictions,
        ),
        "reason": f"User-proposed topic with {len(sources)} relevant sources and {len(all_chunks)} chunks",
        "suggested_at": datetime.utcnow().isoformat(),
    }

    if save:
        idea["idea_id"] = save_article_idea(idea)
    else:
        idea["idea_id"] = generate_idea_id(topic, source_ids)

    return {"idea": idea, "is_duplicate": False}
