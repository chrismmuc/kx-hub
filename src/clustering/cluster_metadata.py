"""
Cluster metadata generation and management.

Generates cluster metadata including:
- Centroids (average embeddings)
- Names and descriptions (via Gemini API)
- Statistics (size, coherence)
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import numpy as np
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector
import vertexai
from vertexai.generative_models import GenerativeModel

logger = logging.getLogger(__name__)


class ClusterMetadataGenerator:
    """
    Generates and manages cluster metadata in Firestore.

    Creates a 'clusters' collection with:
    - Centroid embeddings for efficient assignment
    - Gemini-generated names and descriptions
    - Cluster statistics
    """

    def __init__(
        self,
        project_id: str,
        region: str = 'europe-west4',
        kb_collection: str = 'kb_items',
        clusters_collection: str = 'clusters',
        dry_run: bool = False,
        umap_model = None,
        umap_version: str = None
    ):
        """
        Initialize cluster metadata generator.

        Args:
            project_id: GCP project ID
            region: GCP region
            kb_collection: Knowledge base collection name
            clusters_collection: Clusters collection name
            dry_run: If True, don't write to Firestore
            umap_model: UMAP model for generating 5D centroids
            umap_version: UMAP model version string
        """
        self.project_id = project_id
        self.region = region
        self.kb_collection = kb_collection
        self.clusters_collection = clusters_collection
        self.dry_run = dry_run
        self.umap_model = umap_model
        self.umap_version = umap_version or datetime.now().strftime('%Y-%m-%d')

        # Initialize clients
        logger.info(f"Initializing Firestore for project: {project_id}")
        self.db = firestore.Client(project=project_id)

        logger.info(f"Initializing Vertex AI in region: {region}")
        vertexai.init(project=project_id, location=region)
        self.model = GenerativeModel('gemini-2.5-flash')

    def generate_all_clusters(self) -> Dict[str, Any]:
        """
        Generate metadata for all clusters.

        Returns:
            Dict with statistics about cluster generation
        """
        logger.info("=" * 60)
        logger.info("CLUSTER METADATA GENERATION - START")
        logger.info("=" * 60)

        if self.dry_run:
            logger.warning("⚠️  DRY RUN MODE - No writes will be performed")

        # Step 1: Load chunks grouped by cluster
        logger.info("\n[Step 1/3] Loading chunks grouped by cluster...")
        cluster_groups = self._load_clusters_from_chunks()

        logger.info(f"Found {len(cluster_groups)} clusters")

        # Step 2: Generate metadata for each cluster
        logger.info("\n[Step 2/3] Generating cluster metadata...")
        clusters_metadata = []

        for cluster_id, chunks in cluster_groups.items():
            logger.info(f"Processing {cluster_id} ({len(chunks)} chunks)...")

            metadata = self._generate_cluster_metadata(cluster_id, chunks)
            clusters_metadata.append(metadata)

        # Step 3: Write to Firestore
        logger.info(f"\n[Step 3/3] Writing {len(clusters_metadata)} clusters to Firestore...")

        if self.dry_run:
            logger.info("[DRY RUN] Would write clusters to Firestore")
        else:
            self._write_clusters_to_firestore(clusters_metadata)

        logger.info("\n" + "=" * 60)
        logger.info("CLUSTER METADATA GENERATION - COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total clusters: {len(clusters_metadata)}")

        return {
            'total_clusters': len(clusters_metadata),
            'cluster_ids': [c['id'] for c in clusters_metadata]
        }

    def _load_clusters_from_chunks(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load all chunks grouped by cluster_id.

        Returns:
            Dict mapping cluster_id to list of chunks
        """
        docs = self.db.collection(self.kb_collection).stream()

        cluster_groups = {}

        for doc in docs:
            data = doc.to_dict()

            # Get cluster assignment
            cluster_ids = data.get('cluster_id', [])
            if not cluster_ids:
                continue

            cluster_id = cluster_ids[0]  # Use primary cluster

            # Extract embedding
            if 'embedding' not in data:
                continue

            embedding = data['embedding']
            if hasattr(embedding, 'to_map_value'):
                map_value = embedding.to_map_value()
                embedding_values = map_value.get('value', map_value)
                embedding_array = np.array(embedding_values, dtype=np.float32)
            elif isinstance(embedding, list):
                embedding_array = np.array(embedding, dtype=np.float32)
            else:
                continue

            # Store chunk data
            chunk_data = {
                'id': doc.id,
                'title': data.get('title', ''),
                'content': data.get('content', ''),
                'embedding': embedding_array,
                'tags': data.get('tags', []),
                'source': data.get('source', '')
            }

            if cluster_id not in cluster_groups:
                cluster_groups[cluster_id] = []

            cluster_groups[cluster_id].append(chunk_data)

        logger.info(f"Loaded {sum(len(chunks) for chunks in cluster_groups.values())} chunks across {len(cluster_groups)} clusters")

        return cluster_groups

    def _generate_cluster_metadata(
        self,
        cluster_id: str,
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate metadata for a single cluster.

        Args:
            cluster_id: Cluster ID
            chunks: List of chunks in this cluster

        Returns:
            Cluster metadata dict
        """
        # Calculate centroid in 768D space (mean embedding)
        embeddings = np.array([chunk['embedding'] for chunk in chunks])
        centroid_768d = np.mean(embeddings, axis=0).astype(np.float32)

        # Calculate centroid in 5D UMAP space if UMAP model available
        centroid_5d = None
        if self.umap_model is not None:
            embeddings_5d = self.umap_model.transform(embeddings)
            centroid_5d = np.mean(embeddings_5d, axis=0).astype(np.float32)
            logger.debug(f"  Computed 5D centroid for {cluster_id}: shape {centroid_5d.shape}")

        # Generate name and description via Gemini (with improved sampling)
        name, description = self._generate_cluster_name_description(chunks, embeddings, centroid_768d)

        # Calculate statistics
        size = len(chunks)

        # Prepare metadata
        metadata = {
            'id': cluster_id,
            'name': name,
            'description': description,
            'size': size,
            'centroid_768d': centroid_768d.tolist(),  # Reference only
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'updated_at': datetime.utcnow().isoformat() + 'Z'
        }

        # Add 5D centroid if UMAP model was used
        if centroid_5d is not None:
            metadata['centroid_5d'] = centroid_5d.tolist()  # Active for assignments
            metadata['umap_version'] = self.umap_version

        return metadata

    def _generate_cluster_name_description(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: np.ndarray,
        centroid: np.ndarray,
        sample_size: int = 12
    ) -> tuple[str, str]:
        """
        Generate cluster name and description using Gemini with improved sampling.

        Args:
            chunks: Chunks in this cluster
            embeddings: Embeddings for all chunks (same order as chunks)
            centroid: Cluster centroid embedding
            sample_size: Number of chunks to sample for analysis (default: 12)

        Returns:
            Tuple of (name, description)
        """
        from sklearn.metrics.pairwise import cosine_distances

        # Improved sampling strategy: mix of representative + diverse chunks
        n_chunks = len(chunks)
        actual_sample_size = min(sample_size, n_chunks)

        if n_chunks <= sample_size:
            # Use all chunks if cluster is small
            sample_chunks = chunks
        else:
            # Compute distances from centroid
            distances = cosine_distances(embeddings, centroid.reshape(1, -1)).flatten()

            # Select mix of representative (close to centroid) + diverse (spread across cluster)
            n_representative = actual_sample_size // 2
            n_diverse = actual_sample_size - n_representative

            # Get indices of most representative chunks (closest to centroid)
            representative_indices = np.argsort(distances)[:n_representative]

            # Get diverse chunks by stratified sampling across distance ranges
            remaining_indices = np.argsort(distances)[n_representative:]
            if len(remaining_indices) > n_diverse:
                # Sample evenly across remaining chunks
                diverse_indices = remaining_indices[::len(remaining_indices)//n_diverse][:n_diverse]
            else:
                diverse_indices = remaining_indices

            # Combine and select chunks
            sample_indices = np.concatenate([representative_indices, diverse_indices])
            sample_chunks = [chunks[i] for i in sample_indices]

        logger.debug(f"  Sampling {len(sample_chunks)} chunks ({len(chunks)} total) for naming")

        # Build prompt with chunk titles and LONGER content snippets
        chunk_texts = []
        for i, chunk in enumerate(sample_chunks):
            title = chunk.get('title', 'Untitled')
            content = chunk.get('content', '')[:400]  # Increased from 200 to 400 chars
            chunk_texts.append(f"{i+1}. {title}\n   {content}...")

        prompt = f"""Analyze these {len(chunks)} related knowledge chunks and generate an accurate cluster name.

I'm showing you {len(sample_chunks)} representative samples from the cluster:

{chr(10).join(chunk_texts)}

IMPORTANT INSTRUCTIONS:
1. Identify the DOMINANT topic or theme that appears in MOST chunks (not just a few)
2. Look for recurring keywords, concepts, and themes across all samples
3. Generate a cluster name that captures the MAJORITY of the content
4. If chunks seem to mix multiple topics, identify which topic is most prevalent
5. Be specific enough to distinguish this cluster from others

Generate:
NAME: <cluster name (3-6 words, must reflect the DOMINANT theme across all {len(chunks)} chunks)>
DESCRIPTION: <1-2 sentences explaining the common theme and key recurring concepts>

Format your response EXACTLY as shown above."""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()

            # Parse response
            name = "Unnamed Cluster"
            description = "No description available"

            for line in text.split('\n'):
                if line.startswith('NAME:'):
                    name = line.replace('NAME:', '').strip()
                elif line.startswith('DESCRIPTION:'):
                    description = line.replace('DESCRIPTION:', '').strip()

            logger.info(f"  Generated: {name}")

            return name, description

        except Exception as e:
            logger.warning(f"Failed to generate cluster name via Gemini: {e}")
            # Fallback to tag-based name
            all_tags = []
            for chunk in sample_chunks:
                all_tags.extend(chunk.get('tags', []))

            if all_tags:
                # Use most common tags
                from collections import Counter
                common_tags = Counter(all_tags).most_common(2)
                name = " & ".join([tag for tag, _ in common_tags])
                description = f"Content related to {name}"
            else:
                name = f"Cluster {len(chunks)} items"
                description = "Mixed content cluster"

            return name, description

    def _write_clusters_to_firestore(self, clusters: List[Dict[str, Any]]):
        """
        Write cluster metadata to Firestore.

        Args:
            clusters: List of cluster metadata dicts
        """
        collection_ref = self.db.collection(self.clusters_collection)

        batch = self.db.batch()
        batch_count = 0

        for cluster in clusters:
            doc_ref = collection_ref.document(cluster['id'])

            # Convert centroids to Vector types
            cluster_data = cluster.copy()
            cluster_data['centroid_768d'] = Vector(cluster['centroid_768d'])

            if 'centroid_5d' in cluster:
                cluster_data['centroid_5d'] = Vector(cluster['centroid_5d'])

            batch.set(doc_ref, cluster_data)
            batch_count += 1

            # Commit batch every 500 operations
            if batch_count >= 500:
                batch.commit()
                logger.info(f"  Committed batch ({batch_count} clusters)")
                batch = self.db.batch()
                batch_count = 0

        # Commit final batch
        if batch_count > 0:
            batch.commit()
            logger.info(f"  Committed final batch ({batch_count} clusters)")

        logger.info(f"✅ Successfully wrote {len(clusters)} clusters to Firestore")


def main():
    """CLI entry point for cluster metadata generation."""
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description='Generate cluster metadata and store in Firestore'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without writing to Firestore'
    )

    args = parser.parse_args()

    # Get config from environment
    project_id = os.environ.get('GCP_PROJECT', 'kx-hub')
    region = os.environ.get('GCP_REGION', 'europe-west4')

    generator = ClusterMetadataGenerator(
        project_id=project_id,
        region=region,
        dry_run=args.dry_run
    )

    try:
        stats = generator.generate_all_clusters()
        logger.info(f"\nGeneration complete: {stats}")
    except Exception as e:
        logger.error(f"Cluster metadata generation failed: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    main()
