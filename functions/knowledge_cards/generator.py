"""
Knowledge Card Generator

Batch processes chunks to generate AI-powered knowledge cards using Gemini 2.5 Flash.
Story 2.1: Knowledge Card Generation (Epic 2)

Uses kx-llm package for LLM abstraction (thinking disabled by default for cost efficiency).
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from kx_llm import GenerationConfig, get_client
from prompt_manager import PromptManager, estimate_cost
from schema import KnowledgeCard, validate_knowledge_card_response

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 100  # Process 100 chunks at a time (Firestore batch limit)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 30.0  # seconds

# Global LLM client (lazy initialization)
_llm_client = None


def get_llm_client():
    """Get or create LLM client instance (cached)."""
    global _llm_client
    if _llm_client is None:
        # Uses LLM_MODEL env var or defaults to gemini-2.5-flash
        _llm_client = get_client()
        logger.info(f"Initialized LLM client: {_llm_client}")
    return _llm_client


def generate_knowledge_card(
    chunk_id: str,
    title: str,
    author: str,
    content: str,
    prompt_manager: Optional[PromptManager] = None,
) -> KnowledgeCard:
    """
    Generate knowledge card for a single chunk using LLM.

    Implements retry logic with exponential backoff for rate limiting.

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

    # Get LLM client
    client = get_llm_client()

    # Generation config - thinking disabled for cost efficiency
    config = GenerationConfig(
        temperature=0.7,  # Balanced creativity for summarization
        top_p=0.95,
        top_k=40,
        max_output_tokens=2048,
        enable_thinking=False,  # Disabled to avoid $3.50/1M token costs
    )

    backoff = INITIAL_BACKOFF

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(
                f"Generating knowledge card for chunk {chunk_id} (attempt {attempt + 1}/{MAX_RETRIES})"
            )

            # Use generate_json for automatic JSON parsing
            response_data = client.generate_json(prompt, config=config)

            if response_data is None:
                raise ValueError(f"Empty response from LLM API for chunk {chunk_id}")

            # Validate and create KnowledgeCard
            knowledge_card = validate_knowledge_card_response(response_data)

            logger.info(
                f"Generated knowledge card for chunk {chunk_id}: {len(knowledge_card.summary)} chars, {len(knowledge_card.takeaways)} takeaways"
            )

            return knowledge_card

        except Exception as e:
            error_msg = str(e).lower()

            # Check if rate limit or server error (retriable)
            is_rate_limit = (
                "rate" in error_msg or "quota" in error_msg or "429" in error_msg
            )
            is_server_error = (
                "internal" in error_msg or "500" in error_msg or "503" in error_msg
            )

            if (is_rate_limit or is_server_error) and attempt < MAX_RETRIES - 1:
                logger.warning(
                    f"Retriable error for chunk {chunk_id} (attempt {attempt + 1}/{MAX_RETRIES}): {e}. "
                    f"Retrying after {backoff}s"
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
            else:
                logger.error(
                    f"Failed to generate knowledge card for chunk {chunk_id} after {attempt + 1} attempts: {e}"
                )
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
        - cards: List of dicts with {chunk_id, knowledge_card}
        - errors: List of dicts with {chunk_id, error}
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

            cards.append(
                {"chunk_id": chunk_id, "knowledge_card": knowledge_card.to_dict()}
            )
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
            errors.append({"chunk_id": chunk_id, "error": str(e)})

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
