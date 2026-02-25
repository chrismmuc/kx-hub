"""
Readwise v2 Highlight Writer & Direct Snippet Embedding.

Story 13.3: Write Back to Readwise & Pipeline Integration

This module:
1. Writes extracted snippets back to Readwise v2 as highlights
2. Embeds snippets directly to Firestore kb_items (bypassing GCS pipeline)
3. Orchestrates the full document processing pipeline

Usage:
    from src.ingest.readwise_writer import process_document
    from src.ingest.reader_client import ReaderDocument

    result = process_document(doc, api_key="...", write_to_readwise=True)
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

try:
    from src.knowledge_cards.snippet_extractor import ExtractedSnippet, extract_snippets
except ImportError:
    try:
        from knowledge_cards.snippet_extractor import ExtractedSnippet, extract_snippets
    except ImportError:
        from snippet_extractor import ExtractedSnippet, extract_snippets

try:
    from src.embed.main import (
        generate_embedding,
        write_to_firestore,
        _generate_source_id,
        _ensure_source_exists,
    )
except ImportError:
    try:
        from embed.main import (
            generate_embedding,
            write_to_firestore,
            _generate_source_id,
            _ensure_source_exists,
        )
    except ImportError:
        from embed_main import (
            generate_embedding,
            write_to_firestore,
            _generate_source_id,
            _ensure_source_exists,
        )

try:
    from src.embed.problem_matcher import match_chunks_to_problems
except ImportError:
    try:
        from embed.problem_matcher import match_chunks_to_problems
    except ImportError:
        from problem_matcher import match_chunks_to_problems

try:
    from src.knowledge_cards.generator import generate_knowledge_card
except ImportError:
    try:
        from knowledge_cards.generator import generate_knowledge_card
    except ImportError:
        from generator import generate_knowledge_card

try:
    from src.ingest.reader_client import ReaderDocument
except ImportError:
    from reader_client import ReaderDocument

logger = logging.getLogger(__name__)


# ============================================================================
# Readwise v2 Highlight Writer
# ============================================================================


class ReadwiseHighlightWriter:
    """Write highlights to Readwise v2 API."""

    BASE_URL = "https://readwise.io/api/v2"
    BATCH_SIZE = 100  # Readwise v2 max per request
    MAX_RETRIES = 3

    def __init__(self, api_key: str):
        """
        Initialize highlight writer.

        Args:
            api_key: Readwise API token
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
            }
        )

    def create_highlights(
        self,
        snippets: List[ExtractedSnippet],
        title: str,
        author: str,
        source_url: str,
    ) -> Dict[str, Any]:
        """
        Create highlights in Readwise v2 from extracted snippets.

        Args:
            snippets: List of extracted snippets
            title: Article title
            author: Article author
            source_url: Original article URL

        Returns:
            Dict with created count, failed count, and highlight IDs
        """
        if not snippets:
            return {"created": 0, "failed": 0, "highlight_ids": []}

        now = datetime.now(timezone.utc).isoformat()

        # Build highlights payload
        highlights = []
        for snippet in snippets:
            highlight = {
                "text": snippet.text,
                "title": title,
                "author": author,
                "source_url": source_url,
                "highlighted_at": now,
                "source_type": "article",
            }
            if snippet.context:
                highlight["note"] = snippet.context
            highlights.append(highlight)

        # Batch up to BATCH_SIZE per request
        total_created = 0
        total_failed = 0
        all_highlight_ids = []

        for batch_start in range(0, len(highlights), self.BATCH_SIZE):
            batch = highlights[batch_start : batch_start + self.BATCH_SIZE]
            payload = {"highlights": batch}

            try:
                response_data = self._post_highlights(payload)
                # Readwise v2 returns created highlights
                created_highlights = response_data if isinstance(response_data, list) else []
                total_created += len(batch)
                for h in created_highlights:
                    if isinstance(h, dict) and "id" in h:
                        all_highlight_ids.append(h["id"])
            except Exception as e:
                logger.error(f"Failed to create highlight batch: {e}")
                total_failed += len(batch)

        logger.info(
            f"Readwise highlights: {total_created} created, "
            f"{total_failed} failed for '{title}'"
        )

        return {
            "created": total_created,
            "failed": total_failed,
            "highlight_ids": all_highlight_ids,
        }

    def _post_highlights(self, payload: Dict[str, Any]) -> Any:
        """
        POST highlights to Readwise v2 API with retry logic.

        Args:
            payload: Request payload with highlights array

        Returns:
            Parsed JSON response

        Raises:
            requests.HTTPError: After max retries
        """
        url = f"{self.BASE_URL}/highlights/"

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.post(url, json=payload, timeout=30)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(
                        f"Rate limited. Retrying after {retry_after}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(retry_after)
                        continue
                    response.raise_for_status()

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                logger.error(
                    f"Request timeout (attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
                if attempt == self.MAX_RETRIES - 1:
                    raise
                time.sleep(2**attempt)

            except requests.exceptions.RequestException as e:
                if isinstance(e, requests.exceptions.HTTPError):
                    raise
                logger.error(
                    f"Request failed: {e} (attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
                if attempt == self.MAX_RETRIES - 1:
                    raise
                time.sleep(2**attempt)

        raise Exception("Max retries exceeded")


# ============================================================================
# Direct Snippet Embedding
# ============================================================================


def embed_snippets(
    snippets: List[ExtractedSnippet],
    title: str,
    author: str,
    source_url: str,
    reader_doc_id: str,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Embed extracted snippets directly to Firestore kb_items.

    Bypasses the GCS → pipeline_items → embed pipeline for simplicity.
    Each snippet gets its own embedding and kb_item document.

    Args:
        snippets: List of extracted snippets
        title: Article title
        author: Article author
        source_url: Original article URL
        reader_doc_id: Reader document ID (for chunk_id generation)
        tags: Optional list of tags

    Returns:
        Dict with embedded count, chunk_ids, and source_id
    """
    if not snippets:
        return {"embedded": 0, "chunk_ids": [], "source_id": None}

    all_tags = list(tags or [])
    if "auto-snippet" not in all_tags:
        all_tags.append("auto-snippet")

    source_id = _generate_source_id(title)
    chunk_ids = []
    embedded_count = 0

    for i, snippet in enumerate(snippets):
        chunk_id = f"auto_snippet_{reader_doc_id}_{i}"

        # Build content in markdown format
        content = f"> {snippet.text}\n\n**Context:** {snippet.context}"

        # Build metadata matching write_to_firestore() expectations
        metadata = {
            "id": chunk_id,
            "chunk_id": chunk_id,
            "parent_doc_id": reader_doc_id,
            "chunk_index": i,
            "total_chunks": len(snippets),
            "title": title,
            "author": author,
            "source": "reader",
            "category": "article",
            "tags": all_tags,
            "source_url": source_url,
            "source_type": "auto-snippet",
        }

        try:
            # Generate embedding from title + content
            text_to_embed = f"{title}\n{content}"
            embedding_vector = generate_embedding(text_to_embed)

            # Compute content hash
            content_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"

            # Write to Firestore kb_items
            success = write_to_firestore(
                metadata=metadata,
                content=content,
                content_hash=content_hash,
                run_id=f"auto_ingest_{reader_doc_id}",
                embedding_status="complete",
                embedding_vector=embedding_vector,
            )

            if success:
                chunk_ids.append(chunk_id)
                embedded_count += 1
            else:
                logger.error(f"Failed to write chunk {chunk_id} to Firestore")

        except Exception as e:
            logger.error(f"Failed to embed snippet {i} for '{title}': {e}")
            # Continue with remaining snippets

    logger.info(
        f"Embedded {embedded_count}/{len(snippets)} snippets "
        f"for '{title}' (source_id={source_id})"
    )

    return {
        "embedded": embedded_count,
        "chunk_ids": chunk_ids,
        "source_id": source_id,
    }


# ============================================================================
# Full Pipeline Orchestration
# ============================================================================


def process_document(
    reader_doc: ReaderDocument,
    api_key: str,
    write_to_readwise: bool = True,
) -> Dict[str, Any]:
    """
    Process a Reader document: extract → write to Readwise → embed → match problems.

    Graceful degradation: if one step fails, remaining steps still execute.

    Args:
        reader_doc: ReaderDocument from Story 13.1
        api_key: Readwise API key
        write_to_readwise: Whether to write highlights to Readwise (False for dry-run)

    Returns:
        Dict with stats from each processing step
    """
    result = {
        "snippets_extracted": 0,
        "highlights_created": 0,
        "highlights_failed": 0,
        "chunks_embedded": 0,
        "knowledge_cards_generated": 0,
        "problem_matches": 0,
    }

    # Step 1: Extract snippets
    try:
        snippets = extract_snippets(
            text=reader_doc.clean_text,
            title=reader_doc.title,
            author=reader_doc.author or "Unknown",
            word_count=reader_doc.word_count,
            source_url=reader_doc.source_url,
        )
        result["snippets_extracted"] = len(snippets)
    except Exception as e:
        logger.error(f"Snippet extraction failed for '{reader_doc.title}': {e}")
        return result

    if not snippets:
        logger.info(f"No snippets extracted for '{reader_doc.title}'")
        return result

    # Step 2: Write to Readwise (optional)
    if write_to_readwise and reader_doc.source_url:
        try:
            writer = ReadwiseHighlightWriter(api_key)
            highlight_result = writer.create_highlights(
                snippets=snippets,
                title=reader_doc.title,
                author=reader_doc.author or "Unknown",
                source_url=reader_doc.source_url,
            )
            result["highlights_created"] = highlight_result["created"]
            result["highlights_failed"] = highlight_result["failed"]
        except Exception as e:
            logger.error(f"Readwise write failed for '{reader_doc.title}': {e}")
            # Continue with embedding

    # Step 3: Embed to Firestore
    try:
        embed_result = embed_snippets(
            snippets=snippets,
            title=reader_doc.title,
            author=reader_doc.author or "Unknown",
            source_url=reader_doc.source_url or "",
            reader_doc_id=reader_doc.id or "unknown",
            tags=reader_doc.tags if isinstance(reader_doc.tags, list) else [],
        )
        result["chunks_embedded"] = embed_result["embedded"]
        chunk_ids = embed_result["chunk_ids"]
    except Exception as e:
        logger.error(f"Embedding failed for '{reader_doc.title}': {e}")
        chunk_ids = []

    # Step 4: Generate knowledge cards
    if chunk_ids:
        from google.cloud import firestore as _firestore

        _db = _firestore.Client()
        cards_generated = 0
        for i, snippet in enumerate(snippets):
            chunk_id = chunk_ids[i] if i < len(chunk_ids) else None
            if not chunk_id:
                continue
            try:
                card = generate_knowledge_card(
                    chunk_id=chunk_id,
                    title=reader_doc.title,
                    author=reader_doc.author or "Unknown",
                    content=snippet.text,
                )
                _db.collection("kb_items").document(chunk_id).set(
                    {"knowledge_card": card.to_dict()}, merge=True
                )
                cards_generated += 1
            except Exception as e:
                logger.warning(f"Knowledge card failed for {chunk_id}: {e}")
        result["knowledge_cards_generated"] = cards_generated
        logger.info(
            f"Generated {cards_generated}/{len(chunk_ids)} knowledge cards "
            f"for '{reader_doc.title}'"
        )

    # Step 5: Problem matching
    if chunk_ids:
        try:
            match_result = match_chunks_to_problems(chunk_ids)
            result["problem_matches"] = match_result.get("matches_found", 0)
        except Exception as e:
            logger.error(f"Problem matching failed for '{reader_doc.title}': {e}")

    logger.info(
        f"Processed '{reader_doc.title}': "
        f"{result['snippets_extracted']} snippets, "
        f"{result['highlights_created']} highlights, "
        f"{result['chunks_embedded']} embedded, "
        f"{result['knowledge_cards_generated']} cards, "
        f"{result['problem_matches']} problem matches"
    )

    return result
