"""
Nightly Auto-Snippets Cloud Function (Epic 13, Story 13.4).

Processes Reader articles tagged 'kx-auto-ingest':
1. Fetches tagged documents from Readwise Reader API
2. Checks idempotency (skip already-processed documents)
3. Runs snippet extraction + embedding pipeline (Story 13.2/13.3)
4. Updates Reader tags: removes ingest tag, adds processed tag
5. Stores job report in Firestore batch_jobs
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore, secretmanager

try:
    from src.ingest.reader_client import ReadwiseReaderClient
except ImportError:
    try:
        from ingest.reader_client import ReadwiseReaderClient
    except ImportError:
        from reader_client import ReadwiseReaderClient

try:
    from src.ingest.readwise_writer import process_document
except ImportError:
    try:
        from ingest.readwise_writer import process_document
    except ImportError:
        from readwise_writer import process_document

logger = logging.getLogger(__name__)

# Environment variables
PROJECT_ID = os.environ.get("GCP_PROJECT")

# Lazy-init clients
_firestore_client = None
_secret_client = None


def get_firestore_client():
    """Get cached Firestore client."""
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=PROJECT_ID)
    return _firestore_client


def get_secret(secret_id: str) -> str:
    """Fetch secret from Secret Manager."""
    global _secret_client
    if _secret_client is None:
        _secret_client = secretmanager.SecretManagerServiceClient()

    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
    response = _secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def load_config(db: firestore.Client) -> Dict[str, Any]:
    """
    Load config from Firestore config/auto_snippets.

    Returns:
        Merged config with defaults
    """
    defaults = {
        "enabled": True,
        "tag": "kx-auto-ingest",
        "processed_tag": "kx-processed",
        "write_to_readwise": True,
        "max_documents_per_run": 20,
    }

    doc = db.collection("config").document("auto_snippets").get()
    if doc.exists:
        return {**defaults, **doc.to_dict()}
    return defaults


def is_already_processed(db: firestore.Client, document_id: str) -> bool:
    """
    Check if a document has already been processed (idempotency).

    Checks for existence of kb_items/auto_snippet_{doc_id}_0 — the first
    chunk created by embed_snippets(). O(1) Firestore read.

    Args:
        db: Firestore client
        document_id: Reader document ID

    Returns:
        True if already processed
    """
    chunk_id = f"auto_snippet_{document_id}_0"
    doc = db.collection("kb_items").document(chunk_id).get()
    return doc.exists


def update_tags(
    reader: ReadwiseReaderClient,
    document_id: str,
    current_tags: List[str],
    remove_tag: str,
    add_tag: str,
) -> bool:
    """
    Update Reader document tags after successful processing.

    Args:
        reader: Reader API client
        document_id: Reader document ID
        current_tags: Current tag list
        remove_tag: Tag to remove (e.g., 'kx-auto-ingest')
        add_tag: Tag to add (e.g., 'kx-processed')

    Returns:
        True if successful
    """
    try:
        reader.update_document_tags(
            document_id=document_id,
            current_tags=current_tags,
            remove_tags=[remove_tag],
            add_tags=[add_tag],
        )
        return True
    except Exception as e:
        logger.error(f"Failed to update tags for {document_id}: {e}")
        return False


def store_job_report(
    db: firestore.Client,
    config: Dict[str, Any],
    status: str,
    metrics: Dict[str, Any],
    processed: List[str],
    skipped: List[str],
    failed: List[str],
    error: Optional[str] = None,
    execution_time: float = 0,
) -> str:
    """
    Store job execution report in Firestore batch_jobs collection.

    Returns:
        Job document ID
    """
    report = {
        "timestamp": datetime.now(timezone.utc),
        "job_type": "auto_snippets",
        "status": status,
        "config": config,
        "metrics": metrics,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "error": error,
        "execution_time_seconds": execution_time,
    }

    doc_ref = db.collection("batch_jobs").add(report)
    job_id = doc_ref[1].id

    logger.info(f"Stored auto_snippets job report: {job_id}")
    return job_id


def auto_snippets(event, context):
    """
    Cloud Function entry point (Pub/Sub trigger).

    Processes Reader articles tagged for auto-ingestion:
    1. Load config from Firestore
    2. Fetch tagged documents from Reader API
    3. For each document (up to max_documents_per_run):
       a. Check idempotency (skip if already processed)
       b. Run process_document pipeline
       c. On success with snippets: update tags
       d. On failure: retain tags for retry next night
    4. Store job report

    Args:
        event: Pub/Sub event data
        context: Cloud Functions context
    """
    start_time = time.time()
    db = get_firestore_client()

    try:
        # 1. Load config
        config = load_config(db)
        if not config.get("enabled"):
            logger.info("Auto-snippets disabled in config")
            return

        tag = config["tag"]
        processed_tag = config["processed_tag"]
        write_to_readwise = config["write_to_readwise"]
        max_docs = config["max_documents_per_run"]

        logger.info(f"Starting auto-snippets with config: {config}")

        # 2. Get API key and fetch tagged documents
        api_key = get_secret("readwise-api-key")
        reader = ReadwiseReaderClient(api_key)

        # Fetch all categories (articles, PDFs, etc.) with withHtmlContent=true
        raw_documents = reader.fetch_tagged_documents(tag=tag, category="")

        logger.info(f"Found {len(raw_documents)} documents tagged '{tag}'")

        # 3. Process each document
        processed_list = []
        skipped_list = []
        failed_list = []
        total_snippets = 0
        total_embedded = 0

        for raw_doc in raw_documents[:max_docs]:
            doc_id = raw_doc.get("id", "unknown")
            doc_title = raw_doc.get("title", "Untitled")

            # 3a. Idempotency check
            if is_already_processed(db, doc_id):
                logger.info(f"Skipping already-processed document: {doc_title}")
                skipped_list.append(doc_id)
                continue

            # 3b. Extract content and run pipeline
            try:
                reader_doc = reader.extract_document_content(raw_doc)
                result = process_document(
                    reader_doc,
                    api_key=api_key,
                    write_to_readwise=write_to_readwise,
                )

                snippets_count = result.get("snippets_extracted", 0)
                embedded_count = result.get("chunks_embedded", 0)
                total_snippets += snippets_count
                total_embedded += embedded_count

                # 3c. Update tags on success with snippets
                if snippets_count > 0:
                    current_tags = raw_doc.get("tags", [])
                    update_tags(reader, doc_id, current_tags, tag, processed_tag)
                    processed_list.append(doc_id)
                    logger.info(
                        f"Processed '{doc_title}': "
                        f"{snippets_count} snippets, {embedded_count} embedded"
                    )
                else:
                    # No snippets extracted — skip tag update, count as skipped
                    skipped_list.append(doc_id)
                    logger.info(f"No snippets for '{doc_title}', skipping tag update")

            except Exception as e:
                # 3d. Failure — retain tags for retry
                logger.error(f"Failed to process '{doc_title}': {e}")
                failed_list.append(doc_id)

        # 4. Store job report
        execution_time = time.time() - start_time
        metrics = {
            "documents_found": len(raw_documents),
            "documents_processed": len(processed_list),
            "documents_skipped": len(skipped_list),
            "documents_failed": len(failed_list),
            "total_snippets": total_snippets,
            "total_embedded": total_embedded,
        }

        report_id = store_job_report(
            db=db,
            config=config,
            status="success",
            metrics=metrics,
            processed=processed_list,
            skipped=skipped_list,
            failed=failed_list,
            execution_time=execution_time,
        )

        logger.info(
            f"Auto-snippets complete: {len(processed_list)} processed, "
            f"{len(skipped_list)} skipped, {len(failed_list)} failed "
            f"(report: {report_id}, time: {execution_time:.1f}s)"
        )

    except Exception as e:
        logger.error(f"Auto-snippets job failed: {e}", exc_info=True)

        execution_time = time.time() - start_time
        store_job_report(
            db=db,
            config={},
            status="failed",
            metrics={},
            processed=[],
            skipped=[],
            failed=[],
            error=str(e),
            execution_time=execution_time,
        )

        raise  # Re-raise for Cloud Functions retry
