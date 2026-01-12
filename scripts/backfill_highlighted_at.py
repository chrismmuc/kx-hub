#!/usr/bin/env python3
"""
Backfill script to populate last_highlighted_at and first_highlighted_at fields
for existing chunks that are missing these values.

This script:
1. Queries Firestore for chunks missing last_highlighted_at
2. Groups chunks by parent document ID
3. Fetches raw JSON from GCS to get highlight dates
4. Updates chunks with the correct highlighted_at values

Usage:
    # Dry run (default) - shows what would be updated
    python scripts/backfill_highlighted_at.py

    # Actually perform the updates
    python scripts/backfill_highlighted_at.py --execute

    # Limit to specific number of documents
    python scripts/backfill_highlighted_at.py --limit 10 --execute
"""

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from google.cloud import firestore, storage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = "kx-hub"
FIRESTORE_COLLECTION = "kb_items"
RAW_JSON_BUCKET = f"{PROJECT_ID}-raw-json"


def get_firestore_client():
    """Get Firestore client."""
    return firestore.Client(project=PROJECT_ID, database="(default)")


def get_storage_client():
    """Get GCS client."""
    return storage.Client(project=PROJECT_ID)


def get_chunks_missing_highlighted_at(limit: Optional[int] = None) -> List[Dict]:
    """
    Get all chunks that are missing last_highlighted_at field.

    Args:
        limit: Optional limit on number of chunks to fetch

    Returns:
        List of chunk documents
    """
    db = get_firestore_client()
    collection = db.collection(FIRESTORE_COLLECTION)

    # Query for chunks (have chunk_id field) that are missing last_highlighted_at
    # Firestore doesn't support querying for missing fields, so we fetch and filter
    query = collection.order_by("created_at", direction=firestore.Query.DESCENDING)

    if limit:
        # Fetch more to account for filtering
        query = query.limit(limit * 5)

    chunks = []
    for doc in query.stream():
        data = doc.to_dict()
        # Only process chunks (not legacy documents)
        if "chunk_id" not in data and "doc_id" not in data:
            continue
        # Check if missing last_highlighted_at
        if data.get("last_highlighted_at") is None:
            data["_doc_id"] = doc.id
            chunks.append(data)
            if limit and len(chunks) >= limit:
                break

    return chunks


