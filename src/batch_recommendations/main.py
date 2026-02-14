"""
Batch Recommendations Cloud Function (Epic 12).

Executes weekly recommendations batch:
1. Calls MCP Server /recommendations HTTP endpoint
2. Polls for completion
3. Filters results (max 3, recency)
4. Deduplicates with Reader library
5. Saves to Readwise Reader with auto-tags
6. Tracks execution in Firestore
"""

import os
import time
import logging
import requests
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

from google.cloud import firestore, secretmanager
from reader_client import ReadwiseReaderClient

logger = logging.getLogger(__name__)

# Environment variables
PROJECT_ID = os.environ.get("GCP_PROJECT")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL")  # From config or env

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


def load_batch_config() -> Dict[str, Any]:
    """Load config from Firestore config/batch_recommendations."""
    db = get_firestore_client()
    doc = db.collection("config").document("batch_recommendations").get()

    defaults = {
        "enabled": True,
        "mode": "balanced",
        "max_results": 3,
        "recency_days": 7,
        "auto_tags": ["ai-recommended"],
        "tavily_days": 30,
    }

    if doc.exists:
        return {**defaults, **doc.to_dict()}
    return defaults


def start_recommendations_job(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call MCP Server /recommendations HTTP endpoint to start async job.

    Returns:
        Job metadata with job_id and poll_after_seconds
    """
    mcp_url = config.get("mcp_server_url") or MCP_SERVER_URL
    if not mcp_url:
        raise ValueError("MCP_SERVER_URL not configured in Firestore or environment")

    # Call MCP endpoint: /recommendations to start new job
    payload = {
        "mode": config["mode"],
        "problems": None,  # Use all active problems
    }

    logger.info(
        f"Starting recommendations job via MCP Server: {mcp_url}/recommendations"
    )

    response = requests.post(
        f"{mcp_url}/recommendations",
        json=payload,
        timeout=120,  # Allow time for cold start
    )
    response.raise_for_status()

    job_data = response.json()
    logger.info(f"Started recommendations job: {job_data.get('job_id')}")
    return job_data


def poll_job_until_complete(
    job_id: str, config: Dict[str, Any], timeout: int = 300
) -> Dict[str, Any]:
    """
    Poll MCP Server /recommendations endpoint for job completion.

    Args:
        job_id: Recommendations job ID
        config: Batch config with mcp_server_url
        timeout: Max wait time in seconds (default 5 min)

    Returns:
        Job result when completed

    Raises:
        TimeoutError: If job doesn't complete within timeout
        RuntimeError: If job fails
    """
    mcp_url = config.get("mcp_server_url") or MCP_SERVER_URL
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

        # Poll job status via MCP endpoint
        response = requests.post(
            f"{mcp_url}/recommendations",
            json={"job_id": job_id},
            timeout=120,  # Allow time for cold start
        )
        response.raise_for_status()

        job_status = response.json()
        status = job_status.get("status")

        if status == "completed":
            logger.info(f"Job {job_id} completed successfully")
            return job_status.get("result", {})
        elif status == "failed":
            error = job_status.get("error", "Unknown error")
            raise RuntimeError(f"Job {job_id} failed: {error}")
        elif status in ["pending", "running"]:
            wait_time = job_status.get("poll_after_seconds", 5)
            logger.info(f"Job {job_id} still {status}, waiting {wait_time}s")
            time.sleep(wait_time)
        else:
            raise RuntimeError(f"Unknown job status: {status}")


def filter_by_recency_and_count(
    recommendations: List[Dict[str, Any]],
    max_results: int,
    recency_days: int,
) -> List[Dict[str, Any]]:
    """
    Filter recommendations by recency and limit count.

    Args:
        recommendations: Full list from MCP Server
        max_results: Max items to return
        recency_days: Only include items published within last N days (0 = no filter)

    Returns:
        Filtered and limited recommendations
    """
    # If recency_days is 0 or negative, skip recency filtering
    if recency_days <= 0:
        logger.info(f"Recency filter disabled (recency_days={recency_days})")
        sorted_recs = sorted(
            recommendations, key=lambda x: x.get("final_score", 0), reverse=True
        )
        filtered = sorted_recs[:max_results]
        logger.info(f"Filtered {len(recommendations)} → {len(filtered)} final (no recency filter)")
        return filtered

    cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)

    # Filter by recency
    recent = []
    for rec in recommendations:
        pub_date_str = rec.get("published_date")
        if not pub_date_str:
            logger.debug(f"Skipping {rec.get('url')} - no published_date")
            continue

        # Parse date (format: "2026-01-15" or ISO timestamp)
        try:
            if "T" in pub_date_str:
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            else:
                pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )

            if pub_date > cutoff:
                recent.append(rec)
            else:
                logger.debug(
                    f"Filtered out {rec.get('url')} - published {pub_date_str}"
                )
        except Exception as e:
            logger.warning(f"Failed to parse date {pub_date_str}: {e}")

    # Sort by final_score (already ranked by MCP Server)
    recent_sorted = sorted(recent, key=lambda x: x.get("final_score", 0), reverse=True)

    # Limit count
    filtered = recent_sorted[:max_results]

    logger.info(
        f"Filtered {len(recommendations)} → {len(recent)} recent → {len(filtered)} final"
    )
    return filtered


def dedup_with_reader(
    recommendations: List[Dict[str, Any]],
    reader_client: ReadwiseReaderClient,
) -> List[Dict[str, Any]]:
    """
    Remove URLs already in Readwise Reader library.

    Args:
        recommendations: Filtered recommendations
        reader_client: Readwise Reader API client

    Returns:
        Deduplicated recommendations
    """
    try:
        # Fetch all Reader documents
        reader_docs = reader_client.list_documents(limit=100)

        # Extract existing URLs (normalize: remove trailing slash)
        existing_urls = {doc.get("url", "").rstrip("/").lower() for doc in reader_docs}

        logger.info(f"Checking against {len(existing_urls)} existing Reader documents")

        # Filter out duplicates
        deduplicated = [
            rec
            for rec in recommendations
            if rec.get("url", "").rstrip("/").lower() not in existing_urls
        ]

        removed = len(recommendations) - len(deduplicated)
        if removed > 0:
            logger.info(f"Removed {removed} duplicates already in Reader")

        return deduplicated

    except Exception as e:
        logger.warning(f"Dedup check failed: {e}, proceeding without dedup")
        return recommendations  # Fail gracefully


def build_tags(rec: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
    """
    Build tag list for Reader save.

    Tags: auto_tags + domain + topic tags (max 2)

    Args:
        rec: Recommendation dict with domain, tags
        config: Batch config with auto_tags

    Returns:
        Deduplicated list of tags
    """
    tags = list(config.get("auto_tags", []))

    # Add domain (e.g., "techcrunch.com")
    if rec.get("domain"):
        tags.append(rec["domain"])

    # Add topic tags (max 2)
    if rec.get("tags"):
        tags.extend(rec["tags"][:2])

    return list(set(tags))  # Deduplicate


def save_to_reader_with_retry(
    url: str,
    tags: List[str],
    title: str,
    reader_client: ReadwiseReaderClient,
    max_retries: int = 3,
) -> Optional[Dict[str, Any]]:
    """
    Save article to Reader with exponential backoff retry.

    Args:
        url: Article URL
        tags: Tag list
        title: Article title
        reader_client: Reader API client
        max_retries: Max retry attempts

    Returns:
        Saved document metadata or None if failed/duplicate

    Raises:
        Exception: If all retries fail
    """
    for attempt in range(max_retries):
        try:
            return reader_client.save_url(url, tags, title)
        except requests.HTTPError as e:
            if e.response.status_code == 429:  # Rate limited
                wait_time = 2**attempt
                logger.warning(f"Rate limited, waiting {wait_time}s")
                time.sleep(wait_time)
            elif e.response.status_code == 409:  # Conflict (duplicate)
                logger.info(f"URL already saved: {url}")
                return None
            else:
                raise

    raise Exception(f"Failed to save {url} after {max_retries} retries")


def store_batch_job_report(
    db: firestore.Client,
    config: Dict[str, Any],
    metrics: Dict[str, Any],
    saved_items: List[Dict[str, Any]],
    status: str,
    error: Optional[str] = None,
    execution_time: float = 0,
) -> str:
    """
    Store batch execution report in Firestore batch_jobs collection.

    Returns:
        Job document ID
    """
    report = {
        "timestamp": datetime.now(timezone.utc),
        "status": status,
        "config": config,
        "metrics": metrics,
        "saved_items": saved_items,
        "error": error,
        "execution_time_seconds": execution_time,
    }

    doc_ref = db.collection("batch_jobs").add(report)
    job_id = doc_ref[1].id

    logger.info(f"Stored batch job report: {job_id}")
    return job_id


def batch_recommendations(event, context):
    """
    Cloud Function entry point (Pub/Sub trigger).

    Args:
        event: Pub/Sub event data
        context: Cloud Functions context

    Returns:
        None (logs success/failure)
    """
    start_time = time.time()
    db = get_firestore_client()

    try:
        # 1. Load config
        config = load_batch_config()
        if not config.get("enabled"):
            logger.info("Batch recommendations disabled in config")
            return

        logger.info(f"Starting batch with config: {config}")

        # 2. Start recommendations job (call MCP Server)
        job = start_recommendations_job(config)
        job_id = job.get("job_id")

        if not job_id:
            raise ValueError("No job_id returned from MCP Server")

        # 3. Poll until completed
        result = poll_job_until_complete(job_id, config, timeout=300)
        all_recommendations = result.get("recommendations", [])

        logger.info(f"Received {len(all_recommendations)} recommendations from job")

        # 4. Filter by recency and count
        filtered = filter_by_recency_and_count(
            all_recommendations,
            max_results=config["max_results"],
            recency_days=config["recency_days"],
        )

        # 5. Dedup with Reader library
        reader_client = ReadwiseReaderClient(get_secret("readwise-api-key"))
        deduplicated = dedup_with_reader(filtered, reader_client)

        # 6. Save to Reader with auto-tags
        saved_items = []
        for rec in deduplicated:
            try:
                tags = build_tags(rec, config)
                saved_doc = save_to_reader_with_retry(
                    url=rec["url"],
                    tags=tags,
                    title=rec.get("title", rec["url"]),
                    reader_client=reader_client,
                )

                if saved_doc:
                    saved_items.append(
                        {
                            "url": rec["url"],
                            "title": rec.get("title", rec["url"]),
                            "tags": tags,
                            "reader_id": saved_doc.get("id"),
                        }
                    )
            except Exception as e:
                logger.error(f"Failed to save {rec.get('url')}: {e}")

        # 7. Track execution
        execution_time = time.time() - start_time
        metrics = {
            "original_count": len(all_recommendations),
            "filtered_count": len(filtered),
            "deduplicated_count": len(deduplicated),
            "saved_count": len(saved_items),
        }

        report_id = store_batch_job_report(
            db=db,
            config=config,
            metrics=metrics,
            saved_items=saved_items,
            status="success",
            execution_time=execution_time,
        )

        logger.info(
            f"Batch complete: {len(saved_items)} articles saved "
            f"(report: {report_id}, time: {execution_time:.1f}s)"
        )

    except Exception as e:
        logger.error(f"Batch failed: {e}", exc_info=True)

        # Track failure
        execution_time = time.time() - start_time
        store_batch_job_report(
            db=db,
            config={},
            metrics={},
            saved_items=[],
            status="failed",
            error=str(e),
            execution_time=execution_time,
        )

        # TODO Story 12.7: Send Slack notification on failure
        raise  # Re-raise for Cloud Functions retry
