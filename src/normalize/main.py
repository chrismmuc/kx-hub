"""
Cloud Function to normalize raw Readwise JSON to Markdown with frontmatter.

This function is triggered by Cloud Workflows as part of the batch processing pipeline.
It reads JSON files from the raw-json bucket and writes Markdown files to the
markdown-normalized bucket.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict
from types import SimpleNamespace

from google.api_core.exceptions import NotFound

_HAS_STORAGE_LIB = True
_HAS_FIRESTORE_LIB = True

try:
    from google.cloud import storage, firestore
except ImportError:  # pragma: no cover - allow tests without GCP SDK
    _HAS_STORAGE_LIB = False
    _HAS_FIRESTORE_LIB = False
    storage = None  # type: ignore[assignment]
    firestore = None  # type: ignore[assignment]

try:
    from google.cloud.firestore_v1 import Increment
except ImportError:  # pragma: no cover - tests without Firestore SDK
    Increment = None  # type: ignore[assignment]

# Import transformer - handle both relative and absolute imports
try:
    from .transformer import json_to_markdown
except ImportError:
    from transformer import json_to_markdown

# Import chunker - handle both relative and absolute imports
try:
    from ..common.chunker import DocumentChunker, ChunkConfig
except ImportError:
    try:
        from common.chunker import DocumentChunker, ChunkConfig
    except ImportError:
        # Fallback for tests
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from common.chunker import DocumentChunker, ChunkConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get project ID from environment
PROJECT_ID = os.environ.get("GCP_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT"))
PIPELINE_BUCKET = os.environ.get("PIPELINE_BUCKET")
PIPELINE_MANIFEST_PREFIX = os.environ.get("PIPELINE_MANIFEST_PREFIX", "manifests")
PIPELINE_COLLECTION = os.environ.get("PIPELINE_COLLECTION", "pipeline_items")

# Chunking configuration
CHUNK_TARGET_TOKENS = int(os.environ.get("CHUNK_TARGET_TOKENS", "512"))
CHUNK_MAX_TOKENS = int(os.environ.get("CHUNK_MAX_TOKENS", "1024"))
CHUNK_MIN_TOKENS = int(os.environ.get("CHUNK_MIN_SIZE_TOKENS", "100"))
CHUNK_OVERLAP_TOKENS = int(os.environ.get("CHUNK_OVERLAP_TOKENS", "75"))

# Lazy client initialization pattern (for testability)
storage_client = None
firestore_client = None


def _get_storage_client():
    """Get or create storage client (lazy initialization)."""
    global storage_client
    if storage_client is None:
        if not _HAS_STORAGE_LIB:
            raise ImportError("google-cloud-storage is required to use _get_storage_client")
        storage_client = storage.Client(project=PROJECT_ID)
    return storage_client


def _get_firestore_client():
    """Get or create Firestore client (lazy initialization)."""
    global firestore_client
    if firestore_client is None:
        if not _HAS_FIRESTORE_LIB:
            raise ImportError("google-cloud-firestore is required to use _get_firestore_client")
        if not PROJECT_ID:
            raise ValueError("PROJECT_ID not configured for Firestore access")
        firestore_client = firestore.Client(project=PROJECT_ID)
    return firestore_client


def _get_bucket_names():
    """Get bucket names based on project ID."""
    if not PROJECT_ID:
        raise ValueError("PROJECT_ID not set. Set GCP_PROJECT or GOOGLE_CLOUD_PROJECT environment variable.")

    return {
        "raw": f"{PROJECT_ID}-raw-json",
        "markdown": f"{PROJECT_ID}-markdown-normalized"
    }


def _get_pipeline_bucket():
    if not PIPELINE_BUCKET:
        raise ValueError("PIPELINE_BUCKET environment variable must be set")
    return PIPELINE_BUCKET


def _manifest_blob_path(run_id: str) -> str:
    prefix = (PIPELINE_MANIFEST_PREFIX or "manifests").strip("/")
    if prefix:
        return f"{prefix}/{run_id}.json"
    return f"{run_id}.json"


def _parse_gcs_uri(uri: str) -> Dict[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"Unsupported URI format: {uri}")
    without_scheme = uri[5:]
    if "/" not in without_scheme:
        raise ValueError(f"Unsupported URI format: {uri}")
    bucket_name, object_name = without_scheme.split("/", 1)
    return {"bucket": bucket_name, "object": object_name}


def _compute_markdown_hash(markdown: str) -> str:
    return f"sha256:{hashlib.sha256(markdown.encode('utf-8')).hexdigest()}"


def _load_manifest(run_id: str) -> Dict[str, Any]:
    client = _get_storage_client()
    bucket = client.bucket(_get_pipeline_bucket())
    blob_path = _manifest_blob_path(run_id)
    blob = bucket.blob(blob_path)
    try:
        manifest_text = blob.download_as_text()
    except NotFound as exc:
        raise FileNotFoundError(f"Manifest not found for run_id {run_id}: gs://{bucket.name}/{blob_path}") from exc
    manifest = json.loads(manifest_text)
    if "items" not in manifest or manifest.get("run_id") != run_id:
        raise ValueError(f"Invalid manifest structure for run_id {run_id}")
    return manifest


def _increment_retry(existing: Dict[str, Any]) -> Any:
    if Increment is not None:
        return Increment(1)
    return existing.get("retry_count", 0) + 1


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

    request_json = request.get_json(silent=True) or {}
    run_id = request_json.get("run_id")
    if not run_id:
        error_response = {"status": "error", "message": "run_id is required"}
        return json.dumps(error_response), 400

    try:
        manifest = _load_manifest(run_id)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return json.dumps({"status": "error", "message": str(exc)}), 404
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Unable to load manifest for run_id {run_id}: {exc}")
        return json.dumps({"status": "error", "message": str(exc)}), 500

    bucket_names = _get_bucket_names()
    storage_client = _get_storage_client()
    firestore_client = _get_firestore_client()
    markdown_bucket = storage_client.bucket(bucket_names["markdown"])
    pipeline_collection = firestore_client.collection(PIPELINE_COLLECTION)

    stats = {
        "status": "success",
        "run_id": run_id,
        "manifest_items": len(manifest.get("items", [])),
        "processed": 0,
        "skipped": 0,
        "failed": 0
    }

    for item in manifest.get("items", []):
        item_id = str(item.get("id", "")).strip()
        raw_uri = item.get("raw_uri")
        raw_checksum = item.get("raw_checksum")

        if not item_id or not raw_uri or not raw_checksum:
            logger.error(f"Manifest entry missing required fields: {item}")
            stats["failed"] += 1
            continue

        doc_ref = pipeline_collection.document(item_id)
        snapshot = doc_ref.get()
        doc_data = snapshot.to_dict() if snapshot.exists else {}

        should_skip = (
            doc_data
            and doc_data.get("normalize_status") == "complete"
            and doc_data.get("raw_checksum") == raw_checksum
        )

        if should_skip:
            logger.info(f"Skipping {item_id}: raw checksum unchanged")
            doc_ref.set({
                "manifest_run_id": run_id,
                "last_transition_at": firestore.SERVER_TIMESTAMP
            }, merge=True)
            stats["skipped"] += 1
            continue

        # Mark as processing
        doc_ref.set({
            "raw_uri": raw_uri,
            "raw_updated_at": item.get("updated_at"),
            "raw_checksum": raw_checksum,
            "normalize_status": "processing",
            "manifest_run_id": run_id,
            "last_transition_at": firestore.SERVER_TIMESTAMP
        }, merge=True)

        try:
            uri_parts = _parse_gcs_uri(raw_uri)
            raw_blob = storage_client.bucket(uri_parts["bucket"]).blob(uri_parts["object"])
            json_content = raw_blob.download_as_text()
            book_data = json.loads(json_content)

            user_book_id = book_data["user_book_id"]
            markdown_content = json_to_markdown(book_data)

            # Initialize chunker with configuration
            chunker_config = ChunkConfig(
                target_tokens=CHUNK_TARGET_TOKENS,
                max_tokens=CHUNK_MAX_TOKENS,
                min_tokens=CHUNK_MIN_TOKENS,
                overlap_tokens=CHUNK_OVERLAP_TOKENS
            )
            chunker = DocumentChunker(config=chunker_config)

            # Split document into chunks
            chunks = chunker.split_into_chunks(markdown_content, parent_doc_id=user_book_id)

            logger.info(f"Split {item_id} into {len(chunks)} chunks")

            # Process each chunk
            for chunk in chunks:
                chunk_id = chunk.frontmatter['chunk_id']
                chunk_markdown = chunker.chunk_to_markdown(chunk)

                # Upload chunk markdown to GCS
                output_filename = f"notes/{chunk_id}.md"
                output_blob = markdown_bucket.blob(output_filename)
                output_blob.upload_from_string(
                    chunk_markdown,
                    content_type="text/markdown; charset=utf-8"
                )

                # Create or update pipeline_items entry for this chunk
                chunk_doc_ref = pipeline_collection.document(chunk_id)
                chunk_doc_ref.set({
                    "item_id": chunk_id,
                    "user_book_id": user_book_id,
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": chunk.total_chunks,
                    "raw_uri": raw_uri,
                    "raw_updated_at": item.get("updated_at"),
                    "raw_checksum": raw_checksum,
                    "markdown_uri": f"gs://{bucket_names['markdown']}/{output_filename}",
                    "markdown_size_bytes": len(chunk_markdown.encode('utf-8')),
                    "normalize_status": "complete",
                    "embedding_status": "pending",
                    "content_hash": chunk.content_hash,
                    "chunk_tokens": chunk.token_count,
                    "chunk_boundaries": {
                        "start": chunk.char_start,
                        "end": chunk.char_end
                    },
                    "parent_metadata": {
                        "title": chunk.frontmatter.get("title", ""),
                        "author": chunk.frontmatter.get("author", ""),
                        "source": chunk.frontmatter.get("source", "")
                    },
                    "last_transition_at": firestore.SERVER_TIMESTAMP,
                    "last_error": None,
                    "retry_count": 0,
                    "max_retries": 3,
                    "manifest_run_id": run_id,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP
                }, merge=True)

                logger.info(f"Processed chunk {chunk_id} ({chunk.token_count} tokens)")

            # Update original document entry to mark complete
            doc_ref.set({
                "normalize_status": "complete",
                "total_chunks": len(chunks),
                "last_transition_at": firestore.SERVER_TIMESTAMP,
                "manifest_run_id": run_id
            }, merge=True)

            stats["processed"] += 1
            logger.info(f"Normalized item {item_id} → {len(chunks)} chunks")

        except Exception as exc:  # pragma: no cover - complex integration logic
            logger.error(f"Error processing item {item_id}: {exc}")
            doc_ref.set({
                "normalize_status": "failed",
                "last_error": str(exc),
                "last_transition_at": firestore.SERVER_TIMESTAMP,
                "retry_count": _increment_retry(doc_data),
                "manifest_run_id": run_id
            }, merge=True)
            stats["failed"] += 1

    return json.dumps(stats), 200


# For Cloud Functions 2nd gen
def normalize(request):
    """Cloud Functions 2nd gen entry point."""
    return normalize_handler(request)
def _raise_missing_library(name: str) -> None:
    raise ImportError(f"{name} library is required for this operation")


if not _HAS_FIRESTORE_LIB:
    firestore = SimpleNamespace(  # type: ignore[assignment]
        SERVER_TIMESTAMP=object(),
        Client=lambda *args, **kwargs: _raise_missing_library("google-cloud-firestore")
    )

if not _HAS_STORAGE_LIB:
    storage = SimpleNamespace(  # type: ignore[assignment]
        Client=lambda *args, **kwargs: _raise_missing_library("google-cloud-storage")
    )
