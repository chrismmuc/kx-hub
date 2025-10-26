"""
Cloud Function to embed markdown files and store to Vertex AI Vector Search + Firestore.

Story 1.3: Embed & Store to Vertex AI Vector Search + Firestore

This function:
1. Reads markdown files from Cloud Storage (markdown-normalized bucket)
2. Parses YAML frontmatter to extract metadata
3. Generates embeddings using Vertex AI gemini-embedding-001 model
4. Stores embeddings in Vertex AI Vector Search index
5. Stores metadata in Firestore kb_items collection
"""

import hashlib
import json
import logging
import time
import yaml
import os
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from google.api_core.exceptions import GoogleAPICallError, InternalServerError, NotFound, ResourceExhausted

_HAS_STORAGE_LIB = True
_HAS_FIRESTORE_LIB = True
_HAS_AIPLATFORM_LIB = True
_HAS_VERTEX_LIB = True
_HAS_MATCHING_ENGINE_LIB = True

try:
    from google.cloud import storage, firestore, aiplatform
except ImportError:  # pragma: no cover - allows tests to run without deps
    _HAS_STORAGE_LIB = False
    _HAS_FIRESTORE_LIB = False
    _HAS_AIPLATFORM_LIB = False
    storage = None  # type: ignore[assignment]
    firestore = None  # type: ignore[assignment]
    aiplatform = None  # type: ignore[assignment]

try:
    from vertexai.preview.language_models import TextEmbeddingModel
except ImportError:  # pragma: no cover - allows tests to run without deps
    _HAS_VERTEX_LIB = False
    TextEmbeddingModel = None  # type: ignore[assignment]

try:
    from google.cloud.aiplatform_v1.types import IndexDatapoint, UpsertDatapointsRequest
    from google.cloud.aiplatform_v1 import MatchingEngineIndexEndpointServiceClient
except ImportError:  # pragma: no cover - allows tests to run without deps
    _HAS_MATCHING_ENGINE_LIB = False
    IndexDatapoint = None  # type: ignore[assignment]
    UpsertDatapointsRequest = None  # type: ignore[assignment]
    MatchingEngineIndexEndpointServiceClient = None  # type: ignore[assignment]

try:
    from google.cloud.firestore_v1 import Increment
except ImportError:  # pragma: no cover - allows tests to run without deps
    Increment = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover
    from google.cloud import storage as storage_mod
    from google.cloud import firestore as firestore_mod
    from google.cloud import aiplatform as aiplatform_mod
    from vertexai.preview.language_models import TextEmbeddingModel as TextEmbeddingModelType
    from google.cloud.aiplatform_v1 import MatchingEngineIndexEndpointServiceClient

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Provide lightweight fallbacks when optional dependencies aren't available during tests.
def _raise_missing_library(name: str) -> None:
    raise ImportError(f"{name} library is required for this operation")


if not _HAS_FIRESTORE_LIB:
    firestore = SimpleNamespace(  # type: ignore[assignment]
        SERVER_TIMESTAMP=object(),
        Client=lambda *args, **kwargs: _raise_missing_library("google-cloud-firestore")
    )

if not _HAS_AIPLATFORM_LIB:
    aiplatform = SimpleNamespace(  # type: ignore[assignment]
        MatchingEngineIndexEndpoint=lambda *args, **kwargs: _raise_missing_library("google-cloud-aiplatform")
    )

# Global GCP clients (lazy initialization)
_storage_client = None
_firestore_client = None
_vertex_ai_model = None
_index_endpoint_client = None

# Configuration
GCP_PROJECT = os.environ.get('GCP_PROJECT', 'kx-hub')
GCP_REGION = os.environ.get('GCP_REGION', 'europe-west4')
VECTOR_SEARCH_INDEX_ENDPOINT = os.environ.get('VECTOR_SEARCH_INDEX_ENDPOINT')
VECTOR_SEARCH_DEPLOYED_INDEX_ID = os.environ.get('VECTOR_SEARCH_DEPLOYED_INDEX_ID')
MARKDOWN_BUCKET = os.environ.get('MARKDOWN_BUCKET', f'{GCP_PROJECT}-markdown-normalized')
PIPELINE_BUCKET = os.environ.get('PIPELINE_BUCKET')
PIPELINE_COLLECTION = os.environ.get('PIPELINE_COLLECTION', 'pipeline_items')
PIPELINE_MANIFEST_PREFIX = os.environ.get('PIPELINE_MANIFEST_PREFIX', 'manifests')
try:
    EMBED_STALE_TIMEOUT_SECONDS = int(os.environ.get('EMBED_STALE_TIMEOUT_SECONDS', '900'))
