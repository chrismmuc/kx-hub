"""
Knowledge Card Generation Pipeline

Main entry point for generating knowledge cards for all chunks in Firestore.
Story 2.1: Knowledge Card Generation (Epic 2)

Usage:
    python -m src.knowledge_cards.main

Environment Variables:
    GCP_PROJECT: Google Cloud project ID (default: kx-hub)
    GCP_REGION: Google Cloud region (default: europe-west4)
    FIRESTORE_COLLECTION: Firestore collection name (default: kb_items)
    DRY_RUN: If set to "true", don't write to Firestore (default: false)
"""

import os
import sys
import logging
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime

# Google Cloud imports
try:
    from google.cloud import firestore
    _HAS_FIRESTORE = True
except ImportError:
    _HAS_FIRESTORE = False
    firestore = None

from .generator import process_chunks_batch, estimate_cost
from .schema import KnowledgeCard

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
GCP_PROJECT = os.environ.get('GCP_PROJECT', 'kx-hub')
FIRESTORE_COLLECTION = os.environ.get('FIRESTORE_COLLECTION', 'kb_items')
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'

# Global Firestore client (lazy initialization)
_firestore_client = None


def get_firestore_client() -> firestore.Client:
    """
    Get or create Firestore client instance (cached).

    Returns:
        Initialized Firestore client
    """
    global _firestore_client

    if not _HAS_FIRESTORE:
        raise ImportError(
            "google-cloud-firestore is required. "
            "Install with: pip install google-cloud-firestore"
        )

    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT)
        logger.info(f"Initialized Firestore client for project: {GCP_PROJECT}")

    return _firestore_client


def load_all_chunks() -> List[Dict[str, Any]]:
    """
    Load all chunks from Firestore kb_items collection.

    Returns:
        List of chunk dictionaries with required fields: chunk_id, title, author, content

    Raises:
        Exception: If Firestore query fails
    """
    logger.info(f"Loading all chunks from Firestore collection: {FIRESTORE_COLLECTION}")

    db = get_firestore_client()
    collection_ref = db.collection(FIRESTORE_COLLECTION)

    # Query all documents (no limit for AC #1: 100% coverage)
    docs = collection_ref.stream()

    chunks = []
    for doc in docs:
        chunk_data = doc.to_dict()
        chunk_data['id'] = doc.id  # Add document ID if not present as chunk_id

        # Validate required fields exist
        if 'content' not in chunk_data or not chunk_data['content']:
            logger.warning(f"Skipping chunk {doc.id}: missing content")
            continue

        chunks.append(chunk_data)

    logger.info(f"Loaded {len(chunks)} chunks from Firestore")

    return chunks


