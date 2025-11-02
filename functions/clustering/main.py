"""
Cloud Function for delta clustering processing.

Assigns new chunks to existing clusters as part of the daily batch pipeline.
Triggered by Cloud Workflows after Knowledge Cards generation.

Function URL:
    POST https://europe-west4-{project}.cloudfunctions.net/clustering-function

Request payload:
    {
        "chunk_ids": ["chunk-1", "chunk-2", ...],
        "run_id": "2025-11-02-daily"
    }

Response:
    {
        "status": "success",
        "clusters_assigned": 10,
        "processing_time_sec": 45.3,
        "run_id": "2025-11-02-daily"
    }
"""

import os
import logging
import time
import json
from typing import List, Dict, Any
import numpy as np
from google.cloud import firestore
from google.cloud import storage
import functions_framework
from flask import Request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_embeddings_from_firestore(
    db: firestore.Client,
    collection_name: str,
    chunk_ids: List[str]
) -> tuple[List[Dict[str, Any]], np.ndarray, List[str]]:
    """
    Load embeddings for specific chunks from Firestore.

    Args:
        db: Firestore client
        collection_name: Collection name
        chunk_ids: List of chunk IDs to load

    Returns:
        Tuple of (chunks, embeddings_array, valid_chunk_ids)
    """
    chunks = []
    embeddings = []
    valid_ids = []

    for chunk_id in chunk_ids:
        doc_ref = db.collection(collection_name).document(chunk_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.warning(f"Chunk {chunk_id} not found, skipping")
            continue

        data = doc.to_dict()

        # Check for embedding
        if 'embedding' not in data:
            logger.warning(f"Chunk {chunk_id} missing embedding, skipping")
            continue

        # Extract embedding
        embedding = data['embedding']
        if hasattr(embedding, 'to_map_value'):
            # Firestore Vector type - extract values from dict
            map_value = embedding.to_map_value()
            embedding_values = map_value.get('value', map_value)  # Extract 'value' key
            embedding_array = np.array(embedding_values, dtype=np.float32)
        elif isinstance(embedding, list):
            embedding_array = np.array(embedding, dtype=np.float32)
        else:
            logger.warning(f"Chunk {chunk_id} invalid embedding type: {type(embedding)}")
            continue

        if len(embedding_array) != 768:
            logger.warning(f"Chunk {chunk_id} wrong embedding dimension: {len(embedding_array)}")
            continue

        chunks.append(data)
        embeddings.append(embedding_array)
        valid_ids.append(chunk_id)

    embeddings_array = np.array(embeddings, dtype=np.float32) if embeddings else np.array([])

    logger.info(f"Loaded {len(chunks)} chunks with valid embeddings")

    return chunks, embeddings_array, valid_ids


def load_existing_clusters(
    db: firestore.Client,
    collection_name: str = 'clusters'
) -> tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Load cluster centroids from clusters collection (efficient).

    Instead of loading all chunks, loads only cluster centroids
    for efficient assignment of new chunks.

    Args:
        db: Firestore client
        collection_name: Clusters collection name (default: 'clusters')

    Returns:
        Tuple of (centroid_embeddings, cluster_labels, cluster_ids)
    """
    logger.info("Loading cluster centroids from Firestore...")

    collection_ref = db.collection(collection_name)
    docs = collection_ref.stream()

    centroids = []
    labels = []
    cluster_ids = []

    for doc in docs:
        data = doc.to_dict()
        cluster_id = doc.id

        # Skip noise cluster
        if cluster_id == 'noise':
            continue

        # Extract centroid
        if 'centroid' not in data:
            logger.warning(f"Cluster {cluster_id} missing centroid, skipping")
            continue

        centroid = data['centroid']
        if hasattr(centroid, 'to_map_value'):
            # Firestore Vector type - extract values from dict
            map_value = centroid.to_map_value()
            centroid_values = map_value.get('value', map_value)
            centroid_array = np.array(centroid_values, dtype=np.float32)
        elif isinstance(centroid, list):
            centroid_array = np.array(centroid, dtype=np.float32)
        else:
            logger.warning(f"Cluster {cluster_id} has invalid centroid type: {type(centroid)}")
            continue

        # Convert cluster ID to integer label
        if cluster_id.startswith("cluster-"):
            try:
                label = int(cluster_id.split("-")[1])
            except ValueError:
                logger.warning(f"Invalid cluster_id format: {cluster_id}")
                continue
        else:
            logger.warning(f"Unknown cluster_id format: {cluster_id}")
            continue

        centroids.append(centroid_array)
        labels.append(label)
        cluster_ids.append(cluster_id)

    centroids_array = np.array(centroids, dtype=np.float32) if centroids else np.array([])
    labels_array = np.array(labels, dtype=np.int32) if labels else np.array([])

    logger.info(
        f"Loaded {len(centroids)} cluster centroids "
        f"(much faster than loading all chunks!)"
    )

    return centroids_array, labels_array, cluster_ids


def assign_to_existing_clusters(
    new_embeddings: np.ndarray,
    existing_embeddings: np.ndarray,
    existing_labels: np.ndarray
) -> np.ndarray:
    """
    Assign new embeddings to existing clusters using nearest neighbor.

    Args:
        new_embeddings: New embedding vectors
        existing_embeddings: Existing embedding vectors
        existing_labels: Cluster labels for existing embeddings

    Returns:
        Cluster labels for new embeddings
    """
    from sklearn.metrics.pairwise import cosine_distances

    logger.info(f"Assigning {len(new_embeddings)} new embeddings to existing clusters...")

    # Compute distance from new to existing
    distances = cosine_distances(new_embeddings, existing_embeddings)

    # Find nearest existing embedding for each new embedding
    nearest_indices = np.argmin(distances, axis=1)

    # Assign same cluster as nearest neighbor
    new_labels = existing_labels[nearest_indices]

    # Log assignments
    unique_labels, counts = np.unique(new_labels, return_counts=True)
    for label, count in zip(unique_labels, counts):
        cluster_id = "noise" if label == -1 else f"cluster-{label}"
        logger.info(f"  Assigned {count} chunks to {cluster_id}")

    return new_labels


def update_firestore_batch(
    db: firestore.Client,
    collection_name: str,
    chunk_ids: List[str],
    cluster_labels: np.ndarray
):
    """
    Update Firestore with cluster assignments using batch writes.

    Args:
        db: Firestore client
        collection_name: Collection name
        chunk_ids: List of chunk IDs
        cluster_labels: Cluster labels for each chunk
    """
    logger.info(f"Updating {len(chunk_ids)} chunks with cluster assignments...")

    batch = db.batch()
    write_count = 0

    for chunk_id, label in zip(chunk_ids, cluster_labels):
        # Convert label to cluster_id string
        if label == -1:
            cluster_id = "noise"
        else:
            cluster_id = f"cluster-{label}"

        doc_ref = db.collection(collection_name).document(chunk_id)
        batch.update(doc_ref, {'cluster_id': [cluster_id]})
        write_count += 1

        # Commit every 500 operations
        if write_count == 500:
            batch.commit()
            logger.info(f"  Committed batch ({write_count} updates)")
            batch = db.batch()
            write_count = 0

    # Commit remaining
    if write_count > 0:
        batch.commit()
        logger.info(f"  Committed final batch ({write_count} updates)")

    logger.info("✅ Firestore updates complete")


@functions_framework.http
def cluster_new_chunks(request: Request):
    """
    Cloud Function HTTP handler for delta clustering.

    Args:
        request: Flask request with JSON payload

    Returns:
        JSON response with clustering results
    """
    start_time = time.time()

    # Parse request
    try:
        request_json = request.get_json(silent=True)

        if not request_json:
            return {'error': 'Request body must be JSON'}, 400

        chunk_ids = request_json.get('chunk_ids', [])
        run_id = request_json.get('run_id', 'unknown')

        if not chunk_ids:
            return {'error': 'chunk_ids is required'}, 400

        logger.info(f"Processing {len(chunk_ids)} chunks for run_id: {run_id}")

    except Exception as e:
        logger.error(f"Failed to parse request: {e}")
        return {'error': f'Invalid request: {str(e)}'}, 400

    # Get configuration
    project_id = os.getenv('GCP_PROJECT')
    collection_name = os.getenv('FIRESTORE_COLLECTION', 'kb_items')
    bucket_name = os.getenv('GCS_BUCKET', f'{project_id}-data')

    # Initialize clients
    db = firestore.Client(project=project_id)
    storage_client = storage.Client(project=project_id)

    try:
        # Step 1: Load new chunk embeddings
        logger.info("[Step 1/4] Loading new chunk embeddings...")
        new_chunks, new_embeddings, valid_chunk_ids = load_embeddings_from_firestore(
            db, collection_name, chunk_ids
        )

        if len(new_chunks) == 0:
            logger.warning("No valid chunks to cluster")
            return {
                'status': 'success',
                'clusters_assigned': 0,
                'processing_time_sec': time.time() - start_time,
                'run_id': run_id,
                'message': 'No valid chunks found'
            }, 200

        # Step 2: Load existing cluster centroids (efficient!)
        logger.info("[Step 2/4] Loading cluster centroids...")
        centroid_embeddings, centroid_labels, cluster_ids = load_existing_clusters(
            db, 'clusters'  # Load from clusters collection
        )

        if len(centroid_embeddings) == 0:
            logger.error("No existing clusters found - run initial_load.py first")
            return {
                'error': 'No existing clusters found. Run initial load first.'
            }, 500

        # Step 3: Assign new chunks to nearest centroids
        logger.info("[Step 3/4] Assigning new chunks to nearest centroids...")
        new_labels = assign_to_existing_clusters(
            new_embeddings, centroid_embeddings, centroid_labels
        )

        # Step 4: Update Firestore
        logger.info("[Step 4/4] Updating Firestore...")
        update_firestore_batch(db, collection_name, valid_chunk_ids, new_labels)

        # TODO: Optionally regenerate graph.json with updated memberships
        # This could be expensive for large datasets, so might be done separately

        # Success response
        elapsed = time.time() - start_time
        logger.info(f"✅ Delta clustering complete in {elapsed:.2f}s")

        return {
            'status': 'success',
            'clusters_assigned': len(valid_chunk_ids),
            'processing_time_sec': round(elapsed, 2),
            'run_id': run_id
        }, 200

    except Exception as e:
        logger.error(f"Clustering failed: {e}", exc_info=True)
        return {
            'error': str(e),
            'run_id': run_id
        }, 500
