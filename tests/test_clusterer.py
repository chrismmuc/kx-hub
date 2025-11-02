"""
Unit tests for clustering module.

Tests clustering algorithms, quality metrics, and helper functions.
"""

import unittest
import numpy as np
from unittest.mock import Mock, patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from clustering.clusterer import SemanticClusterer, create_cluster_mapping


class TestSemanticClusterer(unittest.TestCase):
    """Test SemanticClusterer class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create synthetic embeddings (3 groups of similar vectors)
        np.random.seed(42)

        # Group 1: embeddings around [1, 0, 0, ...]
        group1 = np.random.randn(5, 768) * 0.1
        group1[:, 0] += 1.0

        # Group 2: embeddings around [0, 1, 0, ...]
        group2 = np.random.randn(5, 768) * 0.1
        group2[:, 1] += 1.0

        # Group 3: embeddings around [0, 0, 1, ...]
        group3 = np.random.randn(5, 768) * 0.1
        group3[:, 2] += 1.0

        self.synthetic_embeddings = np.vstack([group1, group2, group3])
        self.expected_groups = 3

    def test_initialization(self):
        """Test clusterer initialization."""
        clusterer = SemanticClusterer(
            algorithm='hdbscan',
            min_cluster_size=3,
            min_samples=2
        )

        self.assertEqual(clusterer.algorithm, 'hdbscan')
        self.assertEqual(clusterer.min_cluster_size, 3)
        self.assertEqual(clusterer.min_samples, 2)
        self.assertIsNone(clusterer.labels_)

    def test_hdbscan_clustering(self):
        """Test HDBSCAN clustering with synthetic data."""
        clusterer = SemanticClusterer(
            algorithm='hdbscan',
            min_cluster_size=3,
            min_samples=2
        )

        labels = clusterer.fit_predict(self.synthetic_embeddings)

        # Should find 3 clusters
        unique_labels = set(labels)
        # Remove noise label if present
        if -1 in unique_labels:
            unique_labels.remove(-1)

        self.assertGreaterEqual(len(unique_labels), 2)  # At least 2 clusters
        self.assertLessEqual(len(unique_labels), 4)  # At most 4 clusters

        # Check labels array shape
        self.assertEqual(labels.shape[0], len(self.synthetic_embeddings))

    def test_kmeans_clustering(self):
        """Test K-Means clustering with synthetic data."""
        clusterer = SemanticClusterer(
            algorithm='kmeans',
            n_clusters=3
        )

        labels = clusterer.fit_predict(self.synthetic_embeddings)

        # Should find exactly 3 clusters
        unique_labels = set(labels)
        self.assertEqual(len(unique_labels), 3)

        # No noise points in K-Means
        self.assertNotIn(-1, labels)

    def test_auto_kmeans_clusters(self):
        """Test K-Means with auto-calculated cluster count."""
        clusterer = SemanticClusterer(
            algorithm='kmeans',
            n_clusters=None  # Auto-calculate
        )

        labels = clusterer.fit_predict(self.synthetic_embeddings)

        # Should auto-calculate k = sqrt(15) ≈ 3
        self.assertIsNotNone(clusterer.n_clusters)
        self.assertGreater(clusterer.n_clusters, 0)

    def test_invalid_algorithm(self):
        """Test error handling for invalid algorithm."""
        clusterer = SemanticClusterer(algorithm='invalid')

        with self.assertRaises(ValueError):
            clusterer.fit_predict(self.synthetic_embeddings)

    def test_empty_embeddings(self):
        """Test error handling for empty embeddings."""
        clusterer = SemanticClusterer()

        with self.assertRaises(ValueError):
            clusterer.fit_predict(np.array([]))

    def test_wrong_dimension_embeddings(self):
        """Test error handling for wrong dimension."""
        clusterer = SemanticClusterer()

        # 1D array instead of 2D
        with self.assertRaises(ValueError):
            clusterer.fit_predict(np.array([1, 2, 3]))

    def test_quality_metrics(self):
        """Test clustering quality metrics computation."""
        clusterer = SemanticClusterer(algorithm='hdbscan', min_cluster_size=3)
        clusterer.fit_predict(self.synthetic_embeddings)

        metrics = clusterer.compute_quality_metrics(self.synthetic_embeddings)

        # Check required metrics
        self.assertIn('n_clusters', metrics)
        self.assertIn('n_noise_points', metrics)

        # Silhouette score should be present if 2+ clusters
        if clusterer.n_clusters_found >= 2:
            self.assertIn('silhouette_score', metrics)
            if metrics['silhouette_score'] is not None:
                self.assertGreaterEqual(metrics['silhouette_score'], -1.0)
                self.assertLessEqual(metrics['silhouette_score'], 1.0)

    def test_quality_metrics_before_fit(self):
        """Test error when computing metrics before fit."""
        clusterer = SemanticClusterer()

        with self.assertRaises(ValueError):
            clusterer.compute_quality_metrics(self.synthetic_embeddings)

    def test_get_cluster_members(self):
        """Test retrieving cluster members."""
        clusterer = SemanticClusterer(algorithm='kmeans', n_clusters=3)
        labels = clusterer.fit_predict(self.synthetic_embeddings)

        # Get members of first cluster
        cluster_0_members = clusterer.get_cluster_members(0)

        self.assertGreater(len(cluster_0_members), 0)
        self.assertTrue(np.all(labels[cluster_0_members] == 0))

    def test_assign_to_existing_clusters(self):
        """Test assigning new embeddings to existing clusters."""
        clusterer = SemanticClusterer(algorithm='kmeans', n_clusters=3)

        # Split data: use first 12 for training, last 3 for testing
        train_embeddings = self.synthetic_embeddings[:12]
        test_embeddings = self.synthetic_embeddings[12:]

        # Cluster training data
        train_labels = clusterer.fit_predict(train_embeddings)

        # Assign test data to existing clusters
        test_labels = clusterer.assign_to_existing_clusters(
            test_embeddings, train_embeddings, train_labels
        )

        # Should get labels for all test embeddings
        self.assertEqual(len(test_labels), len(test_embeddings))

        # Labels should be valid (exist in training labels)
        self.assertTrue(np.all(np.isin(test_labels, train_labels)))


class TestClusterMapping(unittest.TestCase):
    """Test cluster mapping helper functions."""

    def test_create_cluster_mapping(self):
        """Test creating cluster mapping from chunk IDs and labels."""
        chunk_ids = ['chunk-1', 'chunk-2', 'chunk-3']
        cluster_labels = np.array([0, 1, 0])

        mapping = create_cluster_mapping(chunk_ids, cluster_labels)

        self.assertEqual(len(mapping), 3)
        self.assertEqual(mapping['chunk-1'], ['cluster-0'])
        self.assertEqual(mapping['chunk-2'], ['cluster-1'])
        self.assertEqual(mapping['chunk-3'], ['cluster-0'])

    def test_cluster_mapping_with_noise(self):
        """Test cluster mapping handles noise points."""
        chunk_ids = ['chunk-1', 'chunk-2', 'chunk-3']
        cluster_labels = np.array([0, -1, 1])  # chunk-2 is noise

        mapping = create_cluster_mapping(chunk_ids, cluster_labels)

        self.assertEqual(mapping['chunk-1'], ['cluster-0'])
        self.assertEqual(mapping['chunk-2'], ['noise'])
        self.assertEqual(mapping['chunk-3'], ['cluster-1'])

    def test_cluster_mapping_length_mismatch(self):
        """Test error handling for mismatched lengths."""
        chunk_ids = ['chunk-1', 'chunk-2']
        cluster_labels = np.array([0, 1, 2])  # Wrong length

        with self.assertRaises(ValueError):
            create_cluster_mapping(chunk_ids, cluster_labels)


if __name__ == '__main__':
    unittest.main()
