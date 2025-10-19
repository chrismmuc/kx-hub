"""
Cloud Function to normalize raw Readwise JSON to Markdown with frontmatter.

This function is triggered by Cloud Workflows as part of the batch processing pipeline.
It reads JSON files from the raw-json bucket and writes Markdown files to the
markdown-normalized bucket.
"""

import json
import logging
import os
from typing import Tuple

from google.cloud import storage

# Import transformer - handle both relative and absolute imports
try:
    from .transformer import json_to_markdown
except ImportError:
    from transformer import json_to_markdown

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get project ID from environment
PROJECT_ID = os.environ.get("GCP_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT"))

# Lazy client initialization pattern (for testability)
storage_client = None


def _get_storage_client():
    """Get or create storage client (lazy initialization)."""
    global storage_client
    if storage_client is None:
        storage_client = storage.Client(project=PROJECT_ID)
    return storage_client


def _get_bucket_names():
    """Get bucket names based on project ID."""
    if not PROJECT_ID:
        raise ValueError("PROJECT_ID not set. Set GCP_PROJECT or GOOGLE_CLOUD_PROJECT environment variable.")

    return {
        "raw": f"{PROJECT_ID}-raw-json",
        "markdown": f"{PROJECT_ID}-markdown-normalized"
    }


def normalize_handler(request):
    """
    Cloud Function entry point for normalization.

    Reads all JSON files from raw-json bucket, transforms them to Markdown,
    and writes to markdown-normalized bucket.

    Args:
        request: Flask request object (not used, triggered by workflow)

    Returns:
        Tuple of (response_body, status_code)
    """
    logger.info("Starting normalization process")

    try:
        bucket_names = _get_bucket_names()
        client = _get_storage_client()

        # Get buckets
        raw_bucket = client.bucket(bucket_names["raw"])
        output_bucket = client.bucket(bucket_names["markdown"])

        # List all JSON files
        blobs = list(raw_bucket.list_blobs())
        logger.info(f"Found {len(blobs)} files to process")

        files_processed = 0
        errors = 0

        for blob in blobs:
            try:
                logger.info(f"Processing: {blob.name}")

                # Read JSON
                json_content = blob.download_as_text()
                book_data = json.loads(json_content)

                # Transform to Markdown
                markdown_content = json_to_markdown(book_data)

                # Generate output filename: notes/{user_book_id}.md
                user_book_id = book_data["user_book_id"]
                output_filename = f"notes/{user_book_id}.md"

                # Write to output bucket
                output_blob = output_bucket.blob(output_filename)
                output_blob.upload_from_string(
                    markdown_content,
                    content_type="text/markdown; charset=utf-8"
                )

                logger.info(f"✓ Wrote: {output_filename}")
                files_processed += 1

            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error in {blob.name}: {e}")
                errors += 1
            except KeyError as e:
                logger.error(f"Missing required field in {blob.name}: {e}")
                errors += 1
            except Exception as e:
                logger.error(f"Error processing {blob.name}: {e}")
                errors += 1

        # Summary
        logger.info(f"Normalization complete: {files_processed} processed, {errors} errors")

        response = {
            "status": "success",
            "files_processed": files_processed,
            "errors": errors
        }

        return json.dumps(response), 200

    except Exception as e:
        logger.error(f"Fatal error in normalization: {e}")
        error_response = {
            "status": "error",
            "message": str(e)
        }
        return json.dumps(error_response), 500


# For Cloud Functions 2nd gen
def normalize(request):
    """Cloud Functions 2nd gen entry point."""
    return normalize_handler(request)
