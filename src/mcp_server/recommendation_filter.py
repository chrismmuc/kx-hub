"""
Quality filtering and deduplication for reading recommendations.

Story 3.5: AI-Powered Reading Recommendations

Provides:
- Gemini-based content depth scoring (1-5 scale)
- "Why recommended" explanation generation
- Source diversity cap (max 2 per domain)
- KB deduplication via embedding similarity
"""

import logging
import os
from typing import List, Dict, Any, Optional
from collections import defaultdict

import vertexai
from vertexai.generative_models import GenerativeModel

import firestore_client
import embeddings

logger = logging.getLogger(__name__)

# Similarity threshold for deduplication
DEDUP_SIMILARITY_THRESHOLD = 0.85

# Maximum recommendations per domain
MAX_PER_DOMAIN = 2

# Minimum depth score required
MIN_DEPTH_SCORE = 3

# Global model cache
_gemini_model = None


def get_gemini_model() -> GenerativeModel:
    """
    Get or create Gemini model instance (cached).

    Returns:
        Initialized GenerativeModel
    """
    global _gemini_model

    if _gemini_model is None:
        project = os.getenv('GCP_PROJECT')
        region = os.getenv('GCP_REGION')

        logger.info(f"Initializing Gemini model in project={project}, region={region}")
        vertexai.init(project=project, location=region)

        # Use Gemini 2.0 Flash for cost efficiency
        _gemini_model = GenerativeModel("gemini-2.0-flash-001")
        logger.info("Gemini model initialized")

    return _gemini_model


def score_content_depth(
    title: str,
    content: str,
    url: str
) -> Dict[str, Any]:
    """
    Score article depth using Gemini.

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
        model = get_gemini_model()

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

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Parse JSON response
        import json
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        result = json.loads(response_text)

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


def check_kb_duplicate(title: str, content: str) -> Dict[str, Any]:
    """
    Check if recommendation content already exists in KB.

    Uses embedding similarity to detect duplicates.

    Args:
        title: Recommendation title
        content: Recommendation snippet

    Returns:
        Dictionary with:
        - is_duplicate: Boolean
        - similarity_score: Highest similarity found (0-1)
        - similar_chunk_id: ID of most similar chunk if duplicate
    """
    try:
        # Combine title and content for embedding
        text_to_embed = f"{title}. {content[:300]}"

        # Generate embedding
        embedding = embeddings.generate_query_embedding(text_to_embed)

        # Search for similar content in KB
        similar_chunks = firestore_client.find_nearest(
            embedding_vector=embedding,
            limit=1
        )

        if not similar_chunks:
            return {
                'is_duplicate': False,
                'similarity_score': 0.0,
                'similar_chunk_id': None
            }

        # Calculate cosine similarity (Firestore returns by similarity, not distance)
        # Since find_nearest returns most similar first, we need to check
        # If the chunk is very similar, it's a duplicate

        # Firestore vector search doesn't return distance by default
        # We'll use a heuristic: check if titles are similar
        top_chunk = similar_chunks[0]
        top_title = top_chunk.get('title', '').lower()
        check_title = title.lower()

        # Simple title similarity check
        title_words = set(check_title.split())
        top_words = set(top_title.split())
        common_words = title_words & top_words
        title_similarity = len(common_words) / max(len(title_words), 1)

        # Consider duplicate if high title similarity
        is_dup = title_similarity > 0.6

        return {
            'is_duplicate': is_dup,
            'similarity_score': title_similarity,
            'similar_chunk_id': top_chunk.get('id') if is_dup else None,
            'similar_title': top_title if is_dup else None
        }

    except Exception as e:
        logger.warning(f"Failed to check KB duplicate: {e}")
        return {
            'is_duplicate': False,
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

            # 2. Check for KB duplicates
            if check_duplicates:
                dup_check = check_kb_duplicate(title, content)
                if dup_check.get('is_duplicate'):
                    filtered_out['duplicate_count'] += 1
                    logger.debug(f"Filtered (duplicate): {title[:50]}...")
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
    Score multiple items efficiently using batched Gemini calls.

    Args:
        items: List of items with title, content, url
        batch_size: Number of items to score per API call

    Returns:
        List of items with depth_score added
    """
    try:
        model = get_gemini_model()
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
                response = model.generate_content(batch_prompt)
                response_text = response.text.strip()

                import json
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                    response_text = response_text.strip()

                scores = json.loads(response_text)

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
