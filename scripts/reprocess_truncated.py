#!/usr/bin/env python3
"""
Reprocess Truncated Articles: Reset kx-processed articles for re-ingestion.

Articles processed before the 12KB truncation fix need to be re-processed
so their full text gets extracted. This script:

  1. Fetches all Reader documents tagged 'kx-processed'
  2. Deletes their auto_snippet_* chunks from Firestore kb_items
  3. Resets tags: kx-processed → kx-auto
     (nightly auto-snippets job then picks them up)

Usage:
    # Dry run (default) — shows what would be reset
    python scripts/reprocess_truncated.py

    # Actually reset (delete chunks + update tags)
    python scripts/reprocess_truncated.py --execute

    # Only reset articles with kx-overflow tag (skip already-full ones)
    python scripts/reprocess_truncated.py --execute --skip-overflow

    # Limit to N articles (useful for testing)
    python scripts/reprocess_truncated.py --execute --limit 5

Cost: Firestore deletes + Reader API calls only (no LLM costs here).
      LLM costs happen when nightly job re-processes.
"""

import argparse
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from google.cloud import firestore, secretmanager

from ingest.reader_client import ReadwiseReaderClient

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

    Queries kb_items where parent_doc_id == doc_id and source_type == auto-snippet.

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
        # Fallback: check the sentinel chunk directly
        sentinel = db.collection("kb_items").document(f"auto_snippet_{doc_id}_0").get()
        if sentinel.exists:
            docs = [sentinel]

    if execute:
        for doc in docs:
            doc.reference.delete()
        logger.info(f"  Deleted {len(docs)} chunks for {doc_id}")
    else:
        logger.info(f"  [dry-run] Would delete {len(docs)} chunks for {doc_id}")

    return len(docs)


def reset_tags(
    reader: ReadwiseReaderClient,
    doc_id: str,
    current_tags: List[str],
    execute: bool,
) -> bool:
    """
    Reset tags: remove kx-processed (and kx-overflow), add kx-auto.

    Returns:
        True if successful (or dry-run)
    """
    remove = [t for t in [PROCESSED_TAG, OVERFLOW_TAG] if t in current_tags]
    add = [INGEST_TAG]

    if not execute:
        logger.info(
            f"  [dry-run] Would remove {remove}, add {add} for {doc_id}"
        )
        return True

    try:
        reader.update_document_tags(
            document_id=doc_id,
            current_tags=current_tags,
            remove_tags=remove,
            add_tags=add,
        )
        logger.info(f"  Tags reset: -{remove} +{add} for {doc_id}")
        return True
    except Exception as e:
        logger.error(f"  Tag update failed for {doc_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Reprocess truncated kx-processed articles")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete chunks and reset tags (default: dry-run)",
    )
    parser.add_argument(
        "--skip-overflow",
        action="store_true",
        help="Skip articles already tagged kx-overflow (already processed with full text)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max articles to process (0 = all)",
    )
    args = parser.parse_args()

    if not args.execute:
        logger.info("DRY RUN — pass --execute to actually reset articles")

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

    # Optional: filter out already-overflow-tagged articles
    if args.skip_overflow:
        before = len(raw_docs)
        raw_docs = [
            d for d in raw_docs
            if OVERFLOW_TAG not in d.get("tags", [])
        ]
        logger.info(
            f"Skipping {before - len(raw_docs)} articles already tagged '{OVERFLOW_TAG}'"
        )

    # Apply limit
    if args.limit and args.limit < len(raw_docs):
        logger.info(f"Limiting to {args.limit} articles (--limit)")
        raw_docs = raw_docs[:args.limit]

    # Process each document
    reset_count = 0
    failed_count = 0
    total_chunks_deleted = 0

    for i, raw_doc in enumerate(raw_docs, 1):
        doc_id = raw_doc.get("id", "unknown")
        title = raw_doc.get("title", "Untitled")[:60]
        current_tags = raw_doc.get("tags", [])

        logger.info(f"[{i}/{len(raw_docs)}] '{title}' ({doc_id})")

        # Step 1: Delete existing chunks
        chunks_deleted = delete_chunks_for_doc(db, doc_id, execute=args.execute)
        total_chunks_deleted += chunks_deleted

        # Step 2: Reset tags
        ok = reset_tags(reader, doc_id, current_tags, execute=args.execute)
        if ok:
            reset_count += 1
        else:
            failed_count += 1

    # Summary
    mode = "Executed" if args.execute else "Dry-run"
    logger.info(
        f"\n{mode} complete: "
        f"{reset_count} articles reset, "
        f"{total_chunks_deleted} chunks deleted, "
        f"{failed_count} failures"
    )
    if not args.execute:
        logger.info("Run with --execute to apply changes.")
    else:
        logger.info(
            f"Done. {reset_count} articles tagged '{INGEST_TAG}' — "
            "nightly job will re-process them tonight."
        )


if __name__ == "__main__":
    main()
