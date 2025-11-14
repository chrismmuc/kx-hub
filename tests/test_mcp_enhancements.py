"""
Unit tests for Story 2.6: MCP Server Enhancements - Knowledge Cards & Clusters.

Tests new knowledge card and cluster tools, plus enhanced existing tools.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))
# Add mcp_server to path so firestore_client and embeddings can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src/mcp_server'))

from mcp_server import tools


class TestKnowledgeCardTools(unittest.TestCase):
    """Test suite for knowledge card tools (AC #2)."""

    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_knowledge_card_success(self, mock_get_chunk):
        """Test get_knowledge_card returns summary and takeaways (AC #2)."""
        # Mock chunk with knowledge card
        mock_get_chunk.return_value = {
            'id': 'test-chunk-1',
            'title': 'Atomic Habits',
            'author': 'James Clear',
            'source': 'kindle',
            'knowledge_card': {
                'summary': 'Small habits compound over time to create remarkable results.',
                'takeaways': [
                    'Focus on systems, not goals',
                    'Make habits obvious, attractive, easy, and satisfying',
                    '1% improvement daily leads to 37x improvement in a year'
                ]
            }
        }

        result = tools.get_knowledge_card('test-chunk-1')

        # Verify result structure
        self.assertEqual(result['chunk_id'], 'test-chunk-1')
        self.assertEqual(result['title'], 'Atomic Habits')
        self.assertIn('knowledge_card', result)
        self.assertIn('summary', result['knowledge_card'])
        self.assertIn('takeaways', result['knowledge_card'])
        self.assertEqual(len(result['knowledge_card']['takeaways']), 3)

    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_knowledge_card_missing(self, mock_get_chunk):
        """Test get_knowledge_card handles missing knowledge card (AC #8)."""
        # Mock chunk without knowledge card
        mock_get_chunk.return_value = {
            'id': 'test-chunk-2',
            'title': 'Test Book',
            'author': 'Test Author',
            'source': 'reader'
        }

        result = tools.get_knowledge_card('test-chunk-2')

        # Should return error when knowledge card is missing
        self.assertIn('error', result)
        self.assertIn('not available', result['error'])

    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_knowledge_card_chunk_not_found(self, mock_get_chunk):
        """Test get_knowledge_card handles non-existent chunk (AC #8)."""
        mock_get_chunk.return_value = None

        result = tools.get_knowledge_card('non-existent-chunk')

        self.assertIn('error', result)
        self.assertIn('not found', result['error'])

    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    def test_search_knowledge_cards_success(self, mock_find_nearest, mock_generate_embedding):
        """Test search_knowledge_cards returns only summaries (AC #2)."""
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock results with knowledge cards
        mock_find_nearest.return_value = [
            {
                'id': 'chunk-1',
                'title': 'Book 1',
                'author': 'Author 1',
                'source': 'kindle',
                'knowledge_card': {
                    'summary': 'Summary 1',
                    'takeaways': ['Takeaway A', 'Takeaway B']
                }
            },
            {
                'id': 'chunk-2',
                'title': 'Book 2',
                'author': 'Author 2',
                'source': 'reader',
                'knowledge_card': {
                    'summary': 'Summary 2',
                    'takeaways': ['Takeaway C']
                }
            }
        ]

        result = tools.search_knowledge_cards('productivity tips', limit=10)

        # Verify results contain only knowledge card data, not full content
        self.assertEqual(result['result_count'], 2)
        self.assertEqual(len(result['results']), 2)

        # Verify first result has knowledge card
        first_result = result['results'][0]
        self.assertIn('knowledge_card', first_result)
        self.assertEqual(first_result['knowledge_card']['summary'], 'Summary 1')
        self.assertEqual(len(first_result['knowledge_card']['takeaways']), 2)

        # Verify no full content in results
        self.assertNotIn('full_content', first_result)
        self.assertNotIn('snippet', first_result)


class TestClusterTools(unittest.TestCase):
    """Test suite for cluster discovery tools (AC #3)."""

    @patch('mcp_server.tools.firestore_client.get_all_clusters')
    def test_list_clusters_success(self, mock_get_all_clusters):
        """Test list_clusters returns all clusters sorted by size (AC #3)."""
        mock_get_all_clusters.return_value = [
            {
                'id': 'cluster-1',
                'name': 'Productivity & Habits',
                'description': 'Personal development and habit formation',
                'size': 120,
                'created_at': '2025-01-15'
            },
            {
                'id': 'cluster-2',
                'name': 'AI & Machine Learning',
                'description': 'Artificial intelligence concepts and applications',
                'size': 85,
                'created_at': '2025-01-16'
            }
        ]

        result = tools.list_clusters()

        self.assertEqual(result['cluster_count'], 2)
        self.assertEqual(len(result['clusters']), 2)

        # Verify first cluster
        first_cluster = result['clusters'][0]
        self.assertEqual(first_cluster['cluster_id'], 'cluster-1')
        self.assertEqual(first_cluster['name'], 'Productivity & Habits')
        self.assertEqual(first_cluster['size'], 120)

    @patch('mcp_server.tools.firestore_client.get_all_clusters')
    def test_list_clusters_handles_noise(self, mock_get_all_clusters):
        """Test list_clusters handles noise cluster appropriately (AC #8)."""
        mock_get_all_clusters.return_value = [
            {
                'id': 'noise',
                'name': 'Noise Cluster',
                'size': 15
            }
        ]

        result = tools.list_clusters()

        self.assertEqual(result['cluster_count'], 1)
        noise_cluster = result['clusters'][0]
        self.assertEqual(noise_cluster['cluster_id'], 'noise')
        self.assertEqual(noise_cluster['name'], 'Outliers / Noise')
        self.assertIn('do not fit', noise_cluster['description'].lower())

    @patch('mcp_server.tools.firestore_client.get_chunks_by_cluster')
    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_with_members(self, mock_get_cluster, mock_get_chunks):
        """Test get_cluster returns metadata and member chunks (AC #3)."""
        mock_get_cluster.return_value = {
            'id': 'cluster-1',
            'name': 'Productivity',
            'description': 'Time management and productivity techniques',
            'size': 50,
            'created_at': '2025-01-15'
        }

        mock_get_chunks.return_value = [
            {
                'id': 'chunk-1',
                'title': 'Atomic Habits',
                'author': 'James Clear',
                'source': 'kindle',
                'knowledge_card': {
                    'summary': 'Habits compound over time',
                    'takeaways': ['Focus on systems']
                }
            }
        ]

        result = tools.get_cluster('cluster-1', include_chunks=True, limit=20)

        self.assertEqual(result['cluster_id'], 'cluster-1')
        self.assertEqual(result['name'], 'Productivity')
        self.assertEqual(result['size'], 50)
        self.assertIn('members', result)
        self.assertEqual(result['member_count'], 1)

        # Verify member includes knowledge card
        member = result['members'][0]
        self.assertIn('knowledge_card', member)

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_not_found(self, mock_get_cluster):
        """Test get_cluster handles non-existent cluster (AC #8)."""
        mock_get_cluster.return_value = None

        result = tools.get_cluster('non-existent-cluster')

        self.assertIn('error', result)
        self.assertIn('not found', result['error'])

    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    @patch('mcp_server.tools.firestore_client.search_within_cluster')
    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_search_within_cluster_success(self, mock_get_cluster, mock_search, mock_generate_embedding):
        """Test search_within_cluster filters to cluster members (AC #3)."""
        mock_get_cluster.return_value = {
            'id': 'cluster-1',
            'name': 'Productivity'
        }

        mock_generate_embedding.return_value = [0.1] * 768

        mock_search.return_value = [
            {
                'id': 'chunk-1',
                'title': 'Deep Work',
                'author': 'Cal Newport',
                'source': 'kindle',
                'content': 'Focus is a superpower in the modern economy.',
                'knowledge_card': {
                    'summary': 'Deep focus enables high-quality work',
                    'takeaways': ['Eliminate distractions']
                }
            }
        ]

        result = tools.search_within_cluster_tool('cluster-1', 'focus techniques', limit=10)

        self.assertEqual(result['cluster_id'], 'cluster-1')
        self.assertEqual(result['cluster_name'], 'Productivity')
        self.assertEqual(result['query'], 'focus techniques')
        self.assertEqual(result['result_count'], 1)

        # Verify result includes knowledge card
        first_result = result['results'][0]
        self.assertIn('knowledge_card', first_result)


class TestEnhancedSearchTools(unittest.TestCase):
    """Test suite for enhanced existing tools with knowledge cards and clusters (AC #1, #6)."""

    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_search_semantic_includes_knowledge_card_and_cluster(self, mock_get_cluster, mock_find_nearest, mock_generate_embedding):
        """Test search_semantic includes knowledge_card and cluster fields (AC #1)."""
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock cluster lookup
        mock_get_cluster.return_value = {
            'id': 'cluster-1',
            'name': 'Productivity',
            'description': 'Time management techniques'
        }

        # Mock search results
        mock_find_nearest.return_value = [
            {
                'id': 'chunk-1',
                'title': 'Test Book',
                'author': 'Test Author',
                'source': 'kindle',
                'tags': ['productivity'],
                'content': 'Test content here.',
                'chunk_index': 0,
                'total_chunks': 1,
                'knowledge_card': {
                    'summary': 'This is a test summary',
                    'takeaways': ['Takeaway 1', 'Takeaway 2']
                },
                'cluster_id': ['cluster-1']
            }
        ]

        result = tools.search_semantic('productivity tips', limit=10)

        # Verify backward compatibility (AC #6)
        self.assertIn('results', result)
        self.assertEqual(len(result['results']), 1)

        first_result = result['results'][0]

        # Verify original fields still present
        self.assertIn('chunk_id', first_result)
        self.assertIn('title', first_result)
        self.assertIn('author', first_result)
        self.assertIn('snippet', first_result)
        self.assertIn('full_content', first_result)

        # Verify new fields added (AC #1)
        self.assertIn('knowledge_card', first_result)
        self.assertIn('cluster', first_result)

        # Verify knowledge_card structure
        self.assertEqual(first_result['knowledge_card']['summary'], 'This is a test summary')
        self.assertEqual(len(first_result['knowledge_card']['takeaways']), 2)

        # Verify cluster structure
        self.assertEqual(first_result['cluster']['cluster_id'], 'cluster-1')
        self.assertEqual(first_result['cluster']['name'], 'Productivity')

    @patch('mcp_server.tools.firestore_client.query_by_metadata')
    def test_search_by_metadata_includes_new_fields(self, mock_query):
        """Test search_by_metadata includes knowledge_card and cluster fields (AC #1)."""
        mock_query.return_value = [
            {
                'id': 'chunk-1',
                'title': 'Test Book',
                'author': 'Test Author',
                'source': 'kindle',
                'tags': ['psychology'],
                'content': 'Test content',
                'chunk_index': 0,
                'total_chunks': 1,
                'knowledge_card': {
                    'summary': 'Test summary',
                    'takeaways': []
                },
                'cluster_id': []  # No cluster assigned
            }
        ]

        result = tools.search_by_metadata(tags=['psychology'], limit=20)

        first_result = result['results'][0]
        self.assertIn('knowledge_card', first_result)
        self.assertIn('cluster', first_result)

        # Verify missing cluster handled gracefully (AC #8)
        self.assertIsNone(first_result['cluster'])

    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    def test_get_related_chunks_includes_new_fields(self, mock_find_nearest, mock_get_chunk):
        """Test get_related_chunks includes knowledge_card and cluster fields (AC #1)."""
        # Mock source chunk
        mock_get_chunk.return_value = {
            'id': 'source-chunk',
            'title': 'Source Book',
            'embedding': [0.1] * 768
        }

        # Mock related chunks
        mock_find_nearest.return_value = [
            {
                'id': 'source-chunk'  # Will be filtered out
            },
            {
                'id': 'related-chunk-1',
                'title': 'Related Book',
                'author': 'Author',
                'source': 'kindle',
                'content': 'Related content',
                'chunk_index': 0,
                'total_chunks': 1,
                'knowledge_card': {
                    'summary': 'Related summary',
                    'takeaways': ['Related takeaway']
                },
                'cluster_id': ['noise']  # Noise cluster
            }
        ]

        result = tools.get_related_chunks('source-chunk', limit=5)

        self.assertEqual(len(result['results']), 1)
        first_result = result['results'][0]

        self.assertIn('knowledge_card', first_result)
        self.assertIn('cluster', first_result)

        # Verify noise cluster handled specially (AC #8)
        self.assertEqual(first_result['cluster']['cluster_id'], 'noise')
        self.assertEqual(first_result['cluster']['name'], 'Outliers / Noise')


class TestEdgeCases(unittest.TestCase):
    """Test edge case handling (AC #8)."""

    @patch('mcp_server.tools.firestore_client.find_nearest')
    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    def test_missing_knowledge_card_handled_gracefully(self, mock_generate_embedding, mock_find_nearest):
        """Test that missing knowledge_card field doesn't break search (AC #8)."""
        mock_generate_embedding.return_value = [0.1] * 768

        mock_find_nearest.return_value = [
            {
                'id': 'chunk-without-card',
                'title': 'Old Chunk',
                'author': 'Author',
                'source': 'kindle',
                'tags': [],
                'content': 'Content without knowledge card',
                'chunk_index': 0,
                'total_chunks': 1
                # No knowledge_card field
            }
        ]

        result = tools.search_semantic('test query', limit=10)

        # Should not crash, should return None for knowledge_card
        first_result = result['results'][0]
        self.assertIsNone(first_result['knowledge_card'])

    @patch('mcp_server.tools.firestore_client.find_nearest')
    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    def test_missing_cluster_handled_gracefully(self, mock_generate_embedding, mock_find_nearest):
        """Test that missing cluster_id field doesn't break search (AC #8)."""
        mock_generate_embedding.return_value = [0.1] * 768

        mock_find_nearest.return_value = [
            {
                'id': 'chunk-without-cluster',
                'title': 'Unclustered Chunk',
                'author': 'Author',
                'source': 'reader',
                'tags': [],
                'content': 'Content without cluster',
                'chunk_index': 0,
                'total_chunks': 1,
                'knowledge_card': {
                    'summary': 'Has summary',
                    'takeaways': []
                }
                # No cluster_id field
            }
        ]

        result = tools.search_semantic('test query', limit=10)

        # Should not crash, should return None for cluster
        first_result = result['results'][0]
        self.assertIsNone(first_result['cluster'])


if __name__ == '__main__':
    unittest.main()
