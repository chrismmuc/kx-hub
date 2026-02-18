"""
KB-Aware Two-Stage Snippet Extraction.

Epic 13 Story 13.2: Extracts key passages from Reader articles using a
two-stage pipeline that prioritizes novel insights aligned with Feynman problems.

Pipeline:
  Stage 1  - LLM extracts N×2 candidate snippets (direct quotes)
  Stage 1.5 - KB enrichment: embedding similarity for novelty + problem matching
  Stage 2  - LLM judge selects top N snippets using KB context

Usage:
    from src.knowledge_cards.snippet_extractor import extract_snippets
    snippets = extract_snippets(
        text="Article full text...",
        title="Article Title",
        author="Author Name",
        word_count=3000,
    )
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# KB service imports (graceful degradation if unavailable)
_kb_services_available = None

try:
    from src.mcp_server import embeddings, firestore_client
    from src.embed.problem_matcher import cosine_similarity
except ImportError:
    try:
        import embeddings
        import firestore_client
        from problem_matcher import cosine_similarity
    except ImportError:
        embeddings = None
        firestore_client = None
        cosine_similarity = None

# LLM imports
try:
    from src.llm import BaseLLMClient, GenerationConfig, get_client, get_model_info, get_default_model
except ImportError:
    from llm import BaseLLMClient, GenerationConfig, get_client, get_model_info, get_default_model


# ============================================================================
# Context Window Overflow Threshold
# ============================================================================
# Computed from the default model's max_context. Text exceeding this is
# truncated before being sent to the LLM, and the article is tagged kx-overflow.
#
# Formula: (max_context − overhead) × chars_per_token × safety_margin
#   - overhead:      6 000 tokens (prompt template + max_output_tokens)
#   - chars_per_token: 3.5 (conservative for mixed-language content)
#   - safety_margin:   0.75 (leave room for tokenizer variance)

_PROMPT_OVERHEAD_TOKENS = 6_000
_CHARS_PER_TOKEN = 3.5
_SAFETY_MARGIN = 0.75


def _compute_overflow_threshold() -> int:
    """Compute max input text chars from the default model's context window."""
    try:
        model_name = get_default_model()
        model_info = get_model_info(model_name)
        if model_info:
            available = model_info.max_context - _PROMPT_OVERHEAD_TOKENS
            return int(available * _CHARS_PER_TOKEN * _SAFETY_MARGIN)
    except Exception:
        pass
    return 600_000  # safe fallback (~200K token model)


OVERFLOW_THRESHOLD = _compute_overflow_threshold()


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ExtractedSnippet:
    """Public API output - a selected snippet from an article."""

    text: str  # Direct quote (2-4 sentences)
    context: str  # Why this matters (1 sentence)
    position: str  # "intro" | "middle" | "conclusion"


@dataclass
class CandidateSnippet:
    """Internal representation flowing through Stage 1 → 1.5 → 2."""

    text: str
    context: str
    position: str
    kb_novelty: float = 1.0  # 1.0 - similarity (higher = more novel)
    is_novel: bool = True
    similar_to: Optional[str] = None  # Most similar kb_item title
    problem_relevance: float = 0.0
    problem_id: Optional[str] = None
    problem_text: Optional[str] = None


class SnippetExtractionError(Exception):
    """Raised when snippet extraction fails after retries."""

    pass


# ============================================================================
# Pure Functions
# ============================================================================


