"""
Migration script to extract highlighted_at from chunk content and store as queryable field.

This fixes the issue where get_recent queries by created_at (ingestion time) instead of
actual reading time (highlighted_at).

Usage:
    # Dry run (no changes)
    python scripts/migrate_highlighted_at.py --dry-run

    # Actually migrate
    python scripts/migrate_highlighted_at.py

    # Limit to N documents (for testing)
    python scripts/migrate_highlighted_at.py --limit 10 --dry-run
"""

import argparse
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Regex to extract "Highlighted: 2025-04-25T04:56:00Z" from content
HIGHLIGHTED_PATTERN = re.compile(r"Highlighted:\s*(\d{4}-\d{2}-\d{2}T[\d:\.]+Z?)")


def parse_highlighted_dates(content: str) -> list[datetime]:
    """Extract all highlighted_at timestamps from chunk content."""
    dates = []
    for match in HIGHLIGHTED_PATTERN.finditer(content):
        date_str = match.group(1)
        try:
            # Handle both with and without Z suffix
            if not date_str.endswith("Z"):
                date_str += "Z"
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            dates.append(dt)
        except ValueError as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
    return dates


def migrate_chunks(dry_run: bool = True, limit: Optional[int] = None):
    """Migrate all chunks to add last_highlighted_at field."""
    project = os.getenv("GCP_PROJECT", "kx-hub")
    db = firestore.Client(project=project)
    collection = db.collection("kb_items")

    query = collection
    if limit:
        query = query.limit(limit)

    stats = {
        "total": 0,
        "updated": 0,
        "skipped_no_dates": 0,
        "skipped_already_set": 0,
        "errors": 0,
    }

    logger.info(f"Starting migration (dry_run={dry_run}, limit={limit})")

    for doc in query.stream():
        stats["total"] += 1
        doc_id = doc.id
        data = doc.to_dict()

        # Skip if already has last_highlighted_at
        if data.get("last_highlighted_at"):
            stats["skipped_already_set"] += 1
            continue

        content = data.get("content", "")
        dates = parse_highlighted_dates(content)

        if not dates:
            stats["skipped_no_dates"] += 1
            logger.debug(f"{doc_id}: No highlighted dates found in content")
            continue

        # Get the most recent highlighted_at
        last_highlighted = max(dates)
        # Also get the earliest for first_highlighted_at
        first_highlighted = min(dates)

        title = data.get("title", "Unknown")[:50]
        logger.info(
            f"{doc_id}: {title}... | "
            f"first={first_highlighted.date()} last={last_highlighted.date()} "
            f"(found {len(dates)} dates)"
        )

        if not dry_run:
            try:
                doc.reference.update(
                    {
                        "last_highlighted_at": last_highlighted,
                        "first_highlighted_at": first_highlighted,
                    }
                )
                stats["updated"] += 1
            except Exception as e:
                logger.error(f"Failed to update {doc_id}: {e}")
                stats["errors"] += 1
        else:
            stats["updated"] += 1  # Would have updated

    logger.info(f"Migration complete: {stats}")
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Migrate highlighted_at dates to Firestore"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't actually write changes"
    )
    parser.add_argument(
        "--limit", type=int, help="Limit number of documents to process"
    )
    args = parser.parse_args()

    migrate_chunks(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
