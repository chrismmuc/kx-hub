"""
Snippet Extraction Pipeline.

Epic 13 Story 13.2: Extracts key passages from Reader articles as direct quotes.
LLM decides how many snippets to extract based on article content, with emphasis
on full-article coverage.

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
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

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


class SnippetExtractionError(Exception):
    """Raised when snippet extraction fails after retries."""

    pass


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
# Snippet Extraction
# ============================================================================


def _extract_snippets_llm(
    text: str,
    title: str,
    author: str,
) -> List[ExtractedSnippet]:
    """
    Extract snippets from article text using LLM.

    Open-ended extraction: LLM decides how many snippets based on article
    content and length. Enhanced prompt ensures full-article coverage.

    Args:
        text: Full article text
        title: Article title
        author: Article author

    Returns:
        List of ExtractedSnippet objects

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
            f"Text TRUNCATED from {original_len:,} to {len(text):,} chars "
            f"(model limit ≈{OVERFLOW_THRESHOLD:,}) for '{title}'"
        )

    prompt = f"""Extract the most important passages from this article as DIRECT QUOTES.

Article: "{title}" by {author}

<article>
{text}
</article>

RULES:
1. Each snippet MUST be a VERBATIM quote from the article (2-4 sentences, copied exactly)
2. Do NOT paraphrase or summarize - use the author's exact words
3. Select passages that contain insights, surprising claims, or actionable advice
4. Distribute snippets proportionally across the ENTIRE article — early, middle, AND late sections must all be represented. Do not cluster snippets in the first half.
5. Avoid generic/obvious statements
6. Extract as many high-quality snippets as the article warrants — short articles may have 2-3, long articles may have 10-20+

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
                    logger.warning("Empty snippets, retrying")
                    continue
                raise SnippetExtractionError("Returned no snippets after retry")

            snippets = []
            for s in snippets_data:
                if not s.get("text"):
                    continue
                snippets.append(
                    ExtractedSnippet(
                        text=s["text"],
                        context=s.get("context", ""),
                        position=s.get("position", "middle"),
                    )
                )

            logger.info(f"Extracted {len(snippets)} snippets")
            return snippets

        except (ValueError, json.JSONDecodeError) as e:
            if attempt == 0:
                logger.warning(f"JSON parse error, retrying: {e}")
                continue
            raise SnippetExtractionError(
                f"JSON parse failed after retry: {e}"
            ) from e
        except SnippetExtractionError:
            raise
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Unexpected error, retrying: {e}")
                continue
            raise SnippetExtractionError(
                f"Extraction failed after retry: {e}"
            ) from e

    raise SnippetExtractionError("Exhausted all retries")


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
    Extract key snippets from an article.

    LLM extracts verbatim quotes proportionally distributed across the entire
    article. The number of snippets is determined by the LLM based on article
    content and length.

    Args:
        text: Full article text
        title: Article title
        author: Article author
        word_count: Article word count (for logging)
        source_url: Optional source URL for logging

    Returns:
        List of ExtractedSnippet objects

    Raises:
        SnippetExtractionError: If extraction fails after retries
    """
    if not text or not text.strip():
        logger.info("Empty text provided, returning no snippets")
        return []

    logger.info(
        f"Extracting snippets from '{title}' (words={word_count})"
    )

    snippets = _extract_snippets_llm(text, title, author)

    logger.info(
        f"Extraction complete: {len(snippets)} snippets from '{title}'"
        + (f" (url={source_url})" if source_url else "")
    )

    return snippets
