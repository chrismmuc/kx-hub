#!/usr/bin/env python3
"""
Migration Script: Extract Sources from Chunks

Story 4.1: Source Extraction & Migration
- Creates sources/ collection from unique chunk titles
- Adds source_id field to each chunk
- Generates URL-safe source IDs

Usage:
    python scripts/migrate_to_sources.py --dry-run
    python scripts/migrate_to_sources.py
"""

import argparse
import hashlib
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from google.cloud import firestore

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

GCP_PROJECT = "kx-hub"
CHUNKS_COLLECTION = "kb_items"
SOURCES_COLLECTION = "sources"


def get_firestore_client() -> firestore.Client:
    return firestore.Client(project=GCP_PROJECT)


def generate_source_id(title: str) -> str:
    """
    Generate a URL-safe source ID from title.

    Examples:
        "Building a Second Brain" -> "building-a-second-brain"
        "The First 90 Days" -> "the-first-90-days"
    """
    # Lowercase
    slug = title.lower()

    # Replace special chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)

    # Remove leading/trailing hyphens
    slug = slug.strip("-")

    # Truncate to reasonable length
    if len(slug) > 60:
        slug = slug[:60].rsplit("-", 1)[0]

    # Add short hash for uniqueness if needed
    if len(slug) < 5:
        hash_suffix = hashlib.md5(title.encode()).hexdigest()[:6]
        slug = f"{slug}-{hash_suffix}"

    return slug


def extract_sources(chunks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Extract unique sources from chunks.

    Returns:
        Dictionary mapping source_id -> source data
    """
    sources = defaultdict(
        lambda: {
            "title": None,
            "author": None,
            "chunk_ids": [],
            "chunk_count": 0,
        }
    )

    for chunk in chunks:
        title = chunk.get("title") or "Unknown"
        author = chunk.get("author") or "Unknown"
        chunk_id = chunk["id"]

        source_id = generate_source_id(title)

        if sources[source_id]["title"] is None:
            sources[source_id]["title"] = title
            sources[source_id]["author"] = author

        sources[source_id]["chunk_ids"].append(chunk_id)
        sources[source_id]["chunk_count"] += 1

    return dict(sources)


def determine_source_type(title: str, author: str) -> str:
    """
    Guess source type based on title/author patterns.
    """
    title_lower = title.lower()
    author_lower = (author or "").lower()

    if "magazine" in author_lower or "ix " in title_lower:
        return "magazine"
    elif "podcast" in title_lower:
        return "podcast"
    elif any(x in title_lower for x in ["article", "blog", "post"]):
        return "article"
    else:
        return "book"  # Default


def run_migration(dry_run: bool = True) -> Dict[str, Any]:
    """
    Run the source extraction migration.

    Args:
        dry_run: If True, don't write to Firestore

    Returns:
        Migration statistics
    """
    db = get_firestore_client()

    logger.info("=" * 60)
    logger.info("Source Extraction Migration")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)

    # Load all chunks
    logger.info("Loading chunks...")
    chunks_ref = db.collection(CHUNKS_COLLECTION)
    chunks = []
    for doc in chunks_ref.stream():
        chunk_data = doc.to_dict()
        chunk_data["id"] = doc.id
        chunks.append(chunk_data)

    logger.info(f"Loaded {len(chunks)} chunks")

    # Extract sources
    logger.info("Extracting sources...")
    sources = extract_sources(chunks)
    logger.info(f"Found {len(sources)} unique sources")

    # Add metadata
    now = datetime.now(timezone.utc)
    for source_id, data in sources.items():
        data["type"] = determine_source_type(data["title"], data["author"])
        data["created_at"] = now
        data["updated_at"] = now

    # Show preview
    logger.info("\nTop 10 sources:")
    sorted_sources = sorted(
        sources.items(), key=lambda x: x[1]["chunk_count"], reverse=True
    )
    for source_id, data in sorted_sources[:10]:
        logger.info(f"  {data['chunk_count']:3d} chunks: {source_id} ({data['type']})")

    if dry_run:
        logger.info("\nDRY RUN - No changes made")
        return {
            "chunks": len(chunks),
            "sources": len(sources),
            "dry_run": True,
        }

    # Write sources to Firestore
    logger.info("\nWriting sources to Firestore...")
    sources_ref = db.collection(SOURCES_COLLECTION)

    batch_size = 100
    written = 0

    source_items = list(sources.items())
    for i in range(0, len(source_items), batch_size):
        batch = db.batch()
        batch_items = source_items[i : i + batch_size]

        for source_id, data in batch_items:
            doc_ref = sources_ref.document(source_id)
            batch.set(doc_ref, data)
            written += 1

        batch.commit()
        logger.info(f"  Written {written}/{len(sources)} sources")

    # Update chunks with source_id
    logger.info("\nUpdating chunks with source_id...")

    # Build chunk -> source_id mapping
    chunk_to_source = {}
    for source_id, data in sources.items():
        for chunk_id in data["chunk_ids"]:
            chunk_to_source[chunk_id] = source_id

    updated = 0
    chunk_items = list(chunk_to_source.items())

    for i in range(0, len(chunk_items), batch_size):
        batch = db.batch()
        batch_items = chunk_items[i : i + batch_size]

        for chunk_id, source_id in batch_items:
            doc_ref = chunks_ref.document(chunk_id)
            batch.update(doc_ref, {"source_id": source_id})
            updated += 1

        batch.commit()
        logger.info(f"  Updated {updated}/{len(chunks)} chunks")

    logger.info("\n" + "=" * 60)
    logger.info("Migration complete!")
    logger.info(f"  Sources created: {len(sources)}")
    logger.info(f"  Chunks updated: {updated}")
    logger.info("=" * 60)

    return {
        "chunks": len(chunks),
        "sources": len(sources),
        "updated": updated,
        "dry_run": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract sources from chunks and create sources collection"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to Firestore",
    )

    args = parser.parse_args()

    try:
        result = run_migration(dry_run=args.dry_run)

        if not args.dry_run:
            logger.info("\nMigration successful!")

        sys.exit(0)

    except Exception as e:
        logger.exception(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