except ValueError:
    EMBED_STALE_TIMEOUT_SECONDS = 900
STALE_PROCESSING_DELTA = timedelta(seconds=EMBED_STALE_TIMEOUT_SECONDS)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 30.0  # seconds


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp string to datetime, tolerate trailing Z."""
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        logger.warning(f"Unable to parse datetime value: {value}")
        return None


def get_storage_client():
    """Lazy initialization of Cloud Storage client."""
    global _storage_client
    if _storage_client is None:
        if storage is None:
            raise ImportError("google-cloud-storage is required to use get_storage_client")
        _storage_client = storage.Client(project=GCP_PROJECT)
        logger.info("Initialized Cloud Storage client")
    return _storage_client


def get_firestore_client():
    """Lazy initialization of Firestore client."""
    global _firestore_client
    if _firestore_client is None:
        if not _HAS_FIRESTORE_LIB:
            raise ImportError("google-cloud-firestore is required to use get_firestore_client")
        _firestore_client = firestore.Client(project=GCP_PROJECT)
        logger.info("Initialized Firestore client")
    return _firestore_client


def get_vertex_ai_client():
    """Lazy initialization of Vertex AI embedding model."""
    global _vertex_ai_model
    if _vertex_ai_model is None:
        if not (_HAS_AIPLATFORM_LIB and _HAS_VERTEX_LIB):
            raise ImportError("google-cloud-aiplatform and vertexai libraries are required for embeddings")
        aiplatform.init(project=GCP_PROJECT, location=GCP_REGION)
        _vertex_ai_model = TextEmbeddingModel.from_pretrained("gemini-embedding-001")
        logger.info("Initialized Vertex AI embedding model")
    return _vertex_ai_model


def get_index_endpoint_client():
    """Lazy initialization of Matching Engine Index Endpoint client."""
    global _index_endpoint_client
    if _index_endpoint_client is None:
        if not (_HAS_AIPLATFORM_LIB and _HAS_MATCHING_ENGINE_LIB):
            raise ImportError("google-cloud-aiplatform>=1.44 is required for Matching Engine operations")
        client_options = {"api_endpoint": f"{GCP_REGION}-aiplatform.googleapis.com"}
        if MatchingEngineIndexEndpointServiceClient is None:
            raise ImportError("google-cloud-aiplatform>=1.44 is required for Matching Engine operations")
        _index_endpoint_client = MatchingEngineIndexEndpointServiceClient(client_options=client_options)
        logger.info("Initialized Matching Engine index endpoint client")
    return _index_endpoint_client


def _index_endpoint_resource() -> str:
    if VECTOR_SEARCH_INDEX_ENDPOINT and "/" in VECTOR_SEARCH_INDEX_ENDPOINT:
        return VECTOR_SEARCH_INDEX_ENDPOINT
    if not VECTOR_SEARCH_INDEX_ENDPOINT:
        raise ValueError("VECTOR_SEARCH_INDEX_ENDPOINT environment variable not set")
    project = os.environ.get('GCP_PROJECT', GCP_PROJECT)
    return f"projects/{project}/locations/{GCP_REGION}/indexEndpoints/{VECTOR_SEARCH_INDEX_ENDPOINT}"


def get_pipeline_collection():
    """Return the Firestore collection handle for pipeline items."""
    if not PIPELINE_COLLECTION:
        raise ValueError("PIPELINE_COLLECTION environment variable not set")
    client = get_firestore_client()
    return client.collection(PIPELINE_COLLECTION)


def _get_pipeline_bucket() -> str:
    if not PIPELINE_BUCKET:
        raise ValueError("PIPELINE_BUCKET environment variable not set")
    return PIPELINE_BUCKET


def _manifest_blob_path(run_id: str) -> str:
    prefix = (PIPELINE_MANIFEST_PREFIX or "manifests").strip("/")
    if prefix:
        return f"{prefix}/{run_id}.json"
    return f"{run_id}.json"


def _load_manifest(run_id: str) -> Dict[str, Any]:
    """Load the manifest for the provided run id (raises if missing)."""
    if not _HAS_STORAGE_LIB:
        raise ImportError("google-cloud-storage is required to load manifests")
    client = get_storage_client()
    bucket = client.bucket(_get_pipeline_bucket())
    blob_path = _manifest_blob_path(run_id)
    blob = bucket.blob(blob_path)
    manifest_text = blob.download_as_text()  # May raise NotFound
    manifest = json.loads(manifest_text)
    if not isinstance(manifest, dict) or manifest.get("run_id") != run_id:
        raise ValueError(f"Invalid manifest structure for run_id {run_id}")
    return manifest


def _parse_gcs_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"Unsupported GCS URI: {uri}")
    without_scheme = uri[5:]
    if "/" not in without_scheme:
        raise ValueError(f"Unsupported GCS URI: {uri}")
    bucket, path = without_scheme.split("/", 1)
    return bucket, path


def _compute_markdown_hash(markdown: str) -> str:
    return f"sha256:{hashlib.sha256(markdown.encode('utf-8')).hexdigest()}"


def _increment_retry(existing: Dict[str, Any]) -> Any:
    if Increment is not None:
        return Increment(1)
    return existing.get("retry_count", 0) + 1


def parse_markdown(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter and content from markdown file.

    Args:
        content: Raw markdown file content with frontmatter

    Returns:
        Tuple of (metadata dict, markdown content)

    Raises:
        ValueError: If frontmatter is malformed or missing required fields
    """
    if not content.startswith('---'):
        raise ValueError("No frontmatter found (must start with '---')")

    parts = content.split('---', 2)
    if len(parts) < 3:
        raise ValueError("Malformed frontmatter (missing closing '---')")

    try:
        metadata = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}")

    # Validate required fields
    required_fields = ['id', 'title', 'author', 'created_at', 'updated_at']
    for field in required_fields:
        if field not in metadata:
            raise ValueError(f"Missing required field in frontmatter: {field}")

    # Normalize optional fields
    if 'url' not in metadata:
        metadata['url'] = None
    if 'tags' not in metadata:
        metadata['tags'] = []

    markdown_content = parts[2].strip()
    return metadata, markdown_content


