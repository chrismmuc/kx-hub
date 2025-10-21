import hashlib
import json
import logging
import os
import time
import requests
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from google.cloud import secretmanager, storage, pubsub_v1

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT")
PIPELINE_BUCKET = os.environ.get("PIPELINE_BUCKET")
PIPELINE_MANIFEST_PREFIX = os.environ.get("PIPELINE_MANIFEST_PREFIX", "manifests")

# Lazy initialization - clients created on first use to avoid auth errors during import
secret_client = None
storage_client = None
pubsub_publisher = None

def _get_secret_client():
    global secret_client
    if secret_client is None:
        secret_client = secretmanager.SecretManagerServiceClient()
    return secret_client

def _get_storage_client():
    global storage_client
    if storage_client is None:
        storage_client = storage.Client()
    return storage_client

def _get_pubsub_publisher():
    global pubsub_publisher
    if pubsub_publisher is None:
        pubsub_publisher = pubsub_v1.PublisherClient()
    return pubsub_publisher

# --- Configuration ---
COMPLETED_TOPIC = "daily-ingest"

# Secret names in Google Secret Manager
READWISE_API_KEY_SECRET = "readwise-api-key"

def get_raw_json_bucket():
    """Get the raw JSON bucket name based on PROJECT_ID."""
    if not PROJECT_ID:
        raise ValueError("GCP_PROJECT environment variable must be set")
    return f"{PROJECT_ID}-raw-json"


def get_pipeline_bucket():
    """Return the pipeline bucket name from environment configuration."""
    if not PIPELINE_BUCKET:
        raise ValueError("PIPELINE_BUCKET environment variable must be set")
    return PIPELINE_BUCKET


def get_manifest_blob_path(run_id: str) -> str:
    """Compute the object path for a run manifest."""
    prefix = (PIPELINE_MANIFEST_PREFIX or "manifests").strip("/")
    if prefix:
        return f"{prefix}/{run_id}.json"
    return f"{run_id}.json"


def generate_run_id() -> str:
    """Generate a deterministic run identifier: timestamp + short uuid."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{timestamp}-{uuid4().hex[:8]}"


def get_secret(secret_id, version_id="latest"):
    """Retrieve a secret from Google Secret Manager."""
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    client = _get_secret_client()
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def get_last_run_timestamp():
    """Placeholder to get the last successful run timestamp. 
       In a real implementation, this would read from Firestore or a state file."""
    # For now, fetch highlights from the last 24 hours.
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def fetch_readwise_highlights(api_key, last_fetch_date, max_retries=3, timeout=30):
    """Fetch all new books/highlights from Readwise since the last fetch date.

    Args:
        api_key: Readwise API token
        last_fetch_date: ISO timestamp to fetch updates since
        max_retries: Maximum retry attempts for rate limiting
        timeout: Request timeout in seconds

    Returns:
        List of book objects, each containing nested highlights
    """
    logger.info(f"Fetching Readwise books since {last_fetch_date}")
    headers = {"Authorization": f"Token {api_key}"}
    full_data = []
    next_page_cursor = None

    while True:
        params = {
            "updated__gt": last_fetch_date
        }
        if next_page_cursor:
            params["pageCursor"] = next_page_cursor

        # Retry logic for rate limiting
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url="https://readwise.io/api/v2/export/",
                    headers=headers,
                    params=params,
                    timeout=timeout
                )

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited. Retrying after {retry_after}s (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(retry_after)
                        continue
                    else:
                        response.raise_for_status()

                response.raise_for_status()
                data = response.json()

                # Validate response structure
                if "results" not in data:
                    raise ValueError(f"Unexpected API response structure: {data.keys()}")

                full_data.extend(data["results"])
                next_page_cursor = data.get("nextPageCursor")
                break  # Success, exit retry loop

            except requests.exceptions.Timeout:
                logger.error(f"Request timeout (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e} (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff

        if not next_page_cursor:
            break

    logger.info(f"Fetched {len(full_data)} books from Readwise")
    return full_data

def store_raw_json(bucket_name, file_name, json_payload):
    """Store data as a JSON file in Google Cloud Storage."""
    client = _get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    blob.upload_from_string(
        data=json_payload,
        content_type="application/json"
    )
    logger.info(f"Successfully uploaded {file_name} to {bucket_name}")

def write_manifest(bucket_name: str, blob_path: str, manifest: dict) -> None:
    """Persist the manifest JSON to Cloud Storage."""
    client = _get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(
        data=json.dumps(manifest, indent=2),
        content_type="application/json"
    )
    logger.info(f"Stored manifest {blob_path} in bucket {bucket_name}")


def publish_completion_message(topic_name, message_dict):
    """Publish a message to a Pub/Sub topic."""
    publisher = _get_pubsub_publisher()
    topic_path = publisher.topic_path(PROJECT_ID, topic_name)
    payload = json.dumps(message_dict).encode("utf-8")
    future = publisher.publish(topic_path, payload)
    logger.info(f"Published message to {topic_path}")

def handler(event, context):
    """Main Cloud Function entry point."""
    logger.info("Ingest function triggered")

    # Validate required environment variables
    if not PROJECT_ID:
        raise ValueError("GCP_PROJECT environment variable must be set")

    try:
        # 1. Get secrets
        readwise_api_key = get_secret(READWISE_API_KEY_SECRET)

        # 2. Get last run timestamp
        last_run = get_last_run_timestamp()

        # 3. Fetch data from Readwise
        # Note: Reader API would be a separate function call here
        books = fetch_readwise_highlights(readwise_api_key, last_run)

        # 4. Store each book (with nested highlights) in GCS + build manifest
        raw_bucket = get_raw_json_bucket()
        pipeline_bucket = get_pipeline_bucket()
        run_id = generate_run_id()
        manifest_items = []
        count = 0

        for book in books:
            # Validate book structure
            if "user_book_id" not in book:
                logger.warning(f"Skipping book without user_book_id: {book.keys()}")
                continue

            book_id = book["user_book_id"]
            file_name = f"readwise-book-{book_id}.json"
            raw_json_payload = json.dumps(book, indent=2, sort_keys=True)
            raw_checksum = hashlib.sha256(raw_json_payload.encode("utf-8")).hexdigest()

            store_raw_json(raw_bucket, file_name, raw_json_payload)
            count += 1

            manifest_items.append({
                "id": str(book_id),
                "raw_uri": f"gs://{raw_bucket}/{file_name}",
                "updated_at": book.get("updated"),
                "raw_checksum": f"sha256:{raw_checksum}"
            })

        manifest_blob_path = get_manifest_blob_path(run_id)
        manifest_payload = {
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "item_count": count,
            "items": manifest_items
        }
        write_manifest(pipeline_bucket, manifest_blob_path, manifest_payload)

        # 5. Publish completion message with run metadata
        completion_message = {
            "run_id": run_id,
            "item_count": count,
            "manifest_uri": f"gs://{pipeline_bucket}/{manifest_blob_path}"
        }
        publish_completion_message(COMPLETED_TOPIC, completion_message)

        logger.info(f"Ingest function completed successfully - {count} books processed")
        return "OK"

    except Exception as e:
        logger.error(f"Error in ingest function: {e}", exc_info=True)
        # Re-raise to trigger Cloud Function retries
        raise
