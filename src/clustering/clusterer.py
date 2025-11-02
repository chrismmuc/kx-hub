"""
Core semantic clustering logic using HDBSCAN or K-Means.

Provides clustering algorithms for grouping knowledge chunks based on
embedding similarity using cosine distance metric.
"""

import logging
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from sklearn.metrics.pairwise import cosine_distances
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize
import umap

logger = logging.getLogger(__name__)


class SemanticClusterer:
    """
    Semantic clustering for knowledge chunks using embeddings.

    Supports two algorithms:
    - HDBSCAN: Density-based clustering without predefined cluster count
    - K-Means: Fast clustering with predefined number of clusters

    Args:
        algorithm: Clustering algorithm to use ('hdbscan' or 'kmeans')
        min_cluster_size: Minimum cluster size for HDBSCAN (default: 3)
        min_samples: Minimum samples for HDBSCAN core points (default: 2)
        n_clusters: Number of clusters for K-Means (default: None, auto-calculated)
        random_state: Random seed for reproducibility (default: 42)
    """

    def __init__(
        self,
        algorithm: str = 'hdbscan',
        min_cluster_size: int = 3,
        min_samples: int = 2,
        n_clusters: Optional[int] = None,
        random_state: int = 42,
        use_umap: bool = True,
        umap_n_components: int = 5,
        umap_n_neighbors: int = 15
    ):
        self.algorithm = algorithm.lower()
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.use_umap = use_umap
        self.umap_n_components = umap_n_components
        self.umap_n_neighbors = umap_n_neighbors

        # Cluster model (set after fit)
        self.clusterer = None
        self.umap_model = None
        self.labels_ = None
        self.n_clusters_found = 0
        self.n_noise_points = 0

        logger.info(
            f"Initialized SemanticClusterer: algorithm={algorithm}, "
            f"min_cluster_size={min_cluster_size}, min_samples={min_samples}, "
            f"use_umap={use_umap}"
        )

    def fit_predict(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Cluster embeddings and return cluster labels.

        Args:
            embeddings: Array of shape (n_samples, n_features) with embedding vectors

        Returns:
            Array of cluster labels (integers). For HDBSCAN, -1 indicates noise.

        Raises:
            ValueError: If algorithm is not supported or embeddings are invalid
        """
        if embeddings.shape[0] == 0:
            raise ValueError("Cannot cluster empty embeddings array")

        if embeddings.ndim != 2:
            raise ValueError(f"Embeddings must be 2D array, got shape {embeddings.shape}")

        n_samples = embeddings.shape[0]
        logger.info(f"Clustering {n_samples} embeddings with {self.algorithm}")

        # Apply UMAP dimensionality reduction if enabled
        if self.use_umap:
            logger.info(f"Applying UMAP: {embeddings.shape[1]}D → {self.umap_n_components}D...")
            self.umap_model = umap.UMAP(
                n_components=self.umap_n_components,
                n_neighbors=self.umap_n_neighbors,
                metric='cosine',
                random_state=self.random_state,
                min_dist=0.0
            )
            embeddings_reduced = self.umap_model.fit_transform(embeddings)
            logger.info(f"UMAP complete: reduced to shape {embeddings_reduced.shape}")
        else:
            embeddings_reduced = embeddings

        if self.algorithm == 'hdbscan':
            labels = self._fit_hdbscan(embeddings_reduced)
        elif self.algorithm == 'kmeans':
            labels = self._fit_kmeans(embeddings_reduced)
        else:
            raise ValueError(
                f"Unsupported algorithm: {self.algorithm}. "
                f"Choose 'hdbscan' or 'kmeans'"
            )

        self.labels_ = labels
        self._compute_statistics()

        return labels

    def _fit_hdbscan(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Cluster using HDBSCAN.

        If UMAP was applied, use euclidean distance on reduced embeddings.
        Otherwise, use cosine distance on original high-dimensional embeddings.
        """
        if self.use_umap:
            # UMAP already applied cosine metric; use euclidean on reduced space
            logger.info(f"Running HDBSCAN on UMAP-reduced embeddings (min_cluster_size={self.min_cluster_size})...")
            self.clusterer = HDBSCAN(
                metric='euclidean',
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                cluster_selection_epsilon=0.1,  # Merge similar clusters
            )
            labels = self.clusterer.fit_predict(embeddings)
        else:
            # Original high-dimensional path: compute cosine distance matrix
            logger.info(f"Computing cosine distance matrix for {len(embeddings)} embeddings...")
            distance_matrix = cosine_distances(embeddings)

            logger.info(f"Running HDBSCAN on cosine distance (min_cluster_size={self.min_cluster_size})...")
            self.clusterer = HDBSCAN(
                metric='precomputed',
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples
            )
            labels = self.clusterer.fit_predict(distance_matrix)

        return labels

    def _fit_kmeans(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Cluster using K-Means with L2-normalized embeddings.

        If n_clusters not specified, uses sqrt(n_samples) heuristic.
        """
        # Auto-calculate k if not provided
        if self.n_clusters is None:
            self.n_clusters = int(np.sqrt(embeddings.shape[0]))
            logger.info(f"Auto-calculated n_clusters = {self.n_clusters}")

        # Normalize embeddings for better clustering with cosine similarity
        logger.info("Normalizing embeddings (L2 norm)...")
        normalized_embeddings = normalize(embeddings, norm='l2')

        logger.info(f"Running K-Means (k={self.n_clusters})...")
        self.clusterer = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init=10,  # Multiple initializations for stability
        )

        labels = self.clusterer.fit_predict(normalized_embeddings)

        return labels

    def _compute_statistics(self):
        """Compute clustering statistics after fit."""
        if self.labels_ is None:
            return

        # Count unique clusters (excluding noise if HDBSCAN)
        unique_labels = set(self.labels_)
        if -1 in unique_labels:
            # HDBSCAN noise points
            self.n_clusters_found = len(unique_labels) - 1
            self.n_noise_points = np.sum(self.labels_ == -1)
        else:
            self.n_clusters_found = len(unique_labels)
            self.n_noise_points = 0

        logger.info(
            f"Clustering complete: {self.n_clusters_found} clusters found, "
            f"{self.n_noise_points} noise points"
        )

    def compute_quality_metrics(self, embeddings: np.ndarray) -> Dict[str, float]:
        """
        Compute clustering quality metrics.

        Args:
            embeddings: Original embeddings used for clustering

        Returns:
            Dictionary with quality metrics (silhouette_score, etc.)

        Raises:
            ValueError: If clustering hasn't been performed yet
        """
        if self.labels_ is None:
            raise ValueError("Must call fit_predict() before computing metrics")

        metrics = {}

        # Silhouette score (requires at least 2 clusters)
        if self.n_clusters_found >= 2:
            # Filter out noise points for silhouette calculation
            mask = self.labels_ != -1
            if np.sum(mask) > 0:
                try:
                    score = silhouette_score(
                        embeddings[mask],
                        self.labels_[mask],
                        metric='cosine'
                    )
                    metrics['silhouette_score'] = float(score)
                    logger.info(f"Silhouette score: {score:.3f}")
                except Exception as e:
                    logger.warning(f"Failed to compute silhouette score: {e}")
                    metrics['silhouette_score'] = None
            else:
                metrics['silhouette_score'] = None
        else:
            logger.warning("Too few clusters for silhouette score")
            metrics['silhouette_score'] = None

        # K-Means specific: inertia (within-cluster sum of squares)
        if self.algorithm == 'kmeans' and hasattr(self.clusterer, 'inertia_'):
            metrics['inertia'] = float(self.clusterer.inertia_)

        # Cluster size statistics
        cluster_sizes = []
        for label in set(self.labels_):
            if label != -1:  # Exclude noise
                cluster_sizes.append(np.sum(self.labels_ == label))

        if cluster_sizes:
            metrics['min_cluster_size'] = int(min(cluster_sizes))
            metrics['max_cluster_size'] = int(max(cluster_sizes))
            metrics['mean_cluster_size'] = float(np.mean(cluster_sizes))
            metrics['median_cluster_size'] = float(np.median(cluster_sizes))

        metrics['n_clusters'] = self.n_clusters_found
        metrics['n_noise_points'] = self.n_noise_points

        return metrics

    def get_cluster_members(self, cluster_id: int) -> np.ndarray:
        """
        Get indices of all members in a specific cluster.

        Args:
            cluster_id: Cluster label to retrieve members for

        Returns:
            Array of indices belonging to the cluster
        """
        if self.labels_ is None:
            raise ValueError("Must call fit_predict() before getting members")

        return np.where(self.labels_ == cluster_id)[0]

    def assign_to_existing_clusters(
        self,
        new_embeddings: np.ndarray,
        existing_embeddings: np.ndarray,
        existing_labels: np.ndarray
    ) -> np.ndarray:
        """
        Assign new embeddings to existing clusters based on nearest neighbors.

        Used for delta processing: assign new chunks to existing cluster structure.

        Args:
            new_embeddings: New embedding vectors to assign (n_new, n_features)
            existing_embeddings: Existing embedding vectors (n_existing, n_features)
            existing_labels: Cluster labels for existing embeddings

        Returns:
            Cluster labels for new embeddings
        """
        logger.info(
            f"Assigning {len(new_embeddings)} new embeddings to existing clusters..."
        )

        # Compute distance from each new embedding to all existing embeddings
        distances = cosine_distances(new_embeddings, existing_embeddings)

        # For each new embedding, find nearest existing embedding
        nearest_indices = np.argmin(distances, axis=1)

        # Assign same cluster as nearest neighbor
        new_labels = existing_labels[nearest_indices]

        # Log assignments
        for label in set(new_labels):
            count = np.sum(new_labels == label)
            logger.info(f"  Assigned {count} new items to cluster {label}")

        return new_labels


def create_cluster_mapping(
    chunk_ids: List[str],
    cluster_labels: np.ndarray
) -> Dict[str, List[str]]:
    """
    Create mapping from chunk IDs to cluster IDs.

    Args:
        chunk_ids: List of chunk document IDs
        cluster_labels: Array of cluster labels (same length as chunk_ids)

    Returns:
        Dictionary mapping chunk_id -> [cluster_id, ...] (list for multi-cluster support)
    """
    if len(chunk_ids) != len(cluster_labels):
        raise ValueError(
            f"Mismatch: {len(chunk_ids)} chunk IDs but {len(cluster_labels)} labels"
        )

    mapping = {}
    for chunk_id, label in zip(chunk_ids, cluster_labels):
        # Convert cluster label to string ID
        # For noise points (-1), use "noise" as cluster ID
        if label == -1:
            cluster_id = "noise"
        else:
            cluster_id = f"cluster-{label}"

        # Store as list to support multi-cluster membership in future
        mapping[chunk_id] = [cluster_id]

    return mapping
