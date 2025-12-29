"""
Unit tests for cluster relationship discovery (Story 3.4).

Tests the get_related_clusters() function that uses Firestore vector search
on cluster centroids to find conceptually related clusters.
"""

import unittest
from unittest.mock import patch, MagicMock

from src.mcp_server import tools


class TestGetRelatedClusters(unittest.TestCase):
    """Test suite for get_related_clusters() function."""

    @patch('src.mcp_server.tools.firestore_client.get_firestore_client')
    @patch('src.mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_related_clusters_success(self, mock_get_cluster, mock_get_db):
        """Test successful cluster relationship discovery."""
        # Mock source cluster
        mock_get_cluster.return_value = {
            'name': 'Semantic Search',
            'description': 'Notes about semantic search techniques',
            'centroid': [0.1] * 768,
            'chunk_count': 15
        }

        # Mock Firestore vector query results
        mock_doc1 = MagicMock()
        mock_doc1.id = 'cluster_18'
        mock_doc1.to_dict.return_value = {
            'name': 'Personal Knowledge Management',
            'description': 'PKM systems and practices',
            'chunk_count': 31
        }
        mock_doc1.get.return_value = 0.26  # Distance for ~87% similarity

        mock_doc2 = MagicMock()
        mock_doc2.id = 'cluster_25'
        mock_doc2.to_dict.return_value = {
            'name': 'MCP and AI Context',
            'description': 'Model Context Protocol patterns',
            'chunk_count': 12
        }
        mock_doc2.get.return_value = 0.36  # Distance for ~82% similarity

        # Mock db.collection().find_nearest().stream()
        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_doc1, mock_doc2]

        mock_collection = MagicMock()
        mock_collection.find_nearest.return_value = mock_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        # Execute
        result = tools.get_related_clusters(cluster_id='cluster_12', limit=5)

        # Assertions
        self.assertEqual(result['source_cluster']['cluster_id'], 'cluster_12')
        self.assertEqual(result['source_cluster']['name'], 'Semantic Search')
        self.assertEqual(result['result_count'], 2)
        self.assertEqual(len(result['results']), 2)

        # Check first related cluster
        self.assertEqual(result['results'][0]['cluster_id'], 'cluster_18')
        self.assertEqual(result['results'][0]['name'], 'Personal Knowledge Management')
        self.assertIn('similarity_score', result['results'][0])

        # Verify mocks
        mock_get_cluster.assert_called_once_with('cluster_12')
        mock_collection.find_nearest.assert_called_once()

    @patch('src.mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_related_clusters_not_found(self, mock_get_cluster):
        """Test error handling for non-existent cluster."""
        mock_get_cluster.return_value = None

        result = tools.get_related_clusters(cluster_id='invalid_cluster', limit=5)

        # Returns error dict, not raises ValueError
        self.assertIn('error', result)
        self.assertIn('not found', result['error'])
        self.assertEqual(result['result_count'], 0)

    @patch('src.mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_related_clusters_no_centroid(self, mock_get_cluster):
        """Test error handling for cluster without centroid."""
        mock_get_cluster.return_value = {
            'name': 'Test Cluster',
            'description': 'A cluster without centroid',
            'chunk_count': 10
            # Note: no 'centroid' field
        }

        result = tools.get_related_clusters(cluster_id='cluster_without_centroid', limit=5)

        # Returns error dict, not raises ValueError
        self.assertIn('error', result)
        self.assertIn('centroid', result['error'].lower())
        self.assertEqual(result['result_count'], 0)

    @patch('src.mcp_server.tools.firestore_client.get_firestore_client')
    @patch('src.mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_related_clusters_filters_noise(self, mock_get_cluster, mock_get_db):
        """Test that noise clusters are filtered from results."""
        # Mock source cluster
        mock_get_cluster.return_value = {
            'name': 'Regular Cluster',
            'description': 'A normal cluster',
            'centroid': [0.1] * 768,
            'chunk_count': 10
        }

        # Mock results including noise cluster
        mock_noise = MagicMock()
        mock_noise.id = '-1'
        mock_noise.to_dict.return_value = {
            'name': 'Noise Cluster',
            'description': 'Unclustered items',
            'chunk_count': 50
        }
        mock_noise.get.return_value = 0.1

        mock_valid = MagicMock()
        mock_valid.id = 'cluster_5'
        mock_valid.to_dict.return_value = {
            'name': 'Valid Cluster',
            'description': 'A real cluster',
            'chunk_count': 20
        }
        mock_valid.get.return_value = 0.3

        mock_noise_named = MagicMock()
        mock_noise_named.id = 'cluster_99'
        mock_noise_named.to_dict.return_value = {
            'name': 'Noise - Uncategorized',
            'description': 'Another noise cluster',
            'chunk_count': 30
        }
        mock_noise_named.get.return_value = 0.2

        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_noise, mock_valid, mock_noise_named]

        mock_collection = MagicMock()
        mock_collection.find_nearest.return_value = mock_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        # Execute
        result = tools.get_related_clusters(cluster_id='cluster_1', limit=5)

        # Should only include the valid cluster, not noise clusters
        self.assertEqual(result['result_count'], 1)
        self.assertEqual(result['results'][0]['cluster_id'], 'cluster_5')
        self.assertEqual(result['results'][0]['name'], 'Valid Cluster')

    @patch('src.mcp_server.tools.firestore_client.get_firestore_client')
    @patch('src.mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_related_clusters_distance_measures(self, mock_get_cluster, mock_get_db):
        """Test different distance measures."""
        # Mock source cluster
        mock_get_cluster.return_value = {
            'name': 'Test Cluster',
            'centroid': [0.1] * 768,
            'chunk_count': 10
        }

        mock_doc = MagicMock()
        mock_doc.id = 'cluster_2'
        mock_doc.to_dict.return_value = {
            'name': 'Related Cluster',
            'description': 'Test',
            'chunk_count': 5
        }
        mock_doc.get.return_value = 0.5

        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_doc]

        mock_collection = MagicMock()
        mock_collection.find_nearest.return_value = mock_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        # Test COSINE (default)
        result_cosine = tools.get_related_clusters(
            cluster_id='cluster_1',
            limit=5,
            distance_measure='COSINE'
        )
        self.assertIn('similarity_score', result_cosine['results'][0])

        # Test EUCLIDEAN
        result_euclidean = tools.get_related_clusters(
            cluster_id='cluster_1',
            limit=5,
            distance_measure='EUCLIDEAN'
        )
        self.assertIn('similarity_score', result_euclidean['results'][0])

        # Test DOT_PRODUCT
        result_dot = tools.get_related_clusters(
            cluster_id='cluster_1',
            limit=5,
            distance_measure='DOT_PRODUCT'
        )
        self.assertIn('similarity_score', result_dot['results'][0])

    def test_get_related_clusters_limit_validation(self):
        """Test that limit is validated (1-20 range)."""
        # Test limit too low
        result_low = tools.get_related_clusters(cluster_id='cluster_1', limit=0)
        self.assertIn('error', result_low)
        self.assertIn('Limit', result_low['error'])

        # Test limit too high
        result_high = tools.get_related_clusters(cluster_id='cluster_1', limit=21)
        self.assertIn('error', result_high)
        self.assertIn('Limit', result_high['error'])


class TestClusterRelationshipsIntegration(unittest.TestCase):
    """Integration-style tests for cluster relationships (require real Firestore)."""

    @unittest.skip("Requires real Firestore connection - run manually")
    def test_real_cluster_search(self):
        """Integration test with real Firestore vector search."""
        # This would require actual GCP credentials
        result = tools.get_related_clusters(cluster_id='cluster_0', limit=3)
        
        # Verify structure
        self.assertIn('source_cluster', result)
        self.assertIn('results', result)
        self.assertIn('result_count', result)
        
        # Log results for manual verification
        print(f"Source: {result['source_cluster']['name']}")
        for related in result['results']:
            print(f"  -> {related['name']} ({related['similarity_score']})")


if __name__ == '__main__':
    unittest.main()
