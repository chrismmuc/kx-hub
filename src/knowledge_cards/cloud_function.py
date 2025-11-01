"""
Cloud Function Entry Point for Knowledge Card Generation

This module provides the Cloud Function handler for generating knowledge cards.
Called by the batch-pipeline workflow after the embed step.

Entry point: generate_cards_handler
"""

import functions_framework
import logging
from typing import Dict, Any

# Import run_pipeline - handle both module and standalone contexts
try:
    from main import run_pipeline
except ImportError:
    from .main import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@functions_framework.http
def generate_cards_handler(request) -> tuple:
    """
    Cloud Function HTTP handler for knowledge card generation.

    Expected request body:
    {
        "run_id": "run-20231101-120000",  // Optional: for tracking
        "limit": null,  // Optional: limit chunks for testing
        "batch_size": 100  // Optional: batch size (default 100)
    }

    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Parse request
        request_json = request.get_json(silent=True) or {}
        run_id = request_json.get('run_id', 'unknown')
        limit = request_json.get('limit')
        batch_size = request_json.get('batch_size', 100)

        logger.info(f"Knowledge card generation triggered for run_id: {run_id}")
        logger.info(f"Parameters: limit={limit}, batch_size={batch_size}")

        # Run the pipeline
        results = run_pipeline(
            batch_size=batch_size,
            dry_run=False,
            limit=limit
        )

        # Check for failures
        if results['failed'] > 0:
            logger.warning(
                f"Knowledge card generation completed with {results['failed']} failures "
                f"out of {results['total_chunks']} chunks"
            )

        # Return success response
        response = {
            'status': 'success' if results['failed'] == 0 else 'partial_success',
            'run_id': run_id,
            'total_chunks': results['total_chunks'],
            'generated': results['generated'],
            'updated': results['updated'],
            'failed': results['failed'],
            'duration_seconds': round(results['duration'], 2),
            'cost_estimate_usd': round(results['cost_estimate']['total_cost'], 4)
        }

        status_code = 200 if results['failed'] == 0 else 206  # 206 = Partial Content

        logger.info(f"Knowledge card generation complete: {response}")

        return (response, status_code)

    except Exception as e:
        logger.exception(f"Knowledge card generation failed: {e}")

        error_response = {
            'status': 'error',
            'error': str(e),
            'run_id': request_json.get('run_id', 'unknown') if 'request_json' in locals() else 'unknown'
        }

        return (error_response, 500)