def group_chunks_by_parent(chunks: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Group chunks by their parent document ID.

    Args:
        chunks: List of chunk documents

    Returns:
        Dictionary mapping doc_id to list of chunks
    """
    grouped = defaultdict(list)
    for chunk in chunks:
        # Get parent doc ID from chunk
        doc_id = chunk.get("doc_id")
        if not doc_id:
            # Try to extract from chunk_id (format: {doc_id}-chunk-{index})
            chunk_id = chunk.get("chunk_id") or chunk.get("_doc_id")
            if chunk_id and "-chunk-" in chunk_id:
                doc_id = chunk_id.rsplit("-chunk-", 1)[0]

        if doc_id:
            grouped[doc_id].append(chunk)
        else:
            logger.warning(f"Could not determine parent doc_id for chunk: {chunk.get('_doc_id')}")

    return dict(grouped)


def fetch_raw_json(doc_id: str) -> Optional[Dict]:
    """
    Fetch raw JSON from GCS for a document.

    Args:
        doc_id: Document ID (user_book_id from Readwise)

    Returns:
        Raw JSON data or None if not found
    """
    storage_client = get_storage_client()
    bucket = storage_client.bucket(RAW_JSON_BUCKET)

    # Try different filename patterns
    patterns = [
        f"readwise-book-{doc_id}.json",
        f"{doc_id}.json",
    ]

    for pattern in patterns:
        blob = bucket.blob(pattern)
        if blob.exists():
            content = blob.download_as_text()
            return json.loads(content)

    logger.warning(f"Raw JSON not found for doc_id: {doc_id}")
    return None


def extract_highlighted_dates(raw_data: Dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract first and last highlighted_at dates from raw Readwise data.

    Args:
        raw_data: Raw JSON data from Readwise

    Returns:
        Tuple of (first_highlighted_at, last_highlighted_at) as ISO strings
    """
    highlights = raw_data.get("highlights", [])

    if not highlights:
        return None, None

    # Extract all highlighted_at dates
    dates = [
        h.get("highlighted_at")
        for h in highlights
        if h.get("highlighted_at")
    ]

    if not dates:
        return None, None

    sorted_dates = sorted(dates)
    return sorted_dates[0], sorted_dates[-1]


def parse_iso_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string to datetime object."""
    if not date_str:
        return None
    try:
        # Handle various ISO formats
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def update_chunks(
    doc_id: str,
    chunks: List[Dict],
    first_highlighted_at: Optional[str],
    last_highlighted_at: Optional[str],
    dry_run: bool = True
) -> int:
    """
    Update chunks with highlighted_at values.

    Args:
        doc_id: Parent document ID
        chunks: List of chunks to update
        first_highlighted_at: First highlight date (ISO string)
        last_highlighted_at: Last highlight date (ISO string)
        dry_run: If True, don't actually update

    Returns:
        Number of chunks updated
    """
    if not first_highlighted_at or not last_highlighted_at:
        logger.info(f"  Skipping {doc_id}: no highlight dates found")
        return 0

    # Parse dates to datetime objects
    first_dt = parse_iso_datetime(first_highlighted_at)
    last_dt = parse_iso_datetime(last_highlighted_at)

    if not first_dt or not last_dt:
        logger.warning(f"  Could not parse dates for {doc_id}")
        return 0

    db = get_firestore_client()
    collection = db.collection(FIRESTORE_COLLECTION)

    updated = 0
    for chunk in chunks:
        chunk_doc_id = chunk.get("_doc_id")
        if not chunk_doc_id:
            continue

        if dry_run:
            logger.info(f"  [DRY RUN] Would update {chunk_doc_id}: last_highlighted_at={last_dt}")
        else:
            doc_ref = collection.document(chunk_doc_id)
            doc_ref.update({
                "first_highlighted_at": first_dt,
                "last_highlighted_at": last_dt,
            })
            logger.info(f"  Updated {chunk_doc_id}")

        updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(description="Backfill highlighted_at fields for chunks")
    parser.add_argument("--execute", action="store_true", help="Actually perform updates (default: dry run)")
    parser.add_argument("--limit", type=int, help="Limit number of chunks to process")
    args = parser.parse_args()

    dry_run = not args.execute

    if dry_run:
        logger.info("=== DRY RUN MODE (use --execute to actually update) ===")
    else:
        logger.info("=== EXECUTING UPDATES ===")

    # Step 1: Get chunks missing highlighted_at
    logger.info("Fetching chunks missing last_highlighted_at...")
    chunks = get_chunks_missing_highlighted_at(limit=args.limit)
    logger.info(f"Found {len(chunks)} chunks to process")

    if not chunks:
        logger.info("No chunks need updating!")
        return

    # Step 2: Group by parent document
    grouped = group_chunks_by_parent(chunks)
    logger.info(f"Grouped into {len(grouped)} parent documents")

    # Step 3: Process each parent document
    total_updated = 0
    total_skipped = 0

    for doc_id, doc_chunks in grouped.items():
        logger.info(f"Processing doc_id {doc_id} ({len(doc_chunks)} chunks)...")

        # Fetch raw JSON
        raw_data = fetch_raw_json(doc_id)
        if not raw_data:
            total_skipped += len(doc_chunks)
            continue

        # Extract dates
        first_hl, last_hl = extract_highlighted_dates(raw_data)

        # Update chunks
        updated = update_chunks(doc_id, doc_chunks, first_hl, last_hl, dry_run=dry_run)
        total_updated += updated

    # Summary
    logger.info("=" * 50)
    logger.info(f"Total chunks processed: {len(chunks)}")
    logger.info(f"Total chunks {'would be ' if dry_run else ''}updated: {total_updated}")
    logger.info(f"Total chunks skipped (no raw data): {total_skipped}")

    if dry_run:
        logger.info("\nRun with --execute to actually perform updates")


if __name__ == "__main__":
    main()
