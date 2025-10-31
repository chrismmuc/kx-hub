"""
Unit tests for MCP server tools.

Mocks Firestore and Vertex AI to test tool logic without GCP dependencies.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from mcp_server import tools


class TestMCPTools(unittest.TestCase):
    """Test suite for MCP search tools."""

    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    def test_search_semantic_success(self, mock_find_nearest, mock_generate_embedding):
        """Test semantic search with successful query."""
        # Mock embedding generation
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock Firestore results
        mock_find_nearest.return_value = [
            {
                'id': 'test-chunk-1',
                'chunk_id': 'test-chunk-1',
                'title': 'Test Book',
                'author': 'Test Author',
                'source': 'kindle',
                'tags': ['psychology'],
                'content': 'This is test content for chunk 1.',
                'chunk_index': 0,
                'total_chunks': 3
            },
            {
                'id': 'test-chunk-2',
                'chunk_id': 'test-chunk-2',
                'title': 'Another Book',
                'author': 'Another Author',
                'source': 'reader',
                'tags': ['business'],
                'content': 'This is test content for chunk 2.',
                'chunk_index': 1,
                'total_chunks': 2
            }
        ]

        # Execute search
        result = tools.search_semantic(query="test query", limit=10)

        # Assertions
        self.assertEqual(result['query'], "test query")
        self.assertEqual(result['result_count'], 2)
        self.assertEqual(result['limit'], 10)
        self.assertEqual(len(result['results']), 2)

        # Check first result
        self.assertEqual(result['results'][0]['chunk_id'], 'test-chunk-1')
        self.assertEqual(result['results'][0]['title'], 'Test Book')
        self.assertEqual(result['results'][0]['rank'], 1)

        # Verify mocks called
        mock_generate_embedding.assert_called_once_with("test query")
        mock_find_nearest.assert_called_once()

    @patch('mcp_server.tools.firestore_client.query_by_metadata')
    def test_search_by_metadata_with_tags(self, mock_query):
        """Test metadata search with tag filter."""
        # Mock Firestore results
        mock_query.return_value = [
            {
                'id': 'tagged-chunk',
                'chunk_id': 'tagged-chunk',
                'title': 'Tagged Book',
                'author': 'Tag Author',
                'source': 'kindle',
                'tags': ['productivity', 'self-improvement'],
                'content': 'Content about productivity.',
                'chunk_index': 0,
                'total_chunks': 1
            }
        ]

        # Execute search
        result = tools.search_by_metadata(tags=['productivity'], limit=20)

        # Assertions
        self.assertEqual(result['result_count'], 1)
        self.assertEqual(result['results'][0]['tags'], ['productivity', 'self-improvement'])

        # Verify mock called
        mock_query.assert_called_once_with(
            tags=['productivity'],
            author=None,
            source=None,
            limit=20
        )

    @patch('mcp_server.tools.firestore_client.query_by_metadata')
    def test_search_by_metadata_no_filters(self, mock_query):
        """Test metadata search requires at least one filter."""
        result = tools.search_by_metadata(limit=20)

        self.assertIn('error', result)
        self.assertEqual(result['result_count'], 0)

        # Should not call Firestore
        mock_query.assert_not_called()

    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    def test_get_related_chunks_success(self, mock_find_nearest, mock_get_chunk):
        """Test finding related chunks."""
        # Mock source chunk
        mock_get_chunk.return_value = {
            'id': 'source-chunk',
            'chunk_id': 'source-chunk',
            'title': 'Source Book',
            'author': 'Source Author',
            'embedding': [0.5] * 768,  # Mock embedding
            'content': 'Source content'
        }

        # Mock related chunks
        mock_find_nearest.return_value = [
            {
                'id': 'source-chunk',  # Will be filtered out
                'chunk_id': 'source-chunk',
                'title': 'Source Book',
                'author': 'Source Author',
                'content': 'Source content',
                'chunk_index': 0,
                'total_chunks': 1
            },
            {
                'id': 'related-chunk-1',
                'chunk_id': 'related-chunk-1',
                'title': 'Related Book 1',
                'author': 'Related Author',
                'source': 'kindle',
                'content': 'Related content 1',
                'chunk_index': 0,
                'total_chunks': 1
            },
            {
                'id': 'related-chunk-2',
                'chunk_id': 'related-chunk-2',
                'title': 'Related Book 2',
                'author': 'Related Author',
                'source': 'reader',
                'content': 'Related content 2',
                'chunk_index': 0,
                'total_chunks': 1
            }
        ]

        # Execute
        result = tools.get_related_chunks(chunk_id='source-chunk', limit=5)

        # Assertions
        self.assertEqual(result['source_chunk_id'], 'source-chunk')
        self.assertEqual(result['source_title'], 'Source Book')
        self.assertEqual(result['result_count'], 2)  # Source filtered out
        self.assertEqual(result['results'][0]['chunk_id'], 'related-chunk-1')

        # Verify mocks
        mock_get_chunk.assert_called_once_with('source-chunk')
        mock_find_nearest.assert_called_once()

    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_related_chunks_not_found(self, mock_get_chunk):
        """Test related chunks with non-existent source chunk."""
        mock_get_chunk.return_value = None

        result = tools.get_related_chunks(chunk_id='missing-chunk', limit=5)

        self.assertIn('error', result)
        self.assertIn('not found', result['error'])
        self.assertEqual(result['result_count'], 0)

    @patch('mcp_server.tools.firestore_client.get_stats')
    def test_get_stats_success(self, mock_get_stats):
        """Test knowledge base stats collection."""
        mock_get_stats.return_value = {
            'total_chunks': 813,
            'total_documents': 273,
            'source_count': 2,
            'author_count': 150,
            'tag_count': 45,
            'avg_chunks_per_doc': 3.0
        }

        result = tools.get_stats()

        self.assertEqual(result['total_chunks'], 813)
        self.assertEqual(result['total_documents'], 273)
        self.assertEqual(result['avg_chunks_per_doc'], 3.0)


if __name__ == '__main__':
    unittest.main()