def generate_embedding(text: str) -> List[float]:
    """
    Generate embedding vector using Vertex AI.

    Implements retry logic with exponential backoff for rate limiting and server errors.

    Args:
        text: Text content to embed

    Returns:
        List of 768 floats representing the embedding vector

    Raises:
        ResourceExhausted: After max retries for rate limiting
        InternalServerError: After max retries for server errors
    """
    model = get_vertex_ai_client()
    backoff = INITIAL_BACKOFF

    for attempt in range(MAX_RETRIES):
        try:
            embeddings = model.get_embeddings([text])
            embedding_vector = embeddings[0].values
            logger.debug(f"Generated embedding with {len(embedding_vector)} dimensions")
            return embedding_vector

        except ResourceExhausted as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Rate limit exceeded (attempt {attempt + 1}/{MAX_RETRIES}), retrying after {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
            else:
                logger.error(f"Rate limit exceeded after {MAX_RETRIES} attempts")
                raise

        except InternalServerError as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Server error (attempt {attempt + 1}/{MAX_RETRIES}), retrying after {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
            else:
                logger.error(f"Server error after {MAX_RETRIES} attempts")
                raise

        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {e}")
            raise


def upsert_to_vector_search(item_id: str, embedding_vector: List[float], run_id: Optional[str] = None) -> bool:
    """
    Upsert a single datapoint to Vector Search index.

    Args:
        item_id: Unique identifier for the datapoint
        embedding_vector: 768-dimensional embedding vector
        run_id: Current pipeline run identifier (used as crowding tag for observability)

    Returns:
        True if successful, False if error occurred
    """
    try:
        client = get_index_endpoint_client()
        if not VECTOR_SEARCH_DEPLOYED_INDEX_ID:
            raise ValueError("Vector Search environment variables are not configured")
        index_endpoint_resource = _index_endpoint_resource()

        datapoint = IndexDatapoint(
            datapoint_id=item_id,
            feature_vector=embedding_vector,
        )
        if run_id:
            datapoint.crowding_tag = run_id

        request = UpsertDatapointsRequest(
            index_endpoint=index_endpoint_resource,
            deployed_index_id=VECTOR_SEARCH_DEPLOYED_INDEX_ID,
            datapoints=[datapoint],
        )

        client.upsert_datapoints(request=request)
        logger.info(f"Upserted datapoint {item_id} to Vector Search")
        return True

    except (GoogleAPICallError, ValueError) as e:
        logger.error(f"Failed to upsert datapoint {item_id} to Vector Search: {e}")
        return False


def upsert_batch_to_vector_search(batch: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Batch upsert datapoints to Vector Search index (up to 100 datapoints per batch).

    Args:
        batch: List of dicts with 'id' and 'embedding' keys

    Returns:
        Dict with 'success' and 'failed' counts
    """
    try:
        client = get_index_endpoint_client()
        if not VECTOR_SEARCH_DEPLOYED_INDEX_ID:
            raise ValueError("Vector Search environment variables are not configured")
        index_endpoint_resource = _index_endpoint_resource()

        datapoints = []
        for item in batch:
            dp = IndexDatapoint(
                datapoint_id=item['id'],
                feature_vector=item['embedding'],
            )
            run_id = item.get('run_id')
            if run_id:
                dp.crowding_tag = run_id
            datapoints.append(dp)

        request = UpsertDatapointsRequest(
            index_endpoint=index_endpoint_resource,
            deployed_index_id=VECTOR_SEARCH_DEPLOYED_INDEX_ID,
            datapoints=datapoints,
        )
        client.upsert_datapoints(request=request)

        logger.info(f"Batch upserted {len(datapoints)} datapoints to Vector Search")
        return {'success': len(datapoints), 'failed': 0}

    except (GoogleAPICallError, ValueError) as e:
        logger.error(f"Failed to batch upsert datapoints to Vector Search: {e}")
        return {'success': 0, 'failed': len(batch)}


def write_to_firestore(metadata: Dict[str, Any], content_hash: str, run_id: str, embedding_status: str) -> bool:
    """
    Write metadata document to Firestore kb_items collection.

    Args:
        metadata: Document metadata from frontmatter
        content_hash: Hash of the markdown content used for embedding
        run_id: Current pipeline run identifier
        embedding_status: Embedding status to persist with metadata

    Returns:
        True if successful, False if error occurred
    """
    try:
        db = get_firestore_client()

        created_at_value = _parse_iso_datetime(metadata.get('created_at'))
        updated_at_value = _parse_iso_datetime(metadata.get('updated_at'))

        # Prepare document data
        doc_data = {
            'title': metadata['title'],
            'url': metadata.get('url'),
            'tags': metadata.get('tags', []),
            'authors': [metadata['author']],  # Convert single author to list
            'created_at': created_at_value if created_at_value else getattr(firestore, "SERVER_TIMESTAMP", None),
            'updated_at': updated_at_value if updated_at_value else getattr(firestore, "SERVER_TIMESTAMP", None),
            'content_hash': content_hash,
            'embedding_status': embedding_status,
            'last_embedded_at': getattr(firestore, "SERVER_TIMESTAMP", None),
            'last_error': None,
            'last_run_id': run_id,
            'cluster_id': [],  # Future: Story 1.5
            'similar_ids': [],  # Future: Story 1.5
            'scores': []  # Future: Story 1.5
        }

        # Write to kb_items collection with document ID = item_id
        doc_ref = db.collection('kb_items').document(metadata['id'])
        doc_ref.set(doc_data, merge=True)

        logger.info(f"Wrote document {metadata['id']} to Firestore")
        return True

    except Exception as e:
        logger.error(f"Failed to write document {metadata['id']} to Firestore: {e}")
        return False


def embed(request):
    """
    Main Cloud Function handler.

    Processes pipeline items flagged for embedding:
    1. Load manifest for provided run_id
    2. Fetch pipeline_items requiring embedding work
    3. Generate embeddings as needed and upsert to Vector Search
    4. Update Firestore metadata + pipeline state
    """
    logger.info("Embed function triggered")

    request_json = request.get_json(silent=True) or {}
    run_id = request_json.get('run_id')
    if not run_id:
        return {'status': 'error', 'message': 'run_id is required'}, 400

    # Ensure manifest exists so replays/invalid run_ids fail fast
    try:
        manifest = _load_manifest(run_id)
    except NotFound:
        message = f"Manifest not found for run_id {run_id}"
        logger.error(message)
        return {'status': 'error', 'message': message}, 404
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Failed to load manifest for run_id {run_id}: {exc}")
        return {'status': 'error', 'message': str(exc)}, 500

    try:
        storage_client = get_storage_client()
        pipeline_collection = get_pipeline_collection()
    except Exception as exc:
        logger.error(f"Failed to initialize clients: {exc}")
        return {'status': 'error', 'message': str(exc)}, 500

    try:
        candidate_snapshots = list(
            pipeline_collection.where('embedding_status', 'in', ['pending', 'failed', 'processing']).stream()
        )
    except Exception as exc:
        logger.error(f"Failed to query pipeline_items: {exc}")
        return {'status': 'error', 'message': str(exc)}, 500

    stats = {
        'status': 'success',
        'run_id': run_id,
        'manifest_items': len(manifest.get('items', [])),
        'candidates': len(candidate_snapshots),
        'processed': 0,
        'skipped': 0,
        'failed': 0,
        'vector_upserts': 0,
        'firestore_updates': 0,
        'stale_resets': 0
    }

    now = datetime.now(timezone.utc)
    stale_cutoff = now - STALE_PROCESSING_DELTA

    for snapshot in candidate_snapshots:
        doc_ref = snapshot.reference
        doc = snapshot.to_dict() or {}
        item_id = doc.get('id', snapshot.id)
        status = doc.get('embedding_status', 'pending')
        manifest_run_id = doc.get('manifest_run_id')
        last_transition = doc.get('last_transition_at')
        is_stale_processing = (
            status == 'processing'
            and isinstance(last_transition, datetime)
            and last_transition.tzinfo is not None
            and last_transition < stale_cutoff
        )

        if status == 'processing' and not is_stale_processing:
            logger.info(f"Skipping {item_id}: currently being processed by another worker")
            stats['skipped'] += 1
            continue

        if status == 'pending' and manifest_run_id not in (None, run_id):
            logger.info(f"Skipping {item_id}: pending for run {manifest_run_id}, not {run_id}")
            stats['skipped'] += 1
            continue

        if is_stale_processing:
            logger.warning(f"Detected stale processing item {item_id}; resetting to pending")
            doc_ref.set({
                'embedding_status': 'pending',
                'last_error': 'Rescheduled after stale timeout',
                'last_transition_at': getattr(firestore, "SERVER_TIMESTAMP", None),
                'retry_count': _increment_retry(doc)
            }, merge=True)
            doc['embedding_status'] = 'pending'
            stats['stale_resets'] += 1

        try:
            # Mark item as processing for this run
            doc_ref.set({
                'embedding_status': 'processing',
                'last_transition_at': getattr(firestore, "SERVER_TIMESTAMP", None),
                'embedding_run_id': run_id
            }, merge=True)

            markdown_uri = doc.get('markdown_uri')
            if not markdown_uri:
                raise ValueError("pipeline item missing markdown_uri")

            bucket_name, blob_path = _parse_gcs_uri(markdown_uri)
            markdown_blob = storage_client.bucket(bucket_name).blob(blob_path)
            markdown_full = markdown_blob.download_as_text()
            metadata, markdown_content = parse_markdown(markdown_full)

            computed_hash = _compute_markdown_hash(markdown_full)
            declared_hash = doc.get('content_hash')
            if declared_hash != computed_hash:
                logger.info(f"Content hash updated for {item_id}: {declared_hash} → {computed_hash}")
                doc_ref.set({
                    'content_hash': computed_hash,
                    'manifest_run_id': run_id
                }, merge=True)

            previous_embedded_hash = doc.get('embedded_content_hash')
            needs_upsert = previous_embedded_hash != computed_hash

            text_to_embed = f"{metadata['title']}\n{metadata['author']}"
            if markdown_content.strip():
                text_to_embed = f"{text_to_embed}\n{markdown_content}"

            if needs_upsert:
                embedding_vector = generate_embedding(text_to_embed)
                if not upsert_to_vector_search(metadata['id'], embedding_vector, run_id=run_id):
                    raise RuntimeError("Vector Search upsert failed")
                stats['vector_upserts'] += 1

                if not write_to_firestore(metadata, computed_hash, run_id, "complete"):
                    raise RuntimeError("Failed to update kb_items metadata")
                stats['firestore_updates'] += 1
            else:
                logger.info(f"Skipping Vector Search upsert for {item_id}; content hash unchanged")

            success_update = {
                'embedding_status': 'complete',
                'embedded_content_hash': computed_hash,
                'content_hash': computed_hash,
                'last_transition_at': getattr(firestore, "SERVER_TIMESTAMP", None),
                'last_error': None,
                'retry_count': 0,
                'manifest_run_id': run_id,
                'embedding_run_id': run_id
            }
            if needs_upsert:
                success_update['last_embedded_at'] = getattr(firestore, "SERVER_TIMESTAMP", None)

            doc_ref.set(success_update, merge=True)
            stats['processed'] += 1

        except Exception as exc:  # pragma: no cover - integration heavy
            logger.error(f"Error embedding item {item_id}: {exc}")
            failure_update = {
                'embedding_status': 'failed',
                'last_error': str(exc),
                'last_transition_at': getattr(firestore, "SERVER_TIMESTAMP", None),
                'retry_count': _increment_retry(doc),
                'manifest_run_id': run_id
            }
            doc_ref.set(failure_update, merge=True)
            stats['failed'] += 1

    logger.info(f"Embed processing complete: {stats}")
    return stats, 200


# For local testing
if __name__ == '__main__':
    class MockRequest:
        def get_json(self, silent=False):
            return {'bucket': 'kx-hub-markdown-normalized'}

    result = embed(MockRequest())
    print(result)