def calculate_snippet_count(word_count: int) -> int:
    """
    Calculate target snippet count based on article length.

    Args:
        word_count: Article word count

    Returns:
        Target number of snippets (2-15)
    """
    return max(2, min(15, word_count // 800))


# ============================================================================
# LLM Client Management
# ============================================================================

_llm_client: Optional[BaseLLMClient] = None


def _get_llm_client() -> BaseLLMClient:
    """Get or create cached LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = get_client()
        logger.info(f"Initialized snippet extractor LLM client: {_llm_client}")
    return _llm_client


# ============================================================================
# KB Service Availability
# ============================================================================


def _has_kb_services() -> bool:
    """Check if KB services (embeddings + firestore) are available."""
    global _kb_services_available
    if _kb_services_available is not None:
        return _kb_services_available

    _kb_services_available = (
        embeddings is not None
        and firestore_client is not None
        and cosine_similarity is not None
    )
    if not _kb_services_available:
        logger.warning("KB services unavailable - skipping enrichment")
    return _kb_services_available


# ============================================================================
# Stage 1: Candidate Extraction
# ============================================================================


def _extract_candidates(
    text: str,
    title: str,
    author: str,
    candidate_count: int,
) -> List[CandidateSnippet]:
    """
    Stage 1: Extract candidate snippets using LLM.

    Requests N×2 candidates for diversity, emphasizing direct quotes.

    Args:
        text: Full article text
        title: Article title
        author: Article author
        candidate_count: Number of candidates to request (typically target×2)

    Returns:
        List of CandidateSnippet objects

    Raises:
        SnippetExtractionError: If extraction fails after retry
    """
    client = _get_llm_client()
    config = GenerationConfig(temperature=0.3, max_output_tokens=4096)

    if len(text) > OVERFLOW_THRESHOLD:
        original_len = len(text)
        # Truncate, preferring a sentence boundary in the last 1 KB
        text = text[:OVERFLOW_THRESHOLD]
        boundary = text.rfind(". ", max(0, OVERFLOW_THRESHOLD - 1000))
        if boundary > OVERFLOW_THRESHOLD * 0.9:
            text = text[: boundary + 1]
        logger.warning(
            f"Stage 1: text TRUNCATED from {original_len:,} to {len(text):,} chars "
            f"(model limit ≈{OVERFLOW_THRESHOLD:,}) for '{title}'"
        )

    prompt = f"""Extract exactly {candidate_count} key passages from this article as DIRECT QUOTES.

Article: "{title}" by {author}

<article>
{text}
</article>

RULES:
1. Each snippet MUST be a VERBATIM quote from the article (2-4 sentences, copied exactly)
2. Do NOT paraphrase or summarize - use the author's exact words
3. Select passages that contain insights, surprising claims, or actionable advice
4. Cover different parts of the article (intro, middle, conclusion)
5. Avoid generic/obvious statements

Return a JSON object with a "snippets" array:
{{
  "snippets": [
    {{
      "text": "Exact verbatim quote from the article...",
      "context": "One sentence explaining why this passage matters",
      "position": "intro" | "middle" | "conclusion"
    }}
  ]
}}"""

    for attempt in range(2):
        try:
            result = client.generate_json(prompt, config=config)
            snippets_data = result.get("snippets", [])

            if not snippets_data:
                if attempt == 0:
                    logger.warning("Stage 1: empty snippets, retrying")
                    continue
                raise SnippetExtractionError("Stage 1 returned no snippets after retry")

            candidates = []
            for s in snippets_data:
                if not s.get("text"):
                    continue
                candidates.append(
                    CandidateSnippet(
                        text=s["text"],
                        context=s.get("context", ""),
                        position=s.get("position", "middle"),
                    )
                )

            logger.info(f"Stage 1: extracted {len(candidates)} candidates")
            return candidates

        except (ValueError, json.JSONDecodeError) as e:
            if attempt == 0:
                logger.warning(f"Stage 1: JSON parse error, retrying: {e}")
                continue
            raise SnippetExtractionError(
                f"Stage 1 JSON parse failed after retry: {e}"
            ) from e
        except SnippetExtractionError:
            raise
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Stage 1: unexpected error, retrying: {e}")
                continue
            raise SnippetExtractionError(
                f"Stage 1 failed after retry: {e}"
            ) from e

    raise SnippetExtractionError("Stage 1 exhausted all retries")


# ============================================================================
# Stage 1.5: KB Enrichment
# ============================================================================


def _enrich_single_candidate(
    candidate: CandidateSnippet,
    problems: List[dict],
) -> CandidateSnippet:
    """
    Enrich a single candidate with KB novelty and problem relevance.

    Args:
        candidate: Candidate to enrich
        problems: Active problems with embeddings

    Returns:
        Enriched candidate (mutated in place and returned)
    """
    try:
        # Generate embedding for candidate text
        snippet_embedding = embeddings.generate_query_embedding(candidate.text)

        # KB novelty: find most similar existing item
        similar_items = firestore_client.find_nearest(
            embedding_vector=snippet_embedding, limit=1
        )
        if similar_items:
            top_item = similar_items[0]
            # Firestore COSINE distance = 1 - cosine_similarity
            # find_nearest returns items ordered by distance (closest first)
            # We use cosine_similarity to compute novelty
            item_embedding = top_item.get("embedding")
            if item_embedding:
                if hasattr(item_embedding, "to_map_value"):
                    item_embedding = list(item_embedding)
                similarity = cosine_similarity(snippet_embedding, item_embedding)
            else:
                # If no embedding in result, assume moderate similarity
                similarity = 0.5

            candidate.kb_novelty = round(1.0 - similarity, 4)
            candidate.similar_to = top_item.get("title", "Unknown")

            # Novelty thresholds: Novel >0.25, Related 0.10-0.25, Duplicate <0.10
            candidate.is_novel = candidate.kb_novelty >= 0.10
        else:
            # Empty KB: everything is novel
            candidate.kb_novelty = 1.0
            candidate.is_novel = True

        # Problem relevance: compare with each active problem
        if problems:
            best_relevance = 0.0
            best_problem = None
            for problem in problems:
                problem_embedding = problem.get("embedding", [])
                if problem_embedding:
                    if hasattr(problem_embedding, "to_map_value"):
                        problem_embedding = list(problem_embedding)
                    relevance = cosine_similarity(snippet_embedding, problem_embedding)
                    if relevance > best_relevance:
                        best_relevance = relevance
                        best_problem = problem

            if best_problem and best_relevance > 0:
                candidate.problem_relevance = round(best_relevance, 4)
                candidate.problem_id = best_problem.get("problem_id")
                candidate.problem_text = best_problem.get("problem")

    except Exception as e:
        logger.warning(f"Failed to enrich candidate, keeping defaults: {e}")
        # Candidate keeps default values (fully novel, no problem match)

    return candidate


def _enrich_with_kb_context(
    candidates: List[CandidateSnippet],
) -> List[CandidateSnippet]:
    """
    Stage 1.5: Enrich candidates with KB novelty and problem relevance.

    Runs in parallel with ThreadPoolExecutor for performance.
    Gracefully degrades if KB services are unavailable.

    Args:
        candidates: List of candidates from Stage 1

    Returns:
        Enriched candidates
    """
    if not _has_kb_services():
        logger.info("Stage 1.5: KB services unavailable, skipping enrichment")
        return candidates

    # Load problems once (cached for all candidates)
    try:
        problems = firestore_client.get_active_problems_with_embeddings()
        logger.info(f"Stage 1.5: loaded {len(problems)} active problems")
    except Exception as e:
        logger.warning(f"Stage 1.5: failed to load problems: {e}")
        problems = []

    # Enrich candidates in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_enrich_single_candidate, c, problems): i
            for i, c in enumerate(candidates)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                candidates[idx] = future.result()
            except Exception as e:
                logger.warning(
                    f"Stage 1.5: enrichment failed for candidate {idx}: {e}"
                )
                # Candidate keeps default values

    novel_count = sum(1 for c in candidates if c.is_novel)
    problem_count = sum(1 for c in candidates if c.problem_relevance > 0)
    logger.info(
        f"Stage 1.5: {novel_count}/{len(candidates)} novel, "
        f"{problem_count} with problem relevance"
    )

    return candidates


# ============================================================================
# Stage 2: KB-Aware Judge
# ============================================================================


def _build_candidate_summary(candidates: List[CandidateSnippet]) -> str:
    """Build a text summary of candidates with KB context for the judge prompt."""
    lines = []
    all_duplicates = all(not c.is_novel for c in candidates)

    for i, c in enumerate(candidates):
        line = f"[{i}] \"{c.text[:200]}{'...' if len(c.text) > 200 else ''}\""
        line += f"\n    Context: {c.context}"
        line += f"\n    Position: {c.position}"
        line += f"\n    Novelty: {c.kb_novelty:.2f}"

        if c.similar_to:
            novelty_label = "NOVEL" if c.kb_novelty >= 0.25 else (
                "RELATED" if c.kb_novelty >= 0.10 else "DUPLICATE"
            )
            line += f" ({novelty_label} - similar to: {c.similar_to})"

        if c.problem_relevance > 0:
            line += f"\n    Problem relevance: {c.problem_relevance:.2f}"
            if c.problem_text:
                line += f" (matches: {c.problem_text[:80]})"

        lines.append(line)

    summary = "\n\n".join(lines)

    if all_duplicates:
        summary += (
            "\n\nNOTE: All candidates overlap with existing KB content. "
            "Prioritize quality and problem relevance over novelty."
        )

    return summary


def _judge_snippets(
    candidates: List[CandidateSnippet],
    target_count: int,
    title: str,
    author: str,
) -> List[ExtractedSnippet]:
    """
    Stage 2: Use LLM judge to select best snippets with KB awareness.

    Scoring: 0.3×quality + 0.3×novelty + 0.3×problem_relevance + 0.1×diversity

    Falls back to local composite scoring if judge returns invalid results.

    Args:
        candidates: Enriched candidates from Stage 1.5
        target_count: Number of snippets to select
        title: Article title
        author: Article author

    Returns:
        List of ExtractedSnippet (final output)
    """
    if len(candidates) <= target_count:
        return [
            ExtractedSnippet(text=c.text, context=c.context, position=c.position)
            for c in candidates
        ]

    client = _get_llm_client()
    config = GenerationConfig(temperature=0.2, max_output_tokens=2048)

    candidate_summary = _build_candidate_summary(candidates)

    prompt = f"""You are a knowledge curation judge. Select the {target_count} best snippets from "{title}" by {author}.

CANDIDATES:
{candidate_summary}

SCORING CRITERIA (weight each factor):
- Quality (30%): Insight depth, actionability, surprise value
- KB Novelty (30%): Prefer snippets that add NEW knowledge (higher novelty score)
- Problem Relevance (30%): Prefer snippets aligned with user's research problems
- Diversity (10%): Cover different parts of the article, different themes

Return a JSON object with a "selected" array of indices (0-based):
{{
  "selected": [0, 3, 5],
  "reasoning": "Brief explanation of selection"
}}"""

    try:
        result = client.generate_json(prompt, config=config)
        selected_indices = result.get("selected", [])

        # Validate indices
        valid_indices = [
            i for i in selected_indices
            if isinstance(i, int) and 0 <= i < len(candidates)
        ]
        # Remove duplicates preserving order
        seen = set()
        unique_indices = []
        for i in valid_indices:
            if i not in seen:
                seen.add(i)
                unique_indices.append(i)
        valid_indices = unique_indices

        if len(valid_indices) == target_count:
            return [
                ExtractedSnippet(
                    text=candidates[i].text,
                    context=candidates[i].context,
                    position=candidates[i].position,
                )
                for i in valid_indices
            ]

        # Wrong count: pad or trim using local composite score
        logger.warning(
            f"Stage 2: judge returned {len(valid_indices)} indices, "
            f"expected {target_count}. Using composite fallback."
        )
        return _fallback_select(candidates, target_count, valid_indices)

    except Exception as e:
        logger.warning(f"Stage 2: judge failed, using composite fallback: {e}")
        return _fallback_select(candidates, target_count)


def _composite_score(candidate: CandidateSnippet) -> float:
    """Calculate local composite score for fallback ranking."""
    return (
        0.3 * 0.5  # Assume mid quality since we can't score locally
        + 0.3 * candidate.kb_novelty
        + 0.3 * candidate.problem_relevance
        + 0.1 * (0.5 if candidate.position != "middle" else 0.3)  # diversity proxy
    )


def _fallback_select(
    candidates: List[CandidateSnippet],
    target_count: int,
    preferred_indices: Optional[List[int]] = None,
) -> List[ExtractedSnippet]:
    """
    Fallback selection using local composite scoring.

    Used when judge returns wrong count or fails entirely.

    Args:
        candidates: All candidates
        target_count: Desired count
        preferred_indices: Indices already selected by judge (if any)

    Returns:
        List of ExtractedSnippet
    """
    if preferred_indices is None:
        preferred_indices = []

    # Start with judge's selections
    selected_indices = set(preferred_indices)

    # Rank remaining candidates by composite score
    remaining = [
        (i, _composite_score(c))
        for i, c in enumerate(candidates)
        if i not in selected_indices
    ]
    remaining.sort(key=lambda x: x[1], reverse=True)

    # Pad if needed
    for idx, _score in remaining:
        if len(selected_indices) >= target_count:
            break
        selected_indices.add(idx)

    # Trim if needed (keep highest scoring from preferred)
    if len(selected_indices) > target_count:
        scored = [(i, _composite_score(candidates[i])) for i in selected_indices]
        scored.sort(key=lambda x: x[1], reverse=True)
        selected_indices = {i for i, _ in scored[:target_count]}

    # Build output preserving candidate order
    result = []
    for i in sorted(selected_indices):
        c = candidates[i]
        result.append(
            ExtractedSnippet(text=c.text, context=c.context, position=c.position)
        )

    return result


# ============================================================================
# Main Entry Point
# ============================================================================


def extract_snippets(
    text: str,
    title: str,
    author: str,
    word_count: int,
    source_url: Optional[str] = None,
) -> List[ExtractedSnippet]:
    """
    Extract key snippets from an article using the two-stage pipeline.

    Stage 1:   LLM extracts N×2 candidate verbatim quotes
    Stage 1.5: KB enrichment (novelty + problem relevance)
    Stage 2:   LLM judge selects top N with KB awareness

    Args:
        text: Full article text
        title: Article title
        author: Article author
        word_count: Article word count
        source_url: Optional source URL for logging

    Returns:
        List of ExtractedSnippet objects (2-15 snippets)

    Raises:
        SnippetExtractionError: If Stage 1 fails after retries
    """
    if not text or not text.strip():
        logger.info("Empty text provided, returning no snippets")
        return []

    target_count = calculate_snippet_count(word_count)
    candidate_count = target_count * 2

    logger.info(
        f"Extracting snippets from '{title}' "
        f"(words={word_count}, target={target_count}, candidates={candidate_count})"
    )

    # Stage 1: Extract candidates
    candidates = _extract_candidates(text, title, author, candidate_count)

    if not candidates:
        logger.warning("Stage 1 returned no candidates")
        return []

    # Stage 1.5: KB enrichment (skip if services unavailable)
    if _has_kb_services():
        candidates = _enrich_with_kb_context(candidates)

    # Stage 2: Judge selects best snippets
    snippets = _judge_snippets(candidates, target_count, title, author)

    logger.info(
        f"Extraction complete: {len(snippets)} snippets from '{title}'"
        + (f" (url={source_url})" if source_url else "")
    )

    return snippets
