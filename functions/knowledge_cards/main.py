"""
Cloud Function Entry Point for Knowledge Card Generation
"""
import os
import logging
import functions_framework
from typing import Dict, Any

from generator import process_chunks_batch
from schema import KnowledgeCard

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
GCP_PROJECT = os.environ.get('GCP_PROJECT', 'kx-hub')
GCP_REGION = os.environ.get('GCP_REGION', 'europe-west4')
FIRESTORE_COLLECTION = os.environ.get('FIRESTORE_COLLECTION', 'kb_items')


def get_firestore_client():
    """Initialize Firestore client"""
    from google.cloud import firestore
    return firestore.Client(project=GCP_PROJECT, database='(default)')


def load_chunks_for_generation(limit=None):
    """Load chunks from Firestore that need knowledge cards"""
    db = get_firestore_client()
    collection_ref = db.collection(FIRESTORE_COLLECTION)

    # Get all chunks (could filter for missing knowledge_card field)
    query = collection_ref
    if limit:
        query = query.limit(limit)

    chunks = []
    for doc in query.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        chunks.append(data)

    logger.info(f"Loaded {len(chunks)} chunks from Firestore")
    return chunks


def update_firestore_with_cards(cards: list[Dict[str, Any]], dry_run=False):
    """Update Firestore with generated knowledge cards"""
    if dry_run:
        logger.info(f"DRY RUN: Would update {len(cards)} cards")
        return {'updated': len(cards), 'failed': 0}

    db = get_firestore_client()
    collection_ref = db.collection(FIRESTORE_COLLECTION)

    updated = 0
    failed = 0

    for card_data in cards:
        try:
            chunk_id = card_data['chunk_id']
            knowledge_card = card_data['knowledge_card']

            doc_ref = collection_ref.document(chunk_id)
            doc_ref.set({'knowledge_card': knowledge_card}, merge=True)
            updated += 1
        except Exception as e:
            logger.error(f"Failed to update {card_data.get('chunk_id')}: {e}")
            failed += 1

    logger.info(f"Firestore update complete: {updated} succeeded, {failed} failed")
    return {'updated': updated, 'failed': failed}


@functions_framework.http
def generate_cards_handler(request):
    """
    Cloud Function HTTP handler for knowledge card generation.

    Expected request body:
    {
        "run_id": "run-20231101-120000",  // Optional
        "limit": null,  // Optional: limit chunks for testing
        "batch_size": 100  // Optional
    }
    """
    try:
        request_json = request.get_json(silent=True) or {}
        run_id = request_json.get('run_id', 'unknown')
        limit = request_json.get('limit')
        batch_size = request_json.get('batch_size', 100)

        logger.info(f"Knowledge card generation triggered for run_id: {run_id}")
        logger.info(f"Parameters: limit={limit}, batch_size={batch_size}")

        # Load chunks
        chunks = load_chunks_for_generation(limit=limit)

        if not chunks:
            return {'status': 'success', 'message': 'No chunks to process'}

        # Process chunks
        results = process_chunks_batch(chunks, batch_size=batch_size)

        # Update Firestore
        update_results = update_firestore_with_cards(results['cards'], dry_run=False)

        # Prepare response
        response = {
            'status': 'success' if results['failed'] == 0 else 'partial_success',
            'run_id': run_id,
            'total_chunks': len(chunks),
            'generated': results['processed'],
            'updated': update_results['updated'],
            'failed': results['failed'],
            'cost_estimate_usd': round(results['cost_estimate']['total_cost'], 4)
        }

        logger.info(f"Knowledge card generation complete: {response}")

        return response

    except Exception as e:
        logger.exception(f"Knowledge card generation failed: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'run_id': request_json.get('run_id', 'unknown') if 'request_json' in locals() else 'unknown'
        }
