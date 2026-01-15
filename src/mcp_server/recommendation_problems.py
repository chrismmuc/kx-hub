"""
Problem-driven query generation for reading recommendations.

Epic 11: Problem-Driven Recommendations
Story 11.1: Problem-Based Query Generation

Generates search queries from Feynman problems instead of reading history.
Supports two modes:
- deepen: Go deeper on topics with existing evidence
- explore: Fill knowledge gaps, find new perspectives
"""

import logging
from typing import Any, Dict, List, Optional

import firestore_client
from src.llm import get_client

logger = logging.getLogger(__name__)

# Cache for problem translations (problems don't change often)
_translation_cache: Dict[str, str] = {}


# ============================================================================
# Query Templates by Mode
# ============================================================================

DEEPEN_TEMPLATES = [
    "{problem} advanced techniques expert insights",
    "{problem} deep dive comprehensive guide",
    "{problem} best practices case studies",
    "{problem} masterclass professional strategies",
]

EXPLORE_TEMPLATES = [
    "{problem} getting started beginner guide",
    "{problem} different perspectives approaches",
    "{problem} contrarian view alternative",
    "{problem} common mistakes pitfalls avoid",
    "{problem} unconventional methods",
]

BALANCED_TEMPLATES = [
    "{problem} practical guide insights",
    "{problem} latest research findings",
    "{problem} expert advice recommendations",
]


def translate_to_english(text: str, use_cache: bool = True) -> str:
    """
    Translate German text to English using Gemini Flash.

    Args:
        text: Text to translate (typically a problem statement)
        use_cache: Whether to use cached translations

    Returns:
        English translation
    """
    if use_cache and text in _translation_cache:
        logger.debug(f"Using cached translation for: {text[:50]}...")
        return _translation_cache[text]

    try:
        client = get_client(model="gemini-flash")

        prompt = f"""Translate this German text to English.
Only return the translation, nothing else.
Keep it natural and search-friendly.

German: {text}

English:"""

        response = client.generate(prompt)
        translation = response.text.strip()

        # Cache the result
        if use_cache:
            _translation_cache[text] = translation

        logger.info(f"Translated: '{text[:40]}...' → '{translation[:40]}...'")
        return translation

    except Exception as e:
        logger.warning(f"Translation failed, using original: {e}")
        return text


