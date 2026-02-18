#!/usr/bin/env python3
"""
Reprocess Truncated Articles: Re-run pipeline on kx-processed articles.

Articles processed before the 12KB truncation fix need to be re-processed
so their full text gets extracted. This script:

  1. Fetches all Reader documents tagged 'kx-processed'
  2. Deletes their auto_snippet_* chunks from Firestore kb_items
  3. Re-runs the full pipeline (extract → Readwise highlights → embed → match)
  4. Updates tags: keeps kx-processed (adds kx-overflow if truncated)

Usage:
    # Dry run (default) — shows what would be reprocessed
    python scripts/reprocess_truncated.py

    # Reprocess directly (deletes old chunks, runs pipeline)
    python scripts/reprocess_truncated.py --execute

    # Limit to N articles (useful for testing)
    python scripts/reprocess_truncated.py --execute --limit 3

    # Reset tags only (don't run pipeline, let nightly job handle it)
    python scripts/reprocess_truncated.py --execute --reset-only

Cost: LLM calls (Gemini Flash) + Readwise API + Firestore writes per article.
"""

import argparse
import logging
import os
import sys
import time
from typing import Any, Dict, List

# Add src and sub-packages to path
_src = os.path.join(os.path.dirname(__file__), "../src")
sys.path.insert(0, _src)
sys.path.insert(0, os.path.join(_src, "ingest"))
sys.path.insert(0, os.path.join(_src, "knowledge_cards"))
sys.path.insert(0, os.path.join(_src, "embed"))
sys.path.insert(0, os.path.join(_src, "mcp_server"))

from google.cloud import firestore, secretmanager

from ingest.reader_client import ReadwiseReaderClient
from ingest.readwise_writer import process_document
from knowledge_cards.snippet_extractor import OVERFLOW_THRESHOLD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT", "kx-hub")

PROCESSED_TAG = "kx-processed"
INGEST_TAG = "kx-auto"
OVERFLOW_TAG = "kx-overflow"


def get_api_key() -> str:
    """Get Readwise API key from env or Secret Manager."""
    key = os.environ.get("READWISE_API_KEY")
    if key:
        return key
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/readwise-api-key/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def delete_chunks_for_doc(
    db: firestore.Client,
    doc_id: str,
    execute: bool,
) -> int:
    """
    Delete all auto_snippet chunks for a Reader document from Firestore.

    Returns:
        Number of chunks deleted (or that would be deleted in dry-run)
    """
    query = (
        db.collection("kb_items")
        .where("parent_doc_id", "==", doc_id)
        .where("source_type", "==", "auto-snippet")
    )
    docs = list(query.stream())

    if not docs:
        sentinel = db.collection("kb_items").document(f"auto_snippet_{doc_id}_0").get()
        if sentinel.exists:
            docs = [sentinel]

    if execute:
        for doc in docs:
            doc.reference.delete()
        logger.info(f"  Deleted {len(docs)} chunks")
    else:
        logger.info(f"  [dry-run] Would delete {len(docs)} chunks")

    return len(docs)


def update_tags_after_reprocess(
    reader: ReadwiseReaderClient,
    doc_id: str,
    current_tags: List[str],
    is_overflow: bool,
) -> bool:
    """Add kx-overflow tag if article was truncated. Keep kx-processed."""
    if not is_overflow:
        return True  # nothing to change

    if OVERFLOW_TAG in current_tags:
        return True  # already tagged

    try:
        reader.update_document_tags(
            document_id=doc_id,
            current_tags=current_tags,
            remove_tags=[],
            add_tags=[OVERFLOW_TAG],
        )
        logger.info(f"  Tagged '{OVERFLOW_TAG}'")
        return True
    except Exception as e:
        logger.error(f"  Tag update failed: {e}")
        return False


