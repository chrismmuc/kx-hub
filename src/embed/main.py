"""
Cloud Function to embed markdown files and store to Firestore with vector search.

Story 1.3+: Embed & Store to Firestore Vector Search

This function:
1. Reads markdown files from Cloud Storage (markdown-normalized bucket)
2. Parses YAML frontmatter to extract metadata
3. Generates embeddings using Vertex AI gemini-embedding-001 model
4. Stores embeddings and metadata in Firestore kb_items collection with vector search support
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
    from google.cloud.firestore_v1.vector import Vector
    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
except ImportError:  # pragma: no cover - allows tests to run without deps
    _HAS_MATCHING_ENGINE_LIB = False
    Vector = None  # type: ignore[assignment]
    DistanceMeasure = None  # type: ignore[assignment]

try:
    from google.cloud.firestore_v1 import Increment
except ImportError:  # pragma: no cover - allows tests to run without deps
    Increment = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover
    from google.cloud import storage as storage_mod
    from google.cloud import firestore as firestore_mod
    from google.cloud import aiplatform as aiplatform_mod
    from vertexai.preview.language_models import TextEmbeddingModel as TextEmbeddingModelType
    from google.cloud.aiplatform_v1.services.index_service import IndexServiceClient as IndexServiceClientType

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

# Configuration
GCP_PROJECT = os.environ.get('GCP_PROJECT', 'kx-hub')
GCP_REGION = os.environ.get('GCP_REGION', 'europe-west4')
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


# Note: Vertex AI Vector Search has been replaced with Firestore native vector search
# No separate index service client needed - embeddings stored directly in Firestore documents


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

    Supports both legacy document format and new chunk format.

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

    # Check if this is a chunk (has chunk_id field)
    is_chunk = 'chunk_id' in metadata

    if is_chunk:
        # Chunk format - validate chunk-specific fields
        required_fields = ['chunk_id', 'doc_id', 'chunk_index', 'total_chunks', 'title', 'author']
        for field in required_fields:
            if field not in metadata:
                raise ValueError(f"Missing required chunk field in frontmatter: {field}")

        # Use chunk_id as the item id
        metadata['id'] = metadata['chunk_id']
        metadata['parent_doc_id'] = metadata.get('doc_id')
    else:
        # Legacy document format - validate legacy fields
        required_fields = ['id', 'title', 'author', 'created_at', 'updated_at']
        for field in required_fields:
            if field not in metadata:
                raise ValueError(f"Missing required field in frontmatter: {field}")

    # Normalize optional fields
    if 'url' not in metadata:
        metadata['url'] = None
    if 'tags' not in metadata:
        metadata['tags'] = []
    if 'source' not in metadata:
        metadata['source'] = 'unknown'
    if 'category' not in metadata:
        metadata['category'] = 'unknown'

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
            # Specify output_dimensionality=768 to stay within Firestore's 2048 limit
            # gemini-embedding-001 default is 3072 dimensions which exceeds Firestore limit
            embeddings = model.get_embeddings([text], output_dimensionality=768)
            embedding_vector = embeddings[0].values
            logger.info(f"Generated embedding with {len(embedding_vector)} dimensions (type: {type(embedding_vector).__name__})")
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


# Removed: upsert_to_vector_search() - embeddings now stored directly in Firestore
# Removed: upsert_batch_to_vector_search() - embeddings now stored directly in Firestore


def write_to_firestore(
    metadata: Dict[str, Any],
    content: str,
    content_hash: str,
    run_id: str,
    embedding_status: str,
    embedding_vector: Optional[List[float]] = None
) -> bool:
    """
    Write chunk metadata, content, and embedding to Firestore kb_items collection.

    Supports both legacy document format and new chunk format.

    Args:
        metadata: Document/chunk metadata from frontmatter
        content: Full chunk content (markdown text without frontmatter)
        content_hash: Hash of the markdown content used for embedding
        run_id: Current pipeline run identifier
        embedding_status: Embedding status to persist with metadata
        embedding_vector: Optional 768-dimensional embedding vector (stored as Firestore Vector)

    Returns:
        True if successful, False if error occurred
    """
    try:
        db = get_firestore_client()

        # Check if this is a chunk
        is_chunk = 'chunk_id' in metadata

        if is_chunk:
            # Chunk schema (Story 1.6)
            doc_data = {
                'chunk_id': metadata['chunk_id'],
                'parent_doc_id': metadata.get('parent_doc_id', metadata.get('doc_id')),
                'chunk_index': metadata.get('chunk_index', 0),
                'total_chunks': metadata.get('total_chunks', 1),
                'title': metadata['title'],
                'author': metadata['author'],
                'source': metadata.get('source', 'unknown'),
                'category': metadata.get('category', 'unknown'),
                'tags': metadata.get('tags', []),
                'content': content,  # NEW: Store full chunk content
                'embedding_model': 'gemini-embedding-001',
                'content_hash': content_hash,
                'embedding_status': embedding_status,
                'last_embedded_at': getattr(firestore, "SERVER_TIMESTAMP", None),
                'last_error': None,
                'retry_count': 0,
                'created_at': getattr(firestore, "SERVER_TIMESTAMP", None),
                'updated_at': getattr(firestore, "SERVER_TIMESTAMP", None)
            }

            # Add chunk-specific fields if present
            if 'token_count' in metadata:
                doc_data['token_count'] = metadata['token_count']
            if 'overlap_start' in metadata:
                doc_data['overlap_start'] = metadata['overlap_start']
            if 'overlap_end' in metadata:
                doc_data['overlap_end'] = metadata['overlap_end']

        else:
            # Legacy document schema (backward compatibility)
            created_at_value = _parse_iso_datetime(metadata.get('created_at'))
            updated_at_value = _parse_iso_datetime(metadata.get('updated_at'))

            doc_data = {
                'title': metadata['title'],
                'url': metadata.get('url'),
                'tags': metadata.get('tags', []),
                'authors': [metadata['author']],
                'created_at': created_at_value if created_at_value else getattr(firestore, "SERVER_TIMESTAMP", None),
                'updated_at': updated_at_value if updated_at_value else getattr(firestore, "SERVER_TIMESTAMP", None),
                'content_hash': content_hash,
                'embedding_status': embedding_status,
                'last_embedded_at': getattr(firestore, "SERVER_TIMESTAMP", None),
                'last_error': None,
                'last_run_id': run_id,
                'cluster_id': [],
                'similar_ids': [],
                'scores': []
            }

        # Add embedding vector if provided (using Firestore Vector type for vector search)
        if embedding_vector is not None:
            # Ensure embedding_vector is a list of floats (not numpy array or other type)
            vector_list = [float(x) for x in embedding_vector]
            logger.info(f"Storing embedding vector with {len(vector_list)} dimensions for {metadata['id']}")

            # Store as Firestore Vector for native vector search
            if _HAS_MATCHING_ENGINE_LIB and Vector is not None:
                doc_data['embedding'] = Vector(vector_list)
            else:
                # Fallback: store as raw list
                doc_data['embedding'] = vector_list

        # Write to kb_items collection with document ID = chunk_id or item_id
        doc_ref = db.collection('kb_items').document(metadata['id'])
        doc_ref.set(doc_data, merge=True)

        logger.info(f"Wrote {'chunk' if is_chunk else 'document'} {metadata['id']} to Firestore with embedding={embedding_vector is not None}")
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
    3. Generate embeddings as needed and store to Firestore with vector search support
    4. Update pipeline state in Firestore
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

                # Store embedding directly in Firestore (replaces separate Vector Search upsert)
                if not write_to_firestore(metadata, markdown_content, computed_hash, run_id, "complete", embedding_vector=embedding_vector):
                    raise RuntimeError("Failed to write embedding to Firestore")
                stats['firestore_updates'] += 1
            else:
                logger.info(f"Skipping embedding generation for {item_id}; content hash unchanged")
                # Still update metadata even if embedding unchanged
                if not write_to_firestore(metadata, markdown_content, computed_hash, run_id, "complete"):
                    raise RuntimeError("Failed to update kb_items metadata")
                stats['firestore_updates'] += 1

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
