"""
Article Idea Generation from Knowledge Base.

Story 6.1: High-Quality Article Idea Generation

Generates article ideas with:
- Concrete thesis (not just topics)
- Unique angle based on user's highlights
- Supporting quotes from KB
- Timeliness assessment
- Medium scores for publication format
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import firestore_client

from src.llm import get_client

logger = logging.getLogger(__name__)


# ============================================================================
# Source Cluster Discovery
# ============================================================================


def find_source_clusters(
    min_relationships: int = 2,
    days: int = 30,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Find clusters of related sources that could make good article topics.

    Looks for sources with:
    - Cross-source relationships (extends, contradicts, etc.)
    - Recent highlights (topic is fresh)
    - Strong knowledge cards with takeaways

    Args:
        min_relationships: Minimum cross-source relationships required
        days: Only consider sources read in last N days
        limit: Maximum clusters to return

    Returns:
        List of source clusters with relationship info
    """
    try:
        # Get recent sources
        sources = firestore_client.list_sources(limit=100)
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        clusters = []

        for source in sources:
            source_id = source.get("source_id")
            if not source_id:
                continue

            # Check recency
            updated_at = source.get("updated_at")
            if updated_at and hasattr(updated_at, "timestamp"):
                if datetime.fromtimestamp(updated_at.timestamp()) < cutoff_date:
                    continue

            # Get relationships to other sources
            relationships = firestore_client.get_source_relationships(source_id)

            if len(relationships) >= min_relationships:
                # Get source details with knowledge cards
                source_details = firestore_client.get_source_by_id(source_id)

                clusters.append(
                    {
                        "primary_source": {
                            "source_id": source_id,
                            "title": source.get("title", "Unknown"),
                            "author": source.get("author", "Unknown"),
                            "chunk_count": source.get("chunk_count", 0),
                        },
                        "related_sources": relationships,
                        "relationship_count": len(relationships),
                        "relationship_types": _aggregate_relationship_types(
                            relationships
                        ),
                    }
                )

            if len(clusters) >= limit:
                break

        # Sort by relationship count
        clusters.sort(key=lambda x: x["relationship_count"], reverse=True)

        logger.info(f"Found {len(clusters)} source clusters")
        return clusters

    except Exception as e:
        logger.error(f"Failed to find source clusters: {e}")
        return []


def _aggregate_relationship_types(relationships: List[Dict]) -> Dict[str, int]:
    """Aggregate relationship types across all related sources."""
    types = {}
    for rel in relationships:
        for rel_type, count in rel.get("relationship_types", {}).items():
            types[rel_type] = types.get(rel_type, 0) + count
    return types


# ============================================================================
# Takeaway Extraction
# ============================================================================


def extract_top_takeaways(
    source_ids: List[str],
    max_per_source: int = 3,
) -> List[Dict[str, Any]]:
    """
    Extract top takeaways from Knowledge Cards for given sources.

    Args:
        source_ids: List of source IDs to extract from
        max_per_source: Maximum takeaways per source

    Returns:
        List of takeaways with source attribution
    """
    takeaways = []

    for source_id in source_ids:
        source = firestore_client.get_source_by_id(source_id)
        if not source:
            continue

        source_title = source.get("title", "Unknown")
        source_author = source.get("author", "Unknown")

        # Get chunks for this source via query
        chunks = firestore_client.get_chunks_by_source_id(source_id)

        source_takeaways = []

        for chunk in chunks:
            kc = chunk.get("knowledge_card", {})
            if not kc:
                continue

            chunk_id = chunk.get("chunk_id", "")

            # Get takeaways from knowledge card
            for takeaway in kc.get("takeaways", []):
                if takeaway and len(takeaway) > 20:  # Skip very short ones
                    source_takeaways.append(
                        {
                            "quote": takeaway,
                            "source": source_title,
                            "author": source_author,
                            "source_id": source_id,
                            "chunk_id": chunk_id,
                        }
                    )

        # Take top N per source (first ones, as they're usually most important)
        takeaways.extend(source_takeaways[:max_per_source])

    logger.info(f"Extracted {len(takeaways)} takeaways from {len(source_ids)} sources")
    return takeaways


# ============================================================================
# Thesis & Angle Generation (LLM)
# ============================================================================


