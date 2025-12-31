"""
Knowledge Card Generator

Batch processes chunks to generate AI-powered knowledge cards.
Supports multiple LLM providers (Gemini, Claude) via abstraction layer.
Story 2.1: Knowledge Card Generation (Epic 2)
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add parent directory to path for llm module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .prompt_manager import PromptManager, estimate_cost
from .schema import KnowledgeCard, validate_knowledge_card_response

# LLM abstraction layer
try:
    from llm import BaseLLMClient, get_client
    from llm import GenerationConfig as LLMGenerationConfig

    _HAS_LLM = True
except ImportError:
    _HAS_LLM = False
    BaseLLMClient = None

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration (from environment or defaults)
DEFAULT_BATCH_SIZE = 100  # Process 100 chunks at a time (Firestore batch limit)

# Global LLM client instance (lazy initialization)
_llm_client: Optional[BaseLLMClient] = None


def get_llm_client() -> BaseLLMClient:
    """
    Get or create LLM client instance (cached).

    Model selection via environment variables:
        LLM_MODEL: Model name (e.g., "gemini-2.5-flash", "claude-haiku")
        LLM_PROVIDER: Provider preference ("gemini" or "claude")

    Returns:
        Initialized LLM client

    Raises:
        ImportError: If LLM libraries not available
    """
    global _llm_client

    if not _HAS_LLM:
        raise ImportError(
            "LLM abstraction layer not available. Ensure src/llm package is installed."
        )

    if _llm_client is None:
        _llm_client = get_client()  # Uses LLM_MODEL env var or default
        logger.info(f"Initialized LLM client: {_llm_client}")

    return _llm_client


def set_llm_client(client: BaseLLMClient) -> None:
    """
    Set a custom LLM client (useful for testing or explicit model selection).

    Args:
        client: Pre-configured LLM client
    """
    global _llm_client
    _llm_client = client
    logger.info(f"LLM client set to: {client}")


def generate_knowledge_card(
    chunk_id: str,
    title: str,
    author: str,
    content: str,
    prompt_manager: Optional[PromptManager] = None,
) -> KnowledgeCard:
    """
    Generate knowledge card for a single chunk using configured LLM.

    Uses the LLM abstraction layer which handles:
    - Model selection (via LLM_MODEL env var)
    - Retry logic with exponential backoff
    - Provider-specific configuration

    Args:
        chunk_id: Chunk document ID (for logging)
        title: Chunk title
        author: Chunk author
        content: Full chunk content (text)
        prompt_manager: Optional PromptManager instance (creates default if None)

    Returns:
        Validated KnowledgeCard instance

    Raises:
        Exception: After max retries for rate limiting or server errors
    """
    if prompt_manager is None:
        prompt_manager = PromptManager()

    # Format prompt with chunk data
    prompt = prompt_manager.format_prompt(title, author, content)

    # Get LLM client (model selected via env var or default)
    client = get_llm_client()

    # Generation config for JSON output (thinking disabled for cost efficiency)
    config = LLMGenerationConfig(
        temperature=0.7,  # Balanced creativity for summarization
        top_p=0.95,
        top_k=40,
        max_output_tokens=2048,  # Ensure complete output
        enable_thinking=False,  # Disabled to avoid $3.50/1M token costs
    )

    logger.debug(
        f"Generating knowledge card for chunk {chunk_id} using {client.model_id}"
    )

    try:
        # Use generate_json for automatic JSON parsing and markdown stripping
        response_data = client.generate_json(prompt, config)

        # Validate and create KnowledgeCard
        knowledge_card = validate_knowledge_card_response(response_data)

        logger.info(
            f"Generated knowledge card for chunk {chunk_id}: "
            f"{len(knowledge_card.summary)} chars, {len(knowledge_card.takeaways)} takeaways "
            f"[model={client.model_id}]"
        )

        return knowledge_card

    except ValueError as e:
        # JSON parsing error - log and re-raise
        logger.error(f"Failed to parse JSON response for chunk {chunk_id}: {e}")
        raise

    except Exception as e:
        logger.error(f"Failed to generate knowledge card for chunk {chunk_id}: {e}")
        raise


def process_chunks_batch(
    chunks: List[Dict[str, Any]], batch_size: int = DEFAULT_BATCH_SIZE
) -> Dict[str, Any]:
    """
    Process chunks in batches to generate knowledge cards.

    Args:
        chunks: List of chunk dictionaries from Firestore (must have: chunk_id, title, author, content)
        batch_size: Number of chunks to process per batch (default: 100)

    Returns:
        Dictionary with processing results:
        - processed: Number of chunks successfully processed
        - failed: Number of chunks that failed
        - cards: List of (chunk_id, KnowledgeCard) tuples
        - errors: List of (chunk_id, error_message) tuples
        - duration: Total processing time in seconds
        - cost_estimate: Estimated cost for this batch

    Example:
        >>> chunks = [...]  # From Firestore query
        >>> results = process_chunks_batch(chunks, batch_size=100)
        >>> print(f"Processed {results['processed']}/{len(chunks)} chunks in {results['duration']}s")
    """
    start_time = time.time()

    processed = 0
    failed = 0
    cards = []
    errors = []

    prompt_manager = PromptManager()

    total_chunks = len(chunks)
    logger.info(
        f"Starting batch processing: {total_chunks} chunks with batch_size={batch_size}"
    )

    # Estimate cost upfront
    cost_estimate = estimate_cost(total_chunks)
    logger.info(
        f"Estimated cost: ${cost_estimate['total_cost']:.4f} for {total_chunks} chunks"
    )

    for i, chunk in enumerate(chunks):
        chunk_id = chunk.get("chunk_id") or chunk.get("id")
        title = chunk.get("title", "Untitled")
        author = chunk.get("author", "Unknown")
        content = chunk.get("content", "")

        if not content:
            logger.warning(f"Skipping chunk {chunk_id}: no content")
            failed += 1
            errors.append((chunk_id, "No content available"))
            continue

        try:
            # Generate knowledge card
            knowledge_card = generate_knowledge_card(
                chunk_id=chunk_id,
                title=title,
                author=author,
                content=content,
                prompt_manager=prompt_manager,
            )

            cards.append((chunk_id, knowledge_card))
            processed += 1

            # Log progress every 10 chunks
            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                chunks_per_sec = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (
                    (total_chunks - (i + 1)) / chunks_per_sec
                    if chunks_per_sec > 0
                    else 0
                )

                logger.info(
                    f"Progress: {i + 1}/{total_chunks} chunks ({processed} succeeded, {failed} failed) | "
                    f"{chunks_per_sec:.1f} chunks/sec | ETA: {eta:.0f}s"
                )

        except Exception as e:
            logger.error(f"Failed to generate card for chunk {chunk_id}: {e}")
            failed += 1
            errors.append((chunk_id, str(e)))

    duration = time.time() - start_time

    results = {
        "processed": processed,
        "failed": failed,
        "cards": cards,
        "errors": errors,
        "duration": duration,
        "cost_estimate": cost_estimate,
        "chunks_per_second": processed / duration if duration > 0 else 0,
    }

    logger.info(
        f"Batch processing complete: {processed}/{total_chunks} succeeded, {failed} failed | "
        f"Duration: {duration:.1f}s | Cost estimate: ${cost_estimate['total_cost']:.4f}"
    )

    return results