def get_active_problems(problem_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Get active problems, optionally filtered by IDs.

    Args:
        problem_ids: Optional list of problem IDs to filter

    Returns:
        List of problem dictionaries with evidence counts
    """
    try:
        db = firestore_client.get_firestore_client()

        if problem_ids:
            # Fetch specific problems
            problems = []
            for pid in problem_ids:
                doc = db.collection("problems").document(pid).get()
                if doc.exists:
                    data = doc.to_dict()
                    if data.get("status") == "active":
                        data["problem_id"] = doc.id
                        data["evidence_count"] = len(data.get("evidence", []))
                        problems.append(data)
        else:
            # Fetch all active problems
            query = db.collection("problems").where("status", "==", "active")
            problems = []
            for doc in query.stream():
                data = doc.to_dict()
                data["problem_id"] = doc.id
                data["evidence_count"] = len(data.get("evidence", []))
                problems.append(data)

        logger.info(f"Loaded {len(problems)} active problems")
        return problems

    except Exception as e:
        logger.error(f"Failed to load problems: {e}")
        return []


def sort_problems_by_mode(
    problems: List[Dict[str, Any]],
    mode: str
) -> List[Dict[str, Any]]:
    """
    Sort problems based on mode strategy.

    Args:
        problems: List of problems with evidence_count
        mode: "deepen" | "explore" | "balanced"

    Returns:
        Sorted list of problems
    """
    if mode == "deepen":
        # High evidence first - go deeper on what you know
        return sorted(problems, key=lambda p: p.get("evidence_count", 0), reverse=True)

    elif mode == "explore":
        # Low evidence first - fill knowledge gaps
        return sorted(problems, key=lambda p: p.get("evidence_count", 0))

    else:  # balanced
        # Interleave: alternate between high and low evidence
        sorted_by_evidence = sorted(problems, key=lambda p: p.get("evidence_count", 0))
        high = sorted_by_evidence[len(sorted_by_evidence)//2:]
        low = sorted_by_evidence[:len(sorted_by_evidence)//2]

        interleaved = []
        for h, l in zip(high[::-1], low):
            interleaved.extend([h, l])

        # Add any remaining
        remaining = len(high) - len(low)
        if remaining > 0:
            interleaved.extend(high[:remaining])
        elif remaining < 0:
            interleaved.extend(low[remaining:])

        return interleaved


def get_evidence_keywords(problem: Dict[str, Any], max_keywords: int = 5) -> List[str]:
    """
    Extract keywords from problem's existing evidence for deepen queries.

    Args:
        problem: Problem dictionary with evidence
        max_keywords: Maximum keywords to extract

    Returns:
        List of keyword strings
    """
    keywords = set()

    evidence = problem.get("evidence", [])
    for ev in evidence[:10]:  # Limit to first 10 evidence items
        # Get source title
        source_title = ev.get("source_title", "")
        if source_title:
            # Extract significant words (>4 chars)
            words = [w for w in source_title.split() if len(w) > 4]
            keywords.update(words[:2])

        # Get author
        author = ev.get("author", "")
        if author and len(author) > 3:
            keywords.add(author.split()[0])  # First name/word

    return list(keywords)[:max_keywords]


def generate_problem_queries(
    problems: Optional[List[str]] = None,
    mode: str = "balanced",
    max_queries: int = 8,
    queries_per_problem: int = 2,
) -> List[Dict[str, Any]]:
    """
    Generate search queries based on Feynman problems.

    Args:
        problems: Optional list of problem IDs (None = all active)
        mode: "deepen" | "explore" | "balanced"
        max_queries: Maximum total queries to generate
        queries_per_problem: Queries to generate per problem

    Returns:
        List of query dictionaries:
        - query: Search query string (English)
        - problem_id: Associated problem ID
        - problem_text: Original problem text (German)
        - mode: Query mode (deepen/explore)
        - evidence_count: Problem's current evidence count
    """
    try:
        logger.info(f"Generating queries: mode={mode}, max={max_queries}")

        # Load problems
        problem_list = get_active_problems(problems)

        if not problem_list:
            logger.warning("No active problems found")
            return []

        # Sort by mode
        sorted_problems = sort_problems_by_mode(problem_list, mode)

        # Select templates based on mode
        if mode == "deepen":
            templates = DEEPEN_TEMPLATES
        elif mode == "explore":
            templates = EXPLORE_TEMPLATES
        else:
            templates = BALANCED_TEMPLATES

        queries = []
        template_idx = 0

        for problem in sorted_problems:
            if len(queries) >= max_queries:
                break

            problem_text = problem.get("problem", "")
            problem_id = problem.get("problem_id", "")
            evidence_count = problem.get("evidence_count", 0)

            # Translate problem to English
            problem_en = translate_to_english(problem_text)

            # Determine effective mode for this problem
            if mode == "balanced":
                # In balanced mode, use deepen for high-evidence, explore for low
                effective_mode = "deepen" if evidence_count >= 2 else "explore"
                effective_templates = DEEPEN_TEMPLATES if effective_mode == "deepen" else EXPLORE_TEMPLATES
            else:
                effective_mode = mode
                effective_templates = templates

            # Generate queries for this problem
            for _ in range(queries_per_problem):
                if len(queries) >= max_queries:
                    break

                template = effective_templates[template_idx % len(effective_templates)]
                template_idx += 1

                # Build query
                query_text = template.format(problem=problem_en)

                # For deepen mode, add evidence keywords
                if effective_mode == "deepen" and evidence_count > 0:
                    keywords = get_evidence_keywords(problem, max_keywords=3)
                    if keywords:
                        query_text = f"{query_text} {' '.join(keywords)}"

                queries.append({
                    "query": query_text,
                    "problem_id": problem_id,
                    "problem_text": problem_text,
                    "problem_en": problem_en,
                    "mode": effective_mode,
                    "evidence_count": evidence_count,
                })

        logger.info(f"Generated {len(queries)} queries from {len(sorted_problems)} problems")
        return queries

    except Exception as e:
        logger.error(f"Failed to generate problem queries: {e}")
        return []


def format_query_for_tavily(query_dict: Dict[str, Any]) -> str:
    """
    Format a query dictionary into a Tavily-optimized search string.

    Args:
        query_dict: Query dictionary from generate_problem_queries()

    Returns:
        Formatted query string
    """
    query = query_dict.get("query", "")

    # Tavily works best with natural language queries
    # Remove excessive punctuation but keep structure
    query = query.replace('"', "").replace("'", "")

    return query.strip()
