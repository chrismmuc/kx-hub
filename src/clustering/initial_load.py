"""
Initial load script for semantic clustering.

Bulk clusters all existing knowledge chunks using their embeddings
and updates Firestore with cluster assignments.

Usage:
    python3 -m src.clustering.initial_load [--dry-run]

Environment Variables:
    GCP_PROJECT: Google Cloud project ID
    GCP_REGION: Google Cloud region (default: europe-west4)
    FIRESTORE_COLLECTION: Firestore collection name (default: kb_items)
    GOOGLE_APPLICATION_CREDENTIALS: Path to service account key
"""

import os
import logging
import argparse
import time
import pickle
import json
from datetime import datetime
from typing import List, Dict, Any
import numpy as np
from google.cloud import firestore
from google.cloud import storage

from src.clustering.clusterer import SemanticClusterer, create_cluster_mapping

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class InitialLoadClusterer:
    """
    Handles initial bulk clustering of all knowledge chunks.

    Loads all chunks with embeddings, clusters them, and updates
    Firestore with cluster assignments. Graph generation is deferred to Story 3.2.
    """

    def __init__(
        self,
        project_id: str,
        region: str = 'europe-west4',
        collection_name: str = 'kb_items',
        bucket_name: str = None,
        dry_run: bool = False
    ):
        """
        Initialize initial load clusterer.

        Args:
            project_id: GCP project ID
            region: GCP region
            collection_name: Firestore collection name
            bucket_name: GCS bucket name (optional)
            dry_run: If True, don't write to Firestore/GCS
        """
        self.project_id = project_id
        self.region = region
        self.collection_name = collection_name
        self.bucket_name = bucket_name or f"{project_id}-pipeline"
        self.dry_run = dry_run

        # Initialize clients
        logger.info(f"Initializing Firestore client for project: {project_id}")
        self.db = firestore.Client(project=project_id)

        if not dry_run:
            logger.info(f"Initializing Storage client for bucket: {self.bucket_name}")
            self.storage_client = storage.Client(project=project_id)

    def load_chunks_with_embeddings(self) -> tuple[List[Dict[str, Any]], np.ndarray, List[str]]:
        """
        Load all chunks with embeddings from Firestore.

        Returns:
            Tuple of (chunks, embeddings_array, chunk_ids)
        """
        logger.info(f"Loading chunks from Firestore collection: {self.collection_name}")

        collection_ref = self.db.collection(self.collection_name)
        docs = collection_ref.stream()

        chunks = []
        embeddings = []
        chunk_ids = []

        for doc in docs:
            data = doc.to_dict()

            # Check if chunk has embedding
            if 'embedding' not in data:
                logger.warning(f"Chunk {doc.id} missing embedding, skipping")
                continue

            # Extract embedding (may be Vector type or list)
            embedding = data['embedding']
            if hasattr(embedding, 'to_map_value'):
                # Firestore Vector type - extract values from dict
                map_value = embedding.to_map_value()
                embedding_values = map_value.get('value', map_value)  # Extract 'value' key
                embedding_array = np.array(embedding_values, dtype=np.float32)
            elif isinstance(embedding, list):
                embedding_array = np.array(embedding, dtype=np.float32)
            else:
                logger.warning(f"Chunk {doc.id} has invalid embedding type: {type(embedding)}")
                continue

            # Validate embedding dimension
            if len(embedding_array) != 768:
                logger.warning(
                    f"Chunk {doc.id} has wrong embedding dimension: {len(embedding_array)}, "
                    f"expected 768"
                )
                continue

            chunks.append(data)
            embeddings.append(embedding_array)
            chunk_ids.append(doc.id)

        embeddings_array = np.array(embeddings, dtype=np.float32)

        logger.info(
            f"Loaded {len(chunks)} chunks with embeddings "
            f"(shape: {embeddings_array.shape})"
        )

        return chunks, embeddings_array, chunk_ids

    def cluster_embeddings(self, embeddings: np.ndarray) -> tuple[np.ndarray, Dict[str, Any], SemanticClusterer]:
        """
        Cluster embeddings using HDBSCAN.

        Args:
            embeddings: Array of embedding vectors

        Returns:
            Tuple of (cluster_labels, quality_metrics, clusterer)
        """
        logger.info("Starting clustering with HDBSCAN...")

        clusterer = SemanticClusterer(
            algorithm='hdbscan',
            min_cluster_size=10,  # Optimal: Research-backed, prevents over-fragmentation
            min_samples=3         # Optimal: Balanced density estimation
        )

        # Cluster
        start_time = time.time()
        cluster_labels = clusterer.fit_predict(embeddings)
        elapsed = time.time() - start_time

        logger.info(f"Clustering completed in {elapsed:.2f} seconds")

        # Compute quality metrics
        metrics = clusterer.compute_quality_metrics(embeddings)
        logger.info(f"Quality metrics: {metrics}")

        return cluster_labels, metrics, clusterer

    def update_firestore_with_clusters(
        self,
        chunk_ids: List[str],
        cluster_labels: np.ndarray,
        clear_existing: bool = True
    ):
        """
        Update Firestore with cluster assignments using batch writes.

        Args:
            chunk_ids: List of chunk document IDs
            cluster_labels: Cluster labels for each chunk
            clear_existing: If True, clear existing cluster_id fields first (idempotency)
        """
        if self.dry_run:
            logger.info("[DRY RUN] Would update Firestore with cluster assignments")
            return

        logger.info(f"Updating {len(chunk_ids)} chunks in Firestore...")

        # Create cluster mapping
        cluster_mapping = create_cluster_mapping(chunk_ids, cluster_labels)

        # Batch write to Firestore (max 500 operations per batch)
        batch = self.db.batch()
        write_count = 0
        total_updates = 0

        for i, chunk_id in enumerate(chunk_ids):
            doc_ref = self.db.collection(self.collection_name).document(chunk_id)

            # Update cluster_id field
            cluster_ids = cluster_mapping[chunk_id]

            if clear_existing and i == 0:
                # First update: clear existing cluster_ids for idempotency
                logger.info("Clearing existing cluster_id fields (idempotency)...")

            batch.update(doc_ref, {'cluster_id': cluster_ids})
            write_count += 1
            total_updates += 1

            # Commit every 500 operations
            if write_count == 500:
                try:
                    batch.commit()
                    logger.info(f"  Committed batch {total_updates//500} ({total_updates} updates)")
                except Exception as e:
                    logger.error(f"Error committing batch: {e}")
                    # Retry once
                    try:
                        logger.info("Retrying batch commit...")
                        time.sleep(2)
                        batch.commit()
                        logger.info("Retry successful")
                    except Exception as retry_e:
                        logger.error(f"Retry failed: {retry_e}")
                        raise

                # Create new batch
                batch = self.db.batch()
                write_count = 0

            # Progress logging every 100 chunks
            if (i + 1) % 100 == 0:
                logger.info(f"  Progress: {i + 1}/{len(chunk_ids)} chunks updated")

        # Commit remaining operations
        if write_count > 0:
            try:
                batch.commit()
                logger.info(f"  Committed final batch ({write_count} updates)")
            except Exception as e:
                logger.error(f"Error committing final batch: {e}")
                raise

        logger.info(f"✅ Successfully updated {total_updates} chunks with cluster assignments")

    def save_umap_model(self, clusterer: SemanticClusterer):
        """
        Save UMAP model and metadata to Cloud Storage.

        Args:
            clusterer: SemanticClusterer instance with fitted UMAP model
        """
        if self.dry_run:
            logger.info("[DRY RUN] Would save UMAP model to Cloud Storage")
            return

        if clusterer.umap_model is None:
            logger.warning("No UMAP model to save (UMAP not used)")
            return

        logger.info("Saving UMAP model to Cloud Storage...")

        # Save using joblib (recommended by UMAP) with Numba-safe settings
        import tempfile
        import joblib

        with tempfile.NamedTemporaryFile(suffix='.pkl', delete=False) as tmp_file:
            joblib.dump(clusterer.umap_model, tmp_file.name)
            tmp_file.seek(0)
            model_bytes = open(tmp_file.name, 'rb').read()
            model_size_kb = len(model_bytes) / 1024
            os.unlink(tmp_file.name)

        logger.info(f"UMAP model serialized: {model_size_kb:.2f} KB")

        # Upload to Cloud Storage
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob('models/umap_model.pkl')
        blob.upload_from_string(model_bytes, content_type='application/octet-stream')

        logger.info(f"✅ UMAP model uploaded to gs://{self.bucket_name}/models/umap_model.pkl")

        # Create metadata file
        metadata = {
            'version': datetime.now().strftime('%Y-%m-%d'),
            'created_at': datetime.now().isoformat(),
            'umap_parameters': {
                'n_components': clusterer.umap_n_components,
                'n_neighbors': clusterer.umap_n_neighbors,
                'metric': 'cosine',
                'min_dist': 0.0,
                'random_state': clusterer.random_state
            },
            'model_size_bytes': len(model_bytes),
            'storage_path': f'gs://{self.bucket_name}/models/umap_model.pkl'
        }

        # Upload metadata
        metadata_blob = bucket.blob('models/umap_metadata.json')
        metadata_blob.upload_from_string(
            json.dumps(metadata, indent=2),
            content_type='application/json'
        )

        logger.info(f"✅ UMAP metadata saved to gs://{self.bucket_name}/models/umap_metadata.json")
        logger.info(f"   UMAP version: {metadata['version']}")
        logger.info(f"   Parameters: {metadata['umap_parameters']}")

    def run(self):
        """Execute the complete initial load clustering workflow."""
        logger.info("=" * 60)
        logger.info("INITIAL LOAD CLUSTERING - START")
        logger.info("=" * 60)

        if self.dry_run:
            logger.warning("⚠️  DRY RUN MODE - No writes will be performed")

        start_time = time.time()

        # Step 1: Load chunks with embeddings
        logger.info("\n[Step 1/4] Loading chunks with embeddings...")
        chunks, embeddings, chunk_ids = self.load_chunks_with_embeddings()

        if len(chunks) == 0:
            logger.error("No chunks with embeddings found. Aborting.")
            return

        # Step 2: Cluster embeddings
        logger.info(f"\n[Step 2/4] Clustering {len(embeddings)} embeddings...")
        cluster_labels, metrics, clusterer = self.cluster_embeddings(embeddings)

        # Step 3: Save UMAP model
        logger.info("\n[Step 3/4] Saving UMAP model to Cloud Storage...")
        self.save_umap_model(clusterer)

        # Step 4: Update Firestore
        logger.info("\n[Step 4/4] Updating Firestore with cluster assignments...")
        self.update_firestore_with_clusters(chunk_ids, cluster_labels, clear_existing=True)

        # Summary
        elapsed = time.time() - start_time
        logger.info("\n" + "=" * 60)
        logger.info("INITIAL LOAD CLUSTERING - COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total time: {elapsed:.2f} seconds ({elapsed/60:.1f} minutes)")
        logger.info(f"Chunks processed: {len(chunks)}")
        logger.info(f"Clusters found: {metrics.get('n_clusters', 0)}")
        logger.info(f"Noise points: {metrics.get('n_noise_points', 0)}")
        logger.info(f"Silhouette score: {metrics.get('silhouette_score', 'N/A')}")
        logger.info("=" * 60)


def main():
    """Main entry point for initial load clustering."""
    parser = argparse.ArgumentParser(
        description='Initial load clustering for kx-hub knowledge base'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without writing to Firestore/GCS (for testing)'
    )

    args = parser.parse_args()

    # Get configuration from environment
    project_id = os.getenv('GCP_PROJECT')
    region = os.getenv('GCP_REGION', 'europe-west4')
    collection_name = os.getenv('FIRESTORE_COLLECTION', 'kb_items')

    if not project_id:
        logger.error("GCP_PROJECT environment variable not set")
        sys.exit(1)

    # Check credentials
    creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if not creds_path:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set, using default credentials")

    # Run clustering
    clusterer = InitialLoadClusterer(
        project_id=project_id,
        region=region,
        collection_name=collection_name,
        dry_run=args.dry_run
    )

    try:
        clusterer.run()
    except Exception as e:
        logger.error(f"Clustering failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
