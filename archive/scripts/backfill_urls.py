#!/usr/bin/env python3
"""
URL Backfill Script for Story 2.7 - URL Link Storage.

Populates URL fields (readwise_url, source_url, highlight_url) for all existing
chunks in Firestore by reading raw JSON data from GCS.

Usage:
    # Dry-run mode (no writes):
    python3 scripts/backfill_urls.py --dry-run

    # Execute backfill:
    python3 scripts/backfill_urls.py

    # With custom project and bucket:
    python3 scripts/backfill_urls.py --project kx-hub --bucket kx-hub-raw-json

Environment Variables:
    GCP_PROJECT: Google Cloud project ID (default: kx-hub)
    GOOGLE_APPLICATION_CREDENTIALS: Path to service account key

Performance:
    - Target: <5 minutes for 825+ chunks
    - Batch size: 500 Firestore writes per batch
    - Expected: ~1-2 minutes total execution time

Story Reference: docs/stories/2.7-url-link-storage.md
"""

import os
import sys
import json
import logging
import argparse
import time
from typing import Dict, Any, Optional, List

from google.cloud import firestore, storage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class URLBackfiller:
    """
    Backfills URL fields for existing Firestore chunks.

    Reads raw JSON files from GCS to extract URLs and updates
    Firestore documents in batches.
    """

    def __init__(
        self,
        project_id: str = 'kx-hub',
        raw_bucket_name: str = None,
        collection_name: str = 'kb_items',
        batch_size: int = 500,
        dry_run: bool = False
    ):
        """
        Initialize URL backfiller.

        Args:
            project_id: GCP project ID
            raw_bucket_name: GCS bucket with raw JSON files
            collection_name: Firestore collection name
            batch_size: Number of updates per Firestore batch
            dry_run: If True, log changes without writing
        """
        self.project_id = project_id
        self.raw_bucket_name = raw_bucket_name or f"{project_id}-raw-json"
        self.collection_name = collection_name
        self.batch_size = batch_size
        self.dry_run = dry_run

        # Initialize clients
        logger.info(f"Initializing clients for project: {project_id}")
        self.db = firestore.Client(project=project_id)
        self.storage_client = storage.Client(project=project_id)
        self.bucket = self.storage_client.bucket(self.raw_bucket_name)

    def load_url_mappings(self) -> Dict[str, Dict[str, Optional[str]]]:
        """
        Load URL mappings from all raw JSON files in GCS.

        Returns:
            Dictionary mapping user_book_id to URL fields
        """
        logger.info(f"Loading raw JSON files from GCS bucket: {self.raw_bucket_name}")

        url_map: Dict[str, Dict[str, Optional[str]]] = {}
        highlight_urls: Dict[str, Dict[int, str]] = {}  # user_book_id -> {highlight_id: url}

        blobs = list(self.bucket.list_blobs())
        logger.info(f"Found {len(blobs)} raw JSON files")

        for blob in blobs:
            if not blob.name.endswith('.json'):
                continue

            try:
                raw_text = blob.download_as_text()
                raw_data = json.loads(raw_text)

                # Extract user_book_id as string (matches Firestore parent_doc_id)
                user_book_id = str(raw_data.get('user_book_id', ''))
                if not user_book_id:
                    logger.warning(f"Missing user_book_id in {blob.name}")
                    continue

                # Extract book-level URLs
                url_map[user_book_id] = {
                    'readwise_url': raw_data.get('readwise_url'),
                    'source_url': raw_data.get('source_url'),  # Often null for books
                    'highlight_url': None  # Will be set per-chunk if available
                }

                # Extract highlight-level URLs for per-chunk assignment
                highlights = raw_data.get('highlights', [])
                if highlights:
                    highlight_urls[user_book_id] = {}
                    for hl in highlights:
                        hl_id = hl.get('id')
                        hl_url = hl.get('readwise_url')
                        if hl_id and hl_url:
                            highlight_urls[user_book_id][hl_id] = hl_url

                    # Also store first highlight URL for book-level reference
                    first_hl = highlights[0]
                    first_hl_url = first_hl.get('readwise_url')
                    if first_hl_url:
                        url_map[user_book_id]['highlight_url'] = first_hl_url

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from {blob.name}: {e}")
            except Exception as e:
                logger.error(f"Error processing {blob.name}: {e}")

        logger.info(f"Loaded URL mappings for {len(url_map)} books")
        return url_map

    def get_chunks_to_update(self) -> List[firestore.DocumentSnapshot]:
        """
        Get all chunks from Firestore that need URL backfill.

        Returns:
            List of Firestore document snapshots
        """
        logger.info(f"Loading chunks from Firestore collection: {self.collection_name}")

        collection_ref = self.db.collection(self.collection_name)
        chunks = list(collection_ref.stream())

        logger.info(f"Found {len(chunks)} chunks to update")
        return chunks

    def backfill(self) -> Dict[str, int]:
        """
        Execute the URL backfill operation.

        Returns:
            Statistics dictionary with counts
        """
        start_time = time.time()

        # Load URL mappings from GCS
        url_map = self.load_url_mappings()

        if not url_map:
            logger.error("No URL mappings loaded. Aborting.")
            return {'total': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

        # Get chunks to update
        chunks = self.get_chunks_to_update()

        if not chunks:
            logger.error("No chunks found. Aborting.")
            return {'total': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

        # Statistics
        stats = {
            'total': len(chunks),
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'missing_mapping': 0
        }

        if self.dry_run:
            logger.info("[DRY RUN] Would update the following chunks:")

        # Batch update Firestore
        batch = self.db.batch()
        batch_count = 0
        total_batches = 0

        for i, chunk_doc in enumerate(chunks):
            chunk_id = chunk_doc.id
            data = chunk_doc.to_dict()

            # Get parent_doc_id to look up URLs
            # Convert to string for consistent lookup (Firestore may store as int)
            parent_doc_id = data.get('parent_doc_id')
            if parent_doc_id is not None:
                parent_doc_id = str(parent_doc_id)
            elif data.get('user_book_id') is not None:
                parent_doc_id = str(data.get('user_book_id'))

            if not parent_doc_id:
                # Try to extract from chunk_id (format: {user_book_id}-chunk-{index})
                if '-chunk-' in chunk_id:
                    parent_doc_id = chunk_id.split('-chunk-')[0]

            if parent_doc_id and parent_doc_id in url_map:
                urls = url_map[parent_doc_id]

                update_data = {
                    'readwise_url': urls['readwise_url'],
                    'source_url': urls['source_url'],
                    'highlight_url': urls['highlight_url']
                }

                if self.dry_run:
                    if i < 5:  # Only show first 5 in dry-run
                        logger.info(f"  Would update {chunk_id}: readwise_url={urls['readwise_url'][:50] if urls['readwise_url'] else None}...")
                else:
                    batch.update(chunk_doc.reference, update_data)
                    batch_count += 1

                stats['updated'] += 1
            else:
                stats['missing_mapping'] += 1
                if i < 3:  # Log first few missing mappings
                    logger.warning(f"No URL mapping for chunk {chunk_id} (parent_doc_id: {parent_doc_id})")

            # Commit batch every batch_size operations
            if not self.dry_run and batch_count >= self.batch_size:
                try:
                    batch.commit()
                    total_batches += 1
                    logger.info(f"  Committed batch {total_batches} ({stats['updated']} chunks updated)")
                except Exception as e:
                    logger.error(f"Error committing batch: {e}")
                    stats['errors'] += batch_count
                    # Retry once
                    try:
                        time.sleep(2)
                        batch.commit()
                        logger.info("Retry successful")
                    except Exception as retry_e:
                        logger.error(f"Retry failed: {retry_e}")

                batch = self.db.batch()
                batch_count = 0

            # Progress logging every 100 chunks
            if (i + 1) % 100 == 0:
                logger.info(f"  Progress: {i + 1}/{len(chunks)} chunks processed")

        # Commit remaining operations
        if not self.dry_run and batch_count > 0:
            try:
                batch.commit()
                total_batches += 1
                logger.info(f"  Committed final batch ({batch_count} updates)")
            except Exception as e:
                logger.error(f"Error committing final batch: {e}")
                stats['errors'] += batch_count

        elapsed_time = time.time() - start_time

        # Print summary
        logger.info("")
        logger.info("=" * 50)
        if self.dry_run:
            logger.info("[DRY RUN] Backfill Summary (no changes made)")
        else:
            logger.info("Backfill Complete!")
        logger.info("=" * 50)
        logger.info(f"Total chunks:      {stats['total']}")
        logger.info(f"Updated:           {stats['updated']}")
        logger.info(f"Missing mapping:   {stats['missing_mapping']}")
        logger.info(f"Errors:            {stats['errors']}")
        logger.info(f"Execution time:    {elapsed_time:.1f} seconds")
        logger.info("=" * 50)

        return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Backfill URL fields for existing Firestore chunks'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Log changes without writing to Firestore'
    )
    parser.add_argument(
        '--project',
        default=os.environ.get('GCP_PROJECT', 'kx-hub'),
        help='GCP project ID (default: kx-hub)'
    )
    parser.add_argument(
        '--bucket',
        default=None,
        help='GCS bucket with raw JSON files (default: {project}-raw-json)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=500,
        help='Firestore batch size (default: 500)'
    )

    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("URL Backfill Script - Story 2.7")
    logger.info("=" * 50)
    logger.info(f"Project:    {args.project}")
    logger.info(f"Bucket:     {args.bucket or f'{args.project}-raw-json'}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Dry run:    {args.dry_run}")
    logger.info("=" * 50)

    if not args.dry_run:
        # Confirm with user before writing
        response = input("\nThis will update Firestore documents. Continue? [y/N]: ")
        if response.lower() != 'y':
            logger.info("Aborted. No changes made.")
            sys.exit(0)

    backfiller = URLBackfiller(
        project_id=args.project,
        raw_bucket_name=args.bucket,
        batch_size=args.batch_size,
        dry_run=args.dry_run
    )

    stats = backfiller.backfill()

    # Exit with error code if significant failures
    if stats['errors'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
