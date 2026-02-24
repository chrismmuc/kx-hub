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
from src.llm import get_client, GenerationConfig

logger = logging.getLogger(__name__)

# Mode instructions for LLM query generation
_MODE_INSTRUCTIONS = {
    "deepen": "Target advanced/niche aspects not covered by existing evidence. Assume the user knows the basics.",
    "explore": "Target adjacent fields and contrarian perspectives the user hasn't encountered.",
    "balanced": "Generate one gap-filling query and one perspective-expanding query.",
}

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


def _build_evidence_summary(evidence: List[Dict[str, Any]], max_items: int = 5) -> str:
    """
    Build compact evidence summary for LLM prompt.

    Extracts source_title, author, and first takeaway from each evidence item.
    Returns a bullet list string, capped at max_items.
    """
    lines = []
    for ev in evidence[:max_items]:
        title = ev.get("source_title", "Unknown")
        author = ev.get("author", "")
        takeaways = ev.get("takeaways", [])
        first_takeaway = takeaways[0] if takeaways else ""

        if author and first_takeaway:
            lines.append(f"- {title} ({author}) — {first_takeaway}")
        elif author:
            lines.append(f"- {title} ({author})")
        elif first_takeaway:
            lines.append(f"- {title} — {first_takeaway}")
        else:
            lines.append(f"- {title}")

    return "\n".join(lines)


def generate_evidence_queries(
    problem_en: str,
    evidence: List[Dict[str, Any]],
    mode: str,
    n_queries: int = 2,
) -> List[str]:
    """
    Use LLM to generate evidence-aware search queries.

    Returns list of query strings, or empty list on failure (triggers template fallback).
    """
    try:
        summary = _build_evidence_summary(evidence)
        mode_instruction = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS["balanced"])

        prompt = f"""You are generating web search queries for a research tool (Tavily).

RESEARCH PROBLEM: "{problem_en}"

WHAT THE USER ALREADY KNOWS (do not search for these topics again):
{summary}

Generate exactly {n_queries} search queries that:
1. Target GAPS not covered by existing evidence
2. Explore specific sub-topics, niche angles, or adjacent fields
3. Are optimized for web search (keywords, not questions — max 8 words each)
4. Will find substantial articles, NOT top-10 listicles or beginner guides

Mode: {mode_instruction}

Return one query per line. No explanations, no numbering."""

        client = get_client(model="gemini-flash")
        config = GenerationConfig(temperature=0.3, max_output_tokens=200)
        response = client.generate(prompt, config=config)

        # Parse: split by newline, strip, filter empty
        queries = [
            line.strip().lstrip("0123456789.-) ")
            for line in response.text.strip().split("\n")
            if line.strip()
        ]
        queries = [q for q in queries if q][:n_queries]

        if queries:
            logger.info(f"LLM generated {len(queries)} queries for: {problem_en[:40]}...")
            return queries

        logger.warning("LLM returned no parseable queries, falling back to templates")
        return []

    except Exception as e:
        logger.warning(f"LLM query generation failed, falling back to templates: {e}")
        return []


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


def filter_problems_by_topic(
    problems: List[Dict[str, Any]],
    topic_filter: List[str],
) -> List[Dict[str, Any]]:
    """
    Filter problems to only those matching topic keywords.

    Matches against problem text, tags, and category fields.
    Case-insensitive keyword matching.

    Args:
        problems: List of problem dictionaries
        topic_filter: List of topic keywords to match (e.g. ["AI", "software", "development"])

    Returns:
        Filtered list of problems matching at least one keyword
    """
    if not topic_filter:
        return problems

    keywords_lower = [kw.lower() for kw in topic_filter]
    filtered = []

    for problem in problems:
        # Build searchable text from problem fields
        searchable_parts = [
            problem.get("problem", ""),
            problem.get("category", ""),
            " ".join(problem.get("tags", [])),
        ]
        searchable_text = " ".join(searchable_parts).lower()

        # Match if any keyword appears in searchable text
        if any(kw in searchable_text for kw in keywords_lower):
            filtered.append(problem)

    logger.info(
        f"Topic filter [{', '.join(topic_filter)}]: "
        f"{len(filtered)}/{len(problems)} problems matched"
    )
    return filtered


def generate_problem_queries(
    problems: Optional[List[str]] = None,
    mode: str = "balanced",
    max_queries: int = 8,
    queries_per_problem: int = 2,
    topic_filter: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate search queries based on Feynman problems.

    Args:
        problems: Optional list of problem IDs (None = all active)
        mode: "deepen" | "explore" | "balanced"
        max_queries: Maximum total queries to generate
        queries_per_problem: Queries to generate per problem
        topic_filter: Optional list of topic keywords to restrict which problems
                      are used for query generation (e.g. ["AI", "software", "development"]).
                      Only problems matching at least one keyword are included.

    Returns:
        List of query dictionaries:
        - query: Search query string (English)
        - problem_id: Associated problem ID
        - problem_text: Original problem text (German)
        - mode: Query mode (deepen/explore)
        - evidence_count: Problem's current evidence count
        - query_method: "llm" or "template"
    """
    try:
        logger.info(f"Generating queries: mode={mode}, max={max_queries}, topic_filter={topic_filter}")

        # Load problems
        problem_list = get_active_problems(problems)

        if not problem_list:
            logger.warning("No active problems found")
            return []

        # Apply topic filter to restrict which problems generate queries
        if topic_filter:
            problem_list = filter_problems_by_topic(problem_list, topic_filter)
            if not problem_list:
                logger.warning(f"No problems matched topic filter: {topic_filter}")
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

            # Try LLM-generated queries first when evidence exists
            if evidence_count > 0:
                remaining = max_queries - len(queries)
                n = min(queries_per_problem, remaining)
                llm_queries = generate_evidence_queries(
                    problem_en=problem_en,
                    evidence=problem.get("evidence", []),
                    mode=effective_mode,
                    n_queries=n,
                )
                if llm_queries:
                    for q in llm_queries:
                        if len(queries) >= max_queries:
                            break
                        queries.append({
                            "query": q,
                            "problem_id": problem_id,
                            "problem_text": problem_text,
                            "problem_en": problem_en,
                            "mode": effective_mode,
                            "evidence_count": evidence_count,
                            "query_method": "llm",
                        })
                    continue  # skip template generation for this problem

            # Template fallback (no evidence, or LLM failed)
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
                    "query_method": "template",
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