THESIS_PROMPT = """Analyze these highlights and generate a concrete article idea.

HIGHLIGHTS:
{takeaways_formatted}

RULES FOR THE THESIS:
- FORBIDDEN: Vague phrases like "holistic approach", "unlock potential", "foster collaboration", "shift mindset"
- FORBIDDEN: Generic statements that could apply to any topic
- REQUIRED: Concrete claim that can be answered with YES or NO
- REQUIRED: Include specific details from the highlights

GOOD THESES (examples):
- "Teams that deploy daily have 3x fewer bugs than teams with weekly releases"
- "The ROI of AI tools drops after 6 months because developers stop using them"
- "Code reviews under 200 lines find 80% more bugs than longer reviews"

BAD THESES (examples):
- "AI transforms software development" (says nothing concrete)
- "Organizations must embrace change" (generic)
- "Balance between X and Y is key" (platitude)

Respond ONLY with this JSON:
{{
    "title": "Short, punchy title",
    "thesis": "A concrete, verifiable claim with specific details",
    "unique_angle": "What exactly connects these sources? What contradiction or surprising connection?"
}}"""


def generate_thesis_and_angle(
    takeaways: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Use LLM to generate thesis and unique angle from takeaways.

    Args:
        takeaways: List of takeaways with quotes and source info

    Returns:
        Dict with title, thesis, unique_angle
    """
    if not takeaways:
        return {"title": "", "thesis": "", "unique_angle": ""}

    # Format takeaways for prompt
    takeaways_formatted = "\n".join(
        [f'- "{t["quote"]}" — {t["author"]}, {t["source"]}' for t in takeaways]
    )

    prompt = THESIS_PROMPT.format(takeaways_formatted=takeaways_formatted)

    try:
        # Use Gemini 3 Pro for better reasoning on creative tasks
        client = get_client(model="gemini-3-pro-preview")
        response = client.generate(prompt)

        # Parse JSON response
        import json

        # Extract JSON from response (handle markdown code blocks)
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        result = json.loads(text.strip())

        return {
            "title": result.get("title", ""),
            "thesis": result.get("thesis", ""),
            "unique_angle": result.get("unique_angle", ""),
        }

    except Exception as e:
        logger.error(f"Failed to generate thesis: {e}")
        return {"title": "", "thesis": "", "unique_angle": ""}


# ============================================================================
# Timeliness Assessment
# ============================================================================


def assess_timeliness(
    source_ids: List[str],
    check_trending: bool = False,
) -> Dict[str, Any]:
    """
    Assess how timely/relevant the topic is.

    Args:
        source_ids: Source IDs to check
        check_trending: Whether to check if topic is trending (uses Tavily)

    Returns:
        Timeliness info with recency and optional trending data
    """
    # Calculate recency based on when sources were last updated
    recent_count = 0
    oldest_days = 0

    for source_id in source_ids:
        source = firestore_client.get_source_by_id(source_id)
        if not source:
            continue

        updated_at = source.get("updated_at")
        if updated_at and hasattr(updated_at, "timestamp"):
            days_ago = (
                datetime.utcnow() - datetime.fromtimestamp(updated_at.timestamp())
            ).days
            if days_ago <= 14:
                recent_count += 1
            oldest_days = max(oldest_days, days_ago)

    recency_text = (
        f"{recent_count} von {len(source_ids)} Sources in den letzten 2 Wochen gelesen"
    )
    if oldest_days <= 7:
        recency_text = "Alle Sources in der letzten Woche gelesen - sehr frisch!"
    elif oldest_days <= 14:
        recency_text = "Sources in den letzten 2 Wochen gelesen"
    elif oldest_days <= 30:
        recency_text = "Sources im letzten Monat gelesen"
    else:
        recency_text = f"Sources vor {oldest_days} Tagen gelesen"

    result = {
        "recency": recency_text,
        "recent_source_count": recent_count,
        "oldest_days_ago": oldest_days,
    }

    # Optional: Check if trending via Tavily
    if check_trending:
        # TODO: Implement trending check via Tavily
        result["trending"] = False
        result["trending_context"] = None

    return result


# ============================================================================
# Medium Score Calculation
# ============================================================================


def calculate_medium_scores(
    source_count: int,
    chunk_count: int,
    has_contradictions: bool,
    takeaway_count: int,
) -> Dict[str, float]:
    """
    Calculate suitability scores for different publication mediums.

    Args:
        source_count: Number of sources
        chunk_count: Total chunks across sources
        has_contradictions: Whether there are contradicting sources
        takeaway_count: Number of strong takeaways

    Returns:
        Dict mapping medium name to score (0.0 - 1.0)
    """
    scores = {}

    # LinkedIn Post: Good for single insight, low complexity
    scores["linkedin_post"] = max(
        0.0, min(1.0, 0.8 - (source_count - 1) * 0.2 - (chunk_count - 3) * 0.1)
    )

    # LinkedIn Article: Good for 2-3 sources, professional topic
    scores["linkedin_article"] = max(
        0.0, min(1.0, 0.5 + min(source_count, 3) * 0.15 + min(takeaway_count, 5) * 0.05)
    )

    # Blog: Good for 2+ sources, comprehensive coverage
    scores["blog"] = max(
        0.0, min(1.0, 0.4 + min(source_count, 4) * 0.1 + min(chunk_count, 10) * 0.03)
    )

    # Newsletter: Good for curated insights, personal voice
    scores["newsletter"] = max(
        0.0, min(1.0, 0.5 + min(source_count, 3) * 0.1 + min(takeaway_count, 4) * 0.05)
    )

    # Twitter Thread: Good for listicle-style, punchy insights
    scores["twitter_thread"] = max(0.0, min(1.0, 0.3 + min(takeaway_count, 7) * 0.1))

    # Substack: Good for analytical, essay-style (especially with contradictions)
    scores["substack"] = max(
        0.0,
        min(1.0, 0.4 + min(source_count, 4) * 0.1 + (0.2 if has_contradictions else 0)),
    )

    # Round scores
    return {k: round(v, 2) for k, v in scores.items()}


# ============================================================================
# Main Idea Generation
# ============================================================================


def generate_article_idea(
    source_ids: List[str],
    check_trending: bool = False,
) -> Dict[str, Any]:
    """
    Generate a complete article idea from given sources.

    Args:
        source_ids: Source IDs to use
        check_trending: Whether to check trending status

    Returns:
        Complete article idea with thesis, angle, highlights, etc.
    """
    # Extract takeaways
    takeaways = extract_top_takeaways(source_ids, max_per_source=3)

    if not takeaways:
        return {"error": "No takeaways found in sources"}

    # Generate thesis and angle via LLM
    thesis_result = generate_thesis_and_angle(takeaways)

    if not thesis_result.get("title"):
        return {"error": "Failed to generate thesis"}

    # Get source details for metadata
    total_chunks = 0
    has_contradictions = False

    for source_id in source_ids:
        source = firestore_client.get_source_by_id(source_id)
        if source:
            total_chunks += len(source.get("chunk_ids", []))

        # Check for contradiction relationships
        relationships = firestore_client.get_source_relationships(source_id)
        for rel in relationships:
            if "contradicts" in rel.get("relationship_types", {}):
                has_contradictions = True
                break

    # Assess timeliness
    timeliness = assess_timeliness(source_ids, check_trending)

    # Calculate medium scores
    medium_scores = calculate_medium_scores(
        source_count=len(source_ids),
        chunk_count=total_chunks,
        has_contradictions=has_contradictions,
        takeaway_count=len(takeaways),
    )

    # Select top highlights (2-4)
    key_highlights = takeaways[:4]

    return {
        "title": thesis_result["title"],
        "thesis": thesis_result["thesis"],
        "unique_angle": thesis_result["unique_angle"],
        "key_highlights": key_highlights,
        "timeliness": timeliness,
        "sources": source_ids,
        "strength": _calculate_strength(
            len(source_ids), total_chunks, len(takeaways), has_contradictions
        ),
        "medium_scores": medium_scores,
    }


def _calculate_strength(
    source_count: int,
    chunk_count: int,
    takeaway_count: int,
    has_contradictions: bool,
) -> float:
    """Calculate overall idea strength score."""
    score = 0.0

    # Source count (2-4 is ideal)
    if source_count >= 2:
        score += 0.3
    if source_count >= 3:
        score += 0.1

    # Chunk count (more material = stronger)
    score += min(chunk_count / 20, 0.3)

    # Takeaway count
    score += min(takeaway_count / 10, 0.2)

    # Contradiction bonus
    if has_contradictions:
        score += 0.1

    return round(min(score, 1.0), 2)


# ============================================================================
# Firestore Operations
# ============================================================================


def save_article_idea(idea: Dict[str, Any]) -> str:
    """
    Save article idea to Firestore.

    Args:
        idea: Complete article idea

    Returns:
        Generated idea_id
    """
    import uuid

    db = firestore_client.get_firestore_client()

    idea_id = f"idea-{uuid.uuid4().hex[:12]}"

    doc_data = {
        **idea,
        "idea_id": idea_id,
        "suggested_at": datetime.utcnow(),
    }

    db.collection("article_ideas").document(idea_id).set(doc_data)

    logger.info(f"Saved article idea: {idea_id}")
    return idea_id


def get_article_ideas(
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get article ideas from Firestore.

    Args:
        limit: Maximum ideas to return

    Returns:
        List of article ideas
    """
    db = firestore_client.get_firestore_client()

    query = db.collection("article_ideas")
    query = query.order_by("suggested_at", direction="DESCENDING").limit(limit)

    ideas = []
    for doc in query.stream():
        idea = doc.to_dict()
        # Convert timestamp to ISO string
        if idea.get("suggested_at") and hasattr(idea["suggested_at"], "isoformat"):
            idea["suggested_at"] = idea["suggested_at"].isoformat() + "Z"
        ideas.append(idea)

    return ideas


# ============================================================================
# Main Entry Points (called by tools.py)
# ============================================================================


def suggest_ideas_from_sources(
    min_sources: int = 2,
    focus_tags: Optional[List[str]] = None,
    limit: int = 5,
    save: bool = True,
) -> List[Dict[str, Any]]:
    """
    Auto-generate article ideas from KB source clusters.

    Args:
        min_sources: Minimum related sources required
        focus_tags: Optional tag filter
        limit: Maximum ideas to generate
        save: Whether to save ideas to Firestore

    Returns:
        List of generated ideas
    """
    # Find source clusters with relationships
    clusters = find_source_clusters(
        min_relationships=min_sources - 1,  # Relationships = sources - 1
        days=60,
        limit=limit * 2,  # Get more clusters, filter later
    )

    if not clusters:
        logger.info("No source clusters found")
        return []

    # Filter by tags if specified
    if focus_tags:
        # TODO: Implement tag filtering on clusters
        pass

    ideas = []

    for cluster in clusters[:limit]:
        # Collect source IDs from cluster
        source_ids = [cluster["primary_source"]["source_id"]]
        for rel in cluster.get("related_sources", [])[:2]:  # Max 3 sources total
            source_ids.append(rel["target_source_id"])

        # Generate idea for this cluster
        idea = generate_article_idea(source_ids)

        if "error" in idea:
            continue

        # Save if requested
        if save:
            idea_id = save_article_idea(idea)
            idea["idea_id"] = idea_id
            idea["suggested_at"] = datetime.utcnow().isoformat() + "Z"

        ideas.append(idea)

    logger.info(f"Generated {len(ideas)} article ideas")
    return ideas


def suggest_idea_for_topic(
    topic: str,
    source_ids: Optional[List[str]] = None,
    save: bool = True,
) -> Dict[str, Any]:
    """
    Evaluate and develop a specific topic into an article idea.

    Args:
        topic: The topic to evaluate
        source_ids: Optional specific sources to use
        save: Whether to save the idea

    Returns:
        Dict with idea or error
    """
    # If no sources specified, find relevant sources
    if not source_ids:
        # Search KB for sources related to topic using embeddings
        import embeddings

        query_embedding = embeddings.generate_query_embedding(topic)
        search_results = firestore_client.find_nearest(
            query_embedding=query_embedding,
            limit=10,
        )

        # Extract unique source IDs
        seen_sources = set()
        source_ids = []
        for result in search_results:
            sid = result.get("source_id")
            if sid and sid not in seen_sources:
                seen_sources.add(sid)
                source_ids.append(sid)
                if len(source_ids) >= 4:
                    break

    if not source_ids:
        return {"error": f"No relevant sources found for topic: {topic}"}

    # Check for duplicate ideas
    existing_ideas = get_article_ideas(limit=50)
    for existing in existing_ideas:
        # Simple title similarity check
        if _titles_similar(topic, existing.get("title", "")):
            return {
                "is_duplicate": True,
                "duplicate_of": existing.get("idea_id"),
                "existing_idea": existing,
            }

    # Generate the idea
    idea = generate_article_idea(source_ids)

    if "error" in idea:
        return idea

    # Override title with provided topic if thesis generation failed
    if not idea.get("title"):
        idea["title"] = topic

    # Save if requested
    if save:
        idea_id = save_article_idea(idea)
        idea["idea_id"] = idea_id
        idea["suggested_at"] = datetime.utcnow().isoformat() + "Z"

    return {"idea": idea}


def _titles_similar(title1: str, title2: str) -> bool:
    """Check if two titles are similar (simple check)."""
    t1 = title1.lower().strip()
    t2 = title2.lower().strip()

    # Exact match
    if t1 == t2:
        return True

    # One contains the other
    if t1 in t2 or t2 in t1:
        return True

    # Word overlap > 50%
    words1 = set(t1.split())
    words2 = set(t2.split())
    if len(words1) > 0 and len(words2) > 0:
        overlap = len(words1 & words2)
        min_len = min(len(words1), len(words2))
        if overlap / min_len > 0.5:
            return True

    return False


def enrich_idea_with_web(idea: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich idea with web analysis via Tavily.

    Args:
        idea: The idea to enrich

    Returns:
        Web analysis dict with trending/competition info
    """
    # TODO: Implement Tavily enrichment
    return {
        "existing_articles": 0,
        "trending": False,
        "competition": "unknown",
        "suggested_angle": None,
    }