def reset_tags(
    reader: ReadwiseReaderClient,
    doc_id: str,
    current_tags: List[str],
    execute: bool,
) -> bool:
    """Reset tags: remove kx-processed, add kx-auto (for nightly job pickup)."""
    remove = [t for t in [PROCESSED_TAG, OVERFLOW_TAG] if t in current_tags]
    add = [INGEST_TAG]

    if not execute:
        logger.info(f"  [dry-run] Would remove {remove}, add {add}")
        return True

    try:
        reader.update_document_tags(
            document_id=doc_id,
            current_tags=current_tags,
            remove_tags=remove,
            add_tags=add,
        )
        logger.info(f"  Tags reset: -{remove} +{add}")
        return True
    except Exception as e:
        logger.error(f"  Tag update failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Reprocess truncated kx-processed articles"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually reprocess (default: dry-run)",
    )
    parser.add_argument(
        "--reset-only",
        action="store_true",
        help="Only reset tags to kx-auto (let nightly job handle reprocessing)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max articles to process (0 = all)",
    )
    args = parser.parse_args()

    if not args.execute:
        logger.info("DRY RUN — pass --execute to actually reprocess")

    # Init clients
    api_key = get_api_key()
    reader = ReadwiseReaderClient(api_key)
    db = firestore.Client(project=PROJECT_ID)

    # Fetch all kx-processed documents
    logger.info(f"Fetching documents tagged '{PROCESSED_TAG}'...")
    raw_docs = reader.fetch_tagged_documents(tag=PROCESSED_TAG, category="")
    logger.info(f"Found {len(raw_docs)} documents tagged '{PROCESSED_TAG}'")

    if not raw_docs:
        logger.info("Nothing to reprocess.")
        return

    if args.limit and args.limit < len(raw_docs):
        logger.info(f"Limiting to {args.limit} articles (--limit)")
        raw_docs = raw_docs[: args.limit]

    # Process each document
    success_count = 0
    failed_count = 0
    skipped_count = 0
    total_chunks_deleted = 0
    total_snippets = 0
    start_time = time.time()

    for i, raw_doc in enumerate(raw_docs, 1):
        doc_id = raw_doc.get("id", "unknown")
        title = raw_doc.get("title", "Untitled")[:60]
        current_tags = raw_doc.get("tags", [])

        logger.info(f"[{i}/{len(raw_docs)}] '{title}' ({doc_id})")

        # Step 1: Delete existing chunks
        chunks_deleted = delete_chunks_for_doc(db, doc_id, execute=args.execute)
        total_chunks_deleted += chunks_deleted

        # Step 2a: Reset-only mode — just flip tags and let nightly handle it
        if args.reset_only:
            reset_tags(reader, doc_id, current_tags, execute=args.execute)
            success_count += 1
            continue

        # Step 2b: Direct mode — run the full pipeline now
        if not args.execute:
            logger.info("  [dry-run] Would run pipeline")
            success_count += 1
            continue

        try:
            reader_doc = reader.extract_document_content(raw_doc)
            is_overflow = len(reader_doc.clean_text) > OVERFLOW_THRESHOLD

            if is_overflow:
                logger.warning(
                    f"  Overflow: {len(reader_doc.clean_text):,} chars "
                    f"(>{OVERFLOW_THRESHOLD:,})"
                )

            result = process_document(
                reader_doc,
                api_key=api_key,
                write_to_readwise=True,
            )

            snippets = result.get("snippets_extracted", 0)
            embedded = result.get("chunks_embedded", 0)
            total_snippets += snippets

            logger.info(
                f"  Pipeline: {snippets} snippets, {embedded} embedded, "
                f"{result.get('problem_matches', 0)} problem matches"
            )

            # Tag overflow if needed
            update_tags_after_reprocess(reader, doc_id, current_tags, is_overflow)
            success_count += 1

        except Exception as e:
            logger.error(f"  Pipeline failed: {e}")
            failed_count += 1

    # Summary
    elapsed = time.time() - start_time
    mode = "Executed" if args.execute else "Dry-run"
    action = "reset" if args.reset_only else "reprocessed"
    logger.info(
        f"\n{mode} complete ({elapsed:.1f}s): "
        f"{success_count} {action}, "
        f"{failed_count} failed, "
        f"{total_chunks_deleted} old chunks deleted, "
        f"{total_snippets} new snippets"
    )
    if not args.execute:
        logger.info("Run with --execute to apply changes.")


if __name__ == "__main__":
    main()
