"""
Retry Failed Knowledge Card Generation

Reads the log file, extracts failed chunk IDs, and retries generation.
Can be run after the main pipeline completes.

Usage:
    python -m src.knowledge_cards.retry_failed /tmp/knowledge_cards_run.log
"""

import sys
import re
import logging
from typing import List, Set
from .main import run_pipeline, get_firestore_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_failed_chunk_ids(log_file_path: str) -> Set[str]:
    """
    Extract failed chunk IDs from the log file.

    Args:
        log_file_path: Path to the knowledge cards run log

    Returns:
        Set of failed chunk IDs
    """
    failed_chunks = set()

    # Pattern: "Failed to generate card for chunk <chunk_id>:"
    pattern = r"Failed to generate card for chunk ([a-zA-Z0-9\-]+):"

    try:
        with open(log_file_path, 'r') as f:
            for line in f:
                match = re.search(pattern, line)
                if match:
                    chunk_id = match.group(1)
                    failed_chunks.add(chunk_id)
    except FileNotFoundError:
        logger.error(f"Log file not found: {log_file_path}")
        sys.exit(1)

    return failed_chunks


def get_failed_chunks_from_firestore(failed_chunk_ids: Set[str]) -> List[dict]:
    """
    Load failed chunks from Firestore by ID.

    Args:
        failed_chunk_ids: Set of chunk IDs that failed

    Returns:
        List of chunk documents
    """
    db = get_firestore_client()
    collection_ref = db.collection('kb_items')

    chunks = []
    for chunk_id in failed_chunk_ids:
        try:
            doc = collection_ref.document(chunk_id).get()
            if doc.exists:
                chunk_data = doc.to_dict()
                chunk_data['id'] = doc.id
                chunks.append(chunk_data)
            else:
                logger.warning(f"Chunk not found in Firestore: {chunk_id}")
        except Exception as e:
            logger.error(f"Error loading chunk {chunk_id}: {e}")

    return chunks


def main():
    """Main entry point for retry script"""
    if len(sys.argv) < 2:
        print("Usage: python -m src.knowledge_cards.retry_failed <log_file_path>")
        print("Example: python -m src.knowledge_cards.retry_failed /tmp/knowledge_cards_run.log")
        sys.exit(1)

    log_file_path = sys.argv[1]

    logger.info(f"Extracting failed chunk IDs from: {log_file_path}")
    failed_chunk_ids = extract_failed_chunk_ids(log_file_path)

    if not failed_chunk_ids:
        logger.info("No failed chunks found in log file. Nothing to retry.")
        return

    logger.info(f"Found {len(failed_chunk_ids)} failed chunks")
    logger.info(f"Failed chunk IDs: {sorted(list(failed_chunk_ids))[:10]}...")  # Show first 10

    # Load failed chunks from Firestore
    logger.info("Loading failed chunks from Firestore...")
    failed_chunks = get_failed_chunks_from_firestore(failed_chunk_ids)

    if not failed_chunks:
        logger.warning("No chunks loaded from Firestore. Exiting.")
        return

    logger.info(f"Loaded {len(failed_chunks)} chunks from Firestore")

    # Retry with the same pipeline but only failed chunks
    logger.info("Retrying failed chunks...")
    from .generator import process_chunks_batch
    from .main import update_firestore_with_cards

    # Process failed chunks
    results = process_chunks_batch(failed_chunks, batch_size=100)

    logger.info(f"Retry complete:")
    logger.info(f"  Succeeded: {results['processed']}")
    logger.info(f"  Failed: {results['failed']}")

    # Update Firestore with successful retries
    if results['cards']:
        logger.info(f"Updating Firestore with {len(results['cards'])} retried cards...")
        update_results = update_firestore_with_cards(results['cards'], dry_run=False)
        logger.info(f"Firestore update: {update_results['updated']} succeeded, {update_results['failed']} failed")

    # Report still-failing chunks
    if results['failed'] > 0:
        logger.warning(f"{results['failed']} chunks still failed after retry")
        logger.info("These chunks may need manual review or prompt adjustment")


if __name__ == '__main__':
    main()