def update_firestore_with_cards(
    cards: List[tuple],
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Update Firestore with generated knowledge cards (AC #6).

    Args:
        cards: List of (chunk_id, KnowledgeCard) tuples
        dry_run: If True, don't actually write to Firestore (for testing)

    Returns:
        Dictionary with update statistics:
        - updated: Number of documents updated
        - failed: Number of updates that failed

    Note: Uses merge=True to preserve existing chunk fields (constraint from context)
    """
    logger.info(f"Updating Firestore with {len(cards)} knowledge cards (dry_run={dry_run})")

    if dry_run:
        logger.info("DRY RUN: Skipping Firestore writes")
        return {'updated': len(cards), 'failed': 0}

    db = get_firestore_client()
    collection_ref = db.collection(FIRESTORE_COLLECTION)

    updated = 0
    failed = 0

    # Batch updates for efficiency (AC #6: batch writes)
    BATCH_SIZE = 100  # Firestore batch write limit is 500, use 100 for safety

    for i in range(0, len(cards), BATCH_SIZE):
        batch = db.batch()
        batch_cards = cards[i:i + BATCH_SIZE]

        for chunk_id, knowledge_card in batch_cards:
            try:
                doc_ref = collection_ref.document(chunk_id)

                # Update with knowledge_card field (merge=True to preserve existing fields)
                batch.set(
                    doc_ref,
                    {'knowledge_card': knowledge_card.to_dict()},
                    merge=True
                )

                updated += 1

            except Exception as e:
                logger.error(f"Failed to prepare update for chunk {chunk_id}: {e}")
                failed += 1

        try:
            # Commit batch write
            batch.commit()
            logger.info(f"Batch {i // BATCH_SIZE + 1}: Updated {len(batch_cards)} documents")

        except Exception as e:
            logger.error(f"Batch write failed: {e}")
            failed += len(batch_cards)
            updated -= len(batch_cards)

    logger.info(f"Firestore updates complete: {updated} succeeded, {failed} failed")

    return {'updated': updated, 'failed': failed}


def run_pipeline(
    batch_size: int = 100,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Run the complete knowledge card generation pipeline (AC #1-6).

    Steps:
    1. Load all chunks from Firestore
    2. Generate knowledge cards for all chunks (batch processing)
    3. Update Firestore with knowledge cards

    Args:
        batch_size: Number of chunks to process per batch (default: 100)
        dry_run: If True, don't write to Firestore (default: False)
        limit: Optional limit on number of chunks to process (for testing)

    Returns:
        Dictionary with pipeline results:
        - total_chunks: Total chunks loaded
        - generated: Number of knowledge cards generated
        - updated: Number of Firestore documents updated
        - failed: Number of failures
        - duration: Total pipeline duration in seconds
        - cost_estimate: Estimated cost breakdown

    Example:
        >>> results = run_pipeline(dry_run=True, limit=10)
        >>> print(f"Generated {results['generated']} cards in {results['duration']}s")
    """
    pipeline_start = datetime.now()
    logger.info("=" * 80)
    logger.info("Knowledge Card Generation Pipeline - Starting")
    logger.info(f"Batch size: {batch_size} | Dry run: {dry_run} | Limit: {limit or 'None'}")
    logger.info("=" * 80)

    # Step 1: Load chunks from Firestore
    chunks = load_all_chunks()

    if limit:
        logger.info(f"Limiting to first {limit} chunks for testing")
        chunks = chunks[:limit]

    total_chunks = len(chunks)

    if total_chunks == 0:
        logger.warning("No chunks found in Firestore. Exiting.")
        return {
            'total_chunks': 0,
            'generated': 0,
            'updated': 0,
            'failed': 0,
            'duration': 0,
            'cost_estimate': estimate_cost(0)
        }

    # Show cost estimate upfront
    cost_estimate = estimate_cost(total_chunks)
    logger.info(f"Cost estimate for {total_chunks} chunks: ${cost_estimate['total_cost']:.4f}")
    logger.info(f"  Input tokens: {total_chunks * 500} (~${cost_estimate['input_cost']:.4f})")
    logger.info(f"  Output tokens: {total_chunks * 150} (~${cost_estimate['output_cost']:.4f})")

    # Step 2: Generate knowledge cards (batch processing)
    logger.info(f"\nGenerating knowledge cards for {total_chunks} chunks...")
    generation_results = process_chunks_batch(chunks, batch_size=batch_size)

    generated_cards = generation_results['cards']
    generation_failed = generation_results['failed']

    logger.info(f"Knowledge card generation complete:")
    logger.info(f"  Generated: {len(generated_cards)}")
    logger.info(f"  Failed: {generation_failed}")
    logger.info(f"  Duration: {generation_results['duration']:.1f}s")
    logger.info(f"  Throughput: {generation_results['chunks_per_second']:.1f} chunks/sec")

    # Step 3: Update Firestore with knowledge cards
    logger.info(f"\nUpdating Firestore with {len(generated_cards)} knowledge cards...")
    update_results = update_firestore_with_cards(generated_cards, dry_run=dry_run)

    pipeline_end = datetime.now()
    total_duration = (pipeline_end - pipeline_start).total_seconds()

    # Final summary
    logger.info("=" * 80)
    logger.info("Knowledge Card Generation Pipeline - Complete")
    logger.info(f"Total chunks: {total_chunks}")
    logger.info(f"Generated: {len(generated_cards)}")
    logger.info(f"Updated: {update_results['updated']}")
    logger.info(f"Failed: {generation_failed + update_results['failed']}")
    logger.info(f"Duration: {total_duration:.1f}s")
    logger.info(f"Estimated cost: ${cost_estimate['total_cost']:.4f}")
    logger.info("=" * 80)

    return {
        'total_chunks': total_chunks,
        'generated': len(generated_cards),
        'updated': update_results['updated'],
        'failed': generation_failed + update_results['failed'],
        'duration': total_duration,
        'cost_estimate': cost_estimate
    }


def main():
    """Main entry point for CLI"""
    parser = argparse.ArgumentParser(
        description='Generate knowledge cards for all chunks in Firestore'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of chunks to process per batch (default: 100)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate cards but don\'t write to Firestore'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit processing to first N chunks (for testing)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        results = run_pipeline(
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            limit=args.limit
        )

        # Exit with error code if any failures
        if results['failed'] > 0:
            logger.error(f"Pipeline completed with {results['failed']} failures")
            sys.exit(1)
        else:
            logger.info("Pipeline completed successfully!")
            sys.exit(0)

    except Exception as e:
        logger.exception(f"Pipeline failed with exception: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
