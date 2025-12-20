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
# Add mcp_server to path so firestore_client and embeddings can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src/mcp_server'))

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


class TestSearchKBUnified(unittest.TestCase):
    """Test suite for unified search_kb tool (Story 4.1)."""

    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    def test_search_kb_semantic_only(self, mock_find_nearest, mock_generate_embedding):
        """Test search_kb with query only (semantic search mode)."""
        # Mock embedding generation
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock Firestore results
        mock_find_nearest.return_value = [
            {
                'id': 'chunk-1',
                'chunk_id': 'chunk-1',
                'title': 'Test Book',
                'author': 'Test Author',
                'source': 'kindle',
                'tags': ['psychology'],
                'content': 'Test content.',
                'chunk_index': 0,
                'total_chunks': 1,
                'knowledge_card': {
                    'summary': 'Test summary',
                    'takeaways': ['Takeaway 1']
                },
                'cluster_id': ['cluster-1']
            }
        ]

        # Execute search
        result = tools.search_kb(query="test query", limit=10)

        # Assertions
        self.assertEqual(result['query'], "test query")
        self.assertEqual(result['result_count'], 1)
        self.assertEqual(result['limit'], 10)
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['chunk_id'], 'chunk-1')

        # Verify knowledge card included (AC 9)
        self.assertIsNotNone(result['results'][0]['knowledge_card'])
        self.assertEqual(result['results'][0]['knowledge_card']['summary'], 'Test summary')

        # Verify cluster info included (AC 9)
        self.assertIsNotNone(result['results'][0]['cluster'])

        # Verify mocks called
        mock_generate_embedding.assert_called_once_with("test query")
        mock_find_nearest.assert_called_once()

    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    def test_search_kb_with_metadata_filters(self, mock_find_nearest, mock_generate_embedding):
        """Test search_kb with metadata filters (tags, author, source)."""
        # Mock embedding generation
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock Firestore results
        mock_find_nearest.return_value = []

        # Execute search with filters
        result = tools.search_kb(
            query="test query",
            filters={'tags': ['productivity'], 'author': 'Test Author', 'source': 'kindle'},
            limit=10
        )

        # Verify filters passed to find_nearest
        mock_find_nearest.assert_called_once()
        call_args = mock_find_nearest.call_args
        self.assertEqual(call_args[1]['filters']['tags'], ['productivity'])
        self.assertEqual(call_args[1]['filters']['author'], 'Test Author')
        self.assertEqual(call_args[1]['filters']['source'], 'kindle')

    @patch('mcp_server.tools.firestore_client.query_by_date_range')
    def test_search_kb_with_date_range(self, mock_query_date):
        """Test search_kb with date range filter."""
        # Mock Firestore results
        mock_query_date.return_value = [
            {
                'id': 'chunk-1',
                'chunk_id': 'chunk-1',
                'title': 'Test Book',
                'author': 'Test Author',
                'source': 'kindle',
                'tags': [],
                'content': 'Test content.',
                'chunk_index': 0,
                'total_chunks': 1
            }
        ]

        # Execute search with date range
        result = tools.search_kb(
            query="test query",
            filters={'date_range': {'start': '2025-01-01', 'end': '2025-12-31'}},
            limit=10
        )

        # Assertions
        self.assertEqual(result['result_count'], 1)

        # Verify date range query called
        mock_query_date.assert_called_once_with(
            start_date='2025-01-01',
            end_date='2025-12-31',
            limit=10,
            tags=None,
            author=None,
            source=None
        )

    @patch('mcp_server.tools.firestore_client.query_by_relative_time')
    def test_search_kb_with_period(self, mock_query_time):
        """Test search_kb with relative time period filter."""
        # Mock Firestore results
        mock_query_time.return_value = []

        # Execute search with period
        result = tools.search_kb(
            query="test query",
            filters={'period': 'last_week'},
            limit=10
        )

        # Verify period query called
        mock_query_time.assert_called_once_with(
            period='last_week',
            limit=10,
            tags=None,
            author=None,
            source=None
        )

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    @patch('mcp_server.tools.firestore_client.search_within_cluster')
    def test_search_kb_with_cluster_id(self, mock_search_cluster, mock_generate_embedding, mock_get_cluster):
        """Test search_kb with cluster_id filter (cluster scoping)."""
        # Mock cluster exists
        mock_get_cluster.return_value = {
            'id': 'cluster-1',
            'name': 'Test Cluster',
            'description': 'Test cluster description'
        }

        # Mock embedding generation
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock cluster search results
        mock_search_cluster.return_value = []

        # Execute search with cluster_id
        result = tools.search_kb(
            query="test query",
            filters={'cluster_id': 'cluster-1'},
            limit=10
        )

        # Verify cluster search called
        mock_search_cluster.assert_called_once_with(
            cluster_id='cluster-1',
            embedding_vector=[0.1] * 768,
            limit=10
        )

        # Verify cluster name in result
        self.assertEqual(result['cluster_name'], 'Test Cluster')

    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    def test_search_kb_with_search_cards_only(self, mock_find_nearest, mock_generate_embedding):
        """Test search_kb with search_cards_only filter."""
        # Mock embedding generation
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock Firestore results
        mock_find_nearest.return_value = [
            {
                'id': 'chunk-1',
                'chunk_id': 'chunk-1',
                'title': 'Test Book',
                'author': 'Test Author',
                'source': 'kindle',
                'knowledge_card': {
                    'summary': 'Card summary',
                    'takeaways': ['Takeaway 1', 'Takeaway 2']
                }
            }
        ]

        # Execute search with search_cards_only
        result = tools.search_kb(
            query="test query",
            filters={'search_cards_only': True},
            limit=10
        )

        # Assertions
        self.assertEqual(result['result_count'], 1)

        # Verify knowledge card returned
        self.assertEqual(result['results'][0]['knowledge_card']['summary'], 'Card summary')
        self.assertEqual(len(result['results'][0]['knowledge_card']['takeaways']), 2)

        # Verify full_content NOT in results (cards only)
        self.assertNotIn('full_content', result['results'][0])

    @patch('mcp_server.tools.firestore_client.query_by_date_range')
    def test_search_kb_combined_filters(self, mock_query_date):
        """Test search_kb with multiple filters (AND logic)."""
        # Mock Firestore results
        mock_query_date.return_value = []

        # Execute search with multiple filters
        result = tools.search_kb(
            query="test query",
            filters={
                'date_range': {'start': '2025-01-01', 'end': '2025-12-31'},
                'tags': ['productivity'],
                'author': 'Test Author'
            },
            limit=10
        )

        # Verify all filters passed together (AND logic)
        mock_query_date.assert_called_once_with(
            start_date='2025-01-01',
            end_date='2025-12-31',
            limit=10,
            tags=['productivity'],
            author='Test Author',
            source=None
        )

    def test_search_kb_conflicting_filters(self):
        """Test search_kb rejects conflicting date_range and period filters."""
        # Execute search with conflicting filters
        result = tools.search_kb(
            query="test query",
            filters={
                'date_range': {'start': '2025-01-01', 'end': '2025-12-31'},
                'period': 'last_week'
            },
            limit=10
        )

        # Verify error returned
        self.assertIn('error', result)
        self.assertIn('Cannot specify both date_range and period', result['error'])
        self.assertEqual(result['result_count'], 0)

    def test_search_kb_invalid_date_range(self):
        """Test search_kb with incomplete date_range."""
        # Execute search with missing end date
        result = tools.search_kb(
            query="test query",
            filters={'date_range': {'start': '2025-01-01'}},
            limit=10
        )

        # Verify error returned
        self.assertIn('error', result)
        self.assertIn('date_range requires both start and end dates', result['error'])

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_search_kb_cluster_not_found(self, mock_get_cluster):
        """Test search_kb with non-existent cluster_id."""
        # Mock cluster not found
        mock_get_cluster.return_value = None

        # Execute search
        result = tools.search_kb(
            query="test query",
            filters={'cluster_id': 'non-existent-cluster'},
            limit=10
        )

        # Verify error returned
        self.assertIn('error', result)
        self.assertIn('Cluster not found', result['error'])
        self.assertEqual(result['result_count'], 0)

    @patch('mcp_server.tools.embeddings.generate_query_embedding')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    def test_search_kb_urls_included(self, mock_find_nearest, mock_generate_embedding):
        """Test search_kb includes all URL fields (AC 10)."""
        # Mock embedding generation
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock Firestore results with URLs
        mock_find_nearest.return_value = [
            {
                'id': 'chunk-1',
                'chunk_id': 'chunk-1',
                'title': 'Test Book',
                'author': 'Test Author',
                'source': 'kindle',
                'tags': [],
                'content': 'Test content.',
                'chunk_index': 0,
                'total_chunks': 1,
                'readwise_url': 'https://readwise.io/bookreview/123',
                'source_url': 'https://example.com/book',
                'highlight_url': 'https://readwise.io/highlights/456'
            }
        ]

        # Execute search
        result = tools.search_kb(query="test query", limit=10)

        # Verify all URL fields included (Story 2.7, AC 10)
        self.assertIn('readwise_url', result['results'][0])
        self.assertIn('source_url', result['results'][0])
        self.assertIn('highlight_url', result['results'][0])
        self.assertEqual(result['results'][0]['readwise_url'], 'https://readwise.io/bookreview/123')


class TestGetChunk(unittest.TestCase):
    """Test suite for get_chunk tool (Story 4.2)."""

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_chunk_with_all_fields(self, mock_get_chunk, mock_find_nearest, mock_get_cluster):
        """Test get_chunk returns all fields including knowledge card, related chunks, cluster, and URLs (AC 2-6)."""
        # Mock chunk data
        mock_get_chunk.return_value = {
            'id': 'chunk-123',
            'chunk_id': 'chunk-123',
            'title': 'Test Book Title',
            'author': 'Test Author',
            'source': 'kindle',
            'tags': ['ai', 'agents'],
            'content': 'Full chunk content here.',
            'chunk_index': 0,
            'total_chunks': 5,
            'embedding': [0.1] * 768,
            'knowledge_card': {
                'summary': 'AI-generated summary of the chunk',
                'takeaways': ['Key point 1', 'Key point 2']
            },
            'cluster_id': ['cluster-28'],
            'readwise_url': 'https://readwise.io/bookreview/123',
            'source_url': 'https://example.com/book',
            'highlight_url': 'https://readwise.io/highlights/456'
        }

        # Mock related chunks
        mock_find_nearest.return_value = [
            {
                'id': 'chunk-123',  # Source chunk (should be filtered out)
                'chunk_id': 'chunk-123',
                'title': 'Test Book Title',
                'author': 'Test Author',
                'content': 'Source chunk content',
                'similarity_score': 1.0
            },
            {
                'id': 'chunk-456',
                'chunk_id': 'chunk-456',
                'title': 'Related Book',
                'author': 'Related Author',
                'content': 'Related chunk content here.',
                'similarity_score': 0.89
            },
            {
                'id': 'chunk-789',
                'chunk_id': 'chunk-789',
                'title': 'Another Related Book',
                'author': 'Another Author',
                'content': 'Another related chunk content.',
                'similarity_score': 0.85
            }
        ]

        # Mock cluster metadata
        mock_get_cluster.return_value = {
            'name': 'AI Agents & LLMs',
            'description': 'Content about AI agents and large language models'
        }

        # Execute get_chunk
        result = tools.get_chunk(chunk_id='chunk-123', include_related=True, related_limit=5)

        # AC 2: Full chunk content returned with all fields
        self.assertEqual(result['chunk_id'], 'chunk-123')
        self.assertEqual(result['title'], 'Test Book Title')
        self.assertEqual(result['author'], 'Test Author')
        self.assertEqual(result['source'], 'kindle')
        self.assertEqual(result['tags'], ['ai', 'agents'])
        self.assertEqual(result['content'], 'Full chunk content here.')
        self.assertEqual(result['chunk_info'], '1/5')

        # AC 3: Knowledge card embedded by default
        self.assertIsNotNone(result['knowledge_card'])
        self.assertEqual(result['knowledge_card']['summary'], 'AI-generated summary of the chunk')
        self.assertEqual(len(result['knowledge_card']['takeaways']), 2)

        # AC 4: Related chunks included by default
        self.assertIsNotNone(result['related_chunks'])
        self.assertEqual(len(result['related_chunks']), 2)  # Source chunk filtered out
        self.assertEqual(result['related_chunks'][0]['chunk_id'], 'chunk-456')
        self.assertEqual(result['related_chunks'][0]['similarity_score'], 0.89)

        # AC 5: Cluster membership info included
        self.assertIsNotNone(result['cluster'])
        self.assertEqual(result['cluster']['cluster_id'], 'cluster-28')
        self.assertEqual(result['cluster']['name'], 'AI Agents & LLMs')

        # AC 6: All URLs included
        self.assertEqual(result['readwise_url'], 'https://readwise.io/bookreview/123')
        self.assertEqual(result['source_url'], 'https://example.com/book')
        self.assertEqual(result['highlight_url'], 'https://readwise.io/highlights/456')

        # Verify mocks called
        mock_get_chunk.assert_called_once_with('chunk-123')
        mock_find_nearest.assert_called_once()
        mock_get_cluster.assert_called_once_with('cluster-28')

    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_chunk_with_include_related_false(self, mock_get_chunk):
        """Test get_chunk with include_related=false disables related chunks retrieval (AC 7)."""
        # Mock chunk data without embedding
        mock_get_chunk.return_value = {
            'id': 'chunk-123',
            'chunk_id': 'chunk-123',
            'title': 'Test Book',
            'author': 'Test Author',
            'source': 'kindle',
            'tags': [],
            'content': 'Content.',
            'chunk_index': 0,
            'total_chunks': 1
        }

        # Execute get_chunk with include_related=False
        result = tools.get_chunk(chunk_id='chunk-123', include_related=False)

        # AC 7: Related chunks should be empty
        self.assertEqual(result['related_chunks'], [])

        # Verify chunk data still returned
        self.assertEqual(result['chunk_id'], 'chunk-123')
        self.assertEqual(result['title'], 'Test Book')

    @patch('mcp_server.tools.firestore_client.find_nearest')
    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_chunk_with_custom_related_limit(self, mock_get_chunk, mock_find_nearest):
        """Test get_chunk with custom related_limit parameter (AC 8)."""
        # Mock chunk data
        mock_get_chunk.return_value = {
            'id': 'chunk-123',
            'chunk_id': 'chunk-123',
            'title': 'Test Book',
            'author': 'Test Author',
            'source': 'kindle',
            'tags': [],
            'content': 'Content.',
            'chunk_index': 0,
            'total_chunks': 1,
            'embedding': [0.1] * 768
        }

        # Mock 10 related chunks
        mock_find_nearest.return_value = [
            {
                'id': f'chunk-{i}',
                'chunk_id': f'chunk-{i}',
                'title': f'Book {i}',
                'author': f'Author {i}',
                'content': f'Content {i}',
                'similarity_score': 1.0 - (i * 0.05)
            }
            for i in range(1, 11)
        ]

        # Execute get_chunk with related_limit=3
        result = tools.get_chunk(chunk_id='chunk-123', include_related=True, related_limit=3)

        # AC 8: Should return exactly 3 related chunks
        self.assertEqual(len(result['related_chunks']), 3)
        self.assertEqual(result['related_chunks'][0]['chunk_id'], 'chunk-1')

        # Verify find_nearest called with limit=4 (3+1 for source chunk filtering)
        mock_find_nearest.assert_called_once()
        call_args = mock_find_nearest.call_args
        self.assertEqual(call_args[1]['limit'], 4)

    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_chunk_not_found(self, mock_get_chunk):
        """Test get_chunk returns error gracefully when chunk_id not found (AC 9)."""
        # Mock chunk not found
        mock_get_chunk.return_value = None

        # Execute get_chunk - should raise ValueError
        with self.assertRaises(ValueError) as context:
            tools.get_chunk(chunk_id='nonexistent-chunk')

        self.assertIn('Chunk not found', str(context.exception))

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_chunk_missing_knowledge_card(self, mock_get_chunk, mock_get_cluster):
        """Test get_chunk returns gracefully when knowledge_card is missing (AC 9)."""
        # Mock chunk without knowledge card
        mock_get_chunk.return_value = {
            'id': 'chunk-123',
            'chunk_id': 'chunk-123',
            'title': 'Test Book',
            'author': 'Test Author',
            'source': 'kindle',
            'tags': [],
            'content': 'Content.',
            'chunk_index': 0,
            'total_chunks': 1,
            'cluster_id': ['cluster-28']
        }

        mock_get_cluster.return_value = {
            'name': 'Test Cluster',
            'description': 'Test description'
        }

        # Execute get_chunk
        result = tools.get_chunk(chunk_id='chunk-123', include_related=False)

        # AC 9: Knowledge card should be None when missing
        self.assertIsNone(result['knowledge_card'])

        # Verify other data still returned
        self.assertEqual(result['chunk_id'], 'chunk-123')
        self.assertIsNotNone(result['cluster'])

    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_chunk_no_embedding_for_related(self, mock_get_chunk):
        """Test get_chunk handles missing embedding gracefully (can't retrieve related chunks)."""
        # Mock chunk without embedding
        mock_get_chunk.return_value = {
            'id': 'chunk-123',
            'chunk_id': 'chunk-123',
            'title': 'Test Book',
            'author': 'Test Author',
            'source': 'kindle',
            'tags': [],
            'content': 'Content.',
            'chunk_index': 0,
            'total_chunks': 1
            # No 'embedding' field
        }

        # Execute get_chunk with include_related=True
        result = tools.get_chunk(chunk_id='chunk-123', include_related=True)

        # Should return empty related_chunks (no embedding available)
        self.assertEqual(result['related_chunks'], [])

        # Other data should still be present
        self.assertEqual(result['chunk_id'], 'chunk-123')

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_chunk_all_url_fields(self, mock_get_chunk, mock_get_cluster):
        """Test get_chunk includes all URL fields (AC 6)."""
        # Mock chunk with all URL fields
        mock_get_chunk.return_value = {
            'id': 'chunk-123',
            'chunk_id': 'chunk-123',
            'title': 'Test Book',
            'author': 'Test Author',
            'source': 'kindle',
            'tags': [],
            'content': 'Content.',
            'chunk_index': 0,
            'total_chunks': 1,
            'cluster_id': ['cluster-1'],
            'readwise_url': 'https://readwise.io/book/123',
            'source_url': 'https://amazon.com/book/456',
            'highlight_url': 'https://readwise.io/highlight/789'
        }

        mock_get_cluster.return_value = {'name': 'Test', 'description': 'Test'}

        # Execute get_chunk
        result = tools.get_chunk(chunk_id='chunk-123', include_related=False)

        # AC 6: Verify all URL fields present
        self.assertIn('readwise_url', result)
        self.assertIn('source_url', result)
        self.assertIn('highlight_url', result)
        self.assertEqual(result['readwise_url'], 'https://readwise.io/book/123')
        self.assertEqual(result['source_url'], 'https://amazon.com/book/456')
        self.assertEqual(result['highlight_url'], 'https://readwise.io/highlight/789')

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.find_nearest')
    @patch('mcp_server.tools.firestore_client.get_chunk_by_id')
    def test_get_chunk_filters_out_source_chunk(self, mock_get_chunk, mock_find_nearest, mock_get_cluster):
        """Test get_chunk filters out the source chunk from related chunks results."""
        # Mock chunk data
        mock_get_chunk.return_value = {
            'id': 'chunk-source',
            'chunk_id': 'chunk-source',
            'title': 'Source Book',
            'author': 'Author',
            'source': 'kindle',
            'tags': [],
            'content': 'Source content.',
            'chunk_index': 0,
            'total_chunks': 1,
            'embedding': [0.1] * 768,
            'cluster_id': ['cluster-1']
        }

        # Mock related chunks including the source chunk
        mock_find_nearest.return_value = [
            {
                'id': 'chunk-source',  # Source chunk should be filtered
                'chunk_id': 'chunk-source',
                'title': 'Source Book',
                'author': 'Author',
                'content': 'Source content.',
                'similarity_score': 1.0
            },
            {
                'id': 'chunk-related',
                'chunk_id': 'chunk-related',
                'title': 'Related Book',
                'author': 'Author',
                'content': 'Related content.',
                'similarity_score': 0.90
            }
        ]

        mock_get_cluster.return_value = {'name': 'Test', 'description': 'Test'}

        # Execute get_chunk
        result = tools.get_chunk(chunk_id='chunk-source', include_related=True, related_limit=5)

        # Verify source chunk filtered out from related chunks
        self.assertEqual(len(result['related_chunks']), 1)
        self.assertEqual(result['related_chunks'][0]['chunk_id'], 'chunk-related')
        self.assertNotEqual(result['related_chunks'][0]['chunk_id'], 'chunk-source')


class TestGetRecent(unittest.TestCase):
    """Test suite for get_recent tool (Story 4.3)."""

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.get_activity_summary')
    @patch('mcp_server.tools.firestore_client.get_recently_added')
    def test_get_recent_default_parameters(self, mock_get_recently_added, mock_get_activity_summary, mock_get_cluster):
        """Test get_recent with default parameters (AC 1)."""
        # Mock recently added chunks
        mock_get_recently_added.return_value = [
            {
                'id': 'chunk-1',
                'chunk_id': 'chunk-1',
                'title': 'Recent Book',
                'author': 'Test Author',
                'source': 'kindle',
                'tags': ['productivity'],
                'content': 'Recent content.',
                'chunk_index': 0,
                'total_chunks': 1,
                'created_at': '2025-12-19T10:00:00Z',
                'cluster_id': ['cluster-28']
            }
        ]

        # Mock activity summary
        mock_get_activity_summary.return_value = {
            'period': 'last_7_days',
            'total_chunks_added': 15,
            'chunks_per_day': {'2025-12-19': 5, '2025-12-18': 10},
            'top_sources': [{'source': 'kindle', 'count': 10}, {'source': 'reader', 'count': 5}],
            'top_authors': [{'author': 'Test Author', 'count': 8}]
        }

        # Mock cluster metadata
        mock_get_cluster.return_value = {
            'name': 'AI Agents & LLMs',
            'description': 'AI content'
        }

        # Execute get_recent with defaults
        result = tools.get_recent()

        # AC 1: Verify default parameters used
        self.assertEqual(result['period'], 'last_7_days')
        mock_get_recently_added.assert_called_once_with(limit=10, days=7)

        # AC 2: Verify recent chunks included
        self.assertIn('recent_chunks', result)
        self.assertEqual(len(result['recent_chunks']), 1)
        self.assertEqual(result['recent_chunks'][0]['chunk_id'], 'chunk-1')

        # AC 3: Verify activity summary included
        self.assertIn('activity_summary', result)
        self.assertEqual(result['activity_summary']['total_chunks_added'], 15)

        # AC 4: Verify cluster distribution included
        self.assertIn('cluster_distribution', result)
        self.assertIn('cluster-28', result['cluster_distribution'])
        self.assertEqual(result['cluster_distribution']['cluster-28']['count'], 1)
        self.assertEqual(result['cluster_distribution']['cluster-28']['name'], 'AI Agents & LLMs')

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.get_activity_summary')
    @patch('mcp_server.tools.firestore_client.get_recently_added')
    def test_get_recent_with_knowledge_cards(self, mock_get_recently_added, mock_get_activity_summary, mock_get_cluster):
        """Test get_recent includes knowledge cards for chunks (AC 6)."""
        # Mock chunk with knowledge card
        mock_get_recently_added.return_value = [
            {
                'id': 'chunk-1',
                'chunk_id': 'chunk-1',
                'title': 'Recent Book',
                'author': 'Test Author',
                'source': 'kindle',
                'tags': [],
                'content': 'Content.',
                'chunk_index': 0,
                'total_chunks': 1,
                'knowledge_card': {
                    'summary': 'AI-generated summary',
                    'takeaways': ['Takeaway 1', 'Takeaway 2']
                }
            }
        ]

        mock_get_activity_summary.return_value = {
            'period': 'last_7_days',
            'total_chunks_added': 1
        }

        # Execute get_recent
        result = tools.get_recent(period='last_7_days', limit=10)

        # AC 6: Verify knowledge card included
        self.assertIsNotNone(result['recent_chunks'][0]['knowledge_card'])
        self.assertEqual(result['recent_chunks'][0]['knowledge_card']['summary'], 'AI-generated summary')
        self.assertEqual(len(result['recent_chunks'][0]['knowledge_card']['takeaways']), 2)

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.get_activity_summary')
    @patch('mcp_server.tools.firestore_client.get_recently_added')
    def test_get_recent_with_custom_period(self, mock_get_recently_added, mock_get_activity_summary, mock_get_cluster):
        """Test get_recent with different period values (AC 5)."""
        # Mock empty results
        mock_get_recently_added.return_value = []
        mock_get_activity_summary.return_value = {
            'period': 'last_3_days',
            'total_chunks_added': 0
        }

        # Execute get_recent with period='last_3_days'
        result = tools.get_recent(period='last_3_days', limit=10)

        # AC 5: Verify period mapped correctly (last_3_days -> 3 days)
        mock_get_recently_added.assert_called_once_with(limit=10, days=3)
        self.assertEqual(result['period'], 'last_3_days')

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.get_activity_summary')
    @patch('mcp_server.tools.firestore_client.get_recently_added')
    def test_get_recent_with_custom_limit(self, mock_get_recently_added, mock_get_activity_summary, mock_get_cluster):
        """Test get_recent with custom limit parameter (AC 7)."""
        # Mock 5 chunks
        mock_get_recently_added.return_value = [
            {
                'id': f'chunk-{i}',
                'chunk_id': f'chunk-{i}',
                'title': f'Book {i}',
                'author': 'Author',
                'source': 'kindle',
                'tags': [],
                'content': f'Content {i}',
                'chunk_index': 0,
                'total_chunks': 1
            }
            for i in range(1, 6)
        ]

        mock_get_activity_summary.return_value = {
            'period': 'last_7_days',
            'total_chunks_added': 5
        }

        # Execute get_recent with limit=5
        result = tools.get_recent(period='last_7_days', limit=5)

        # AC 7: Verify limit parameter used
        mock_get_recently_added.assert_called_once_with(limit=5, days=7)
        self.assertEqual(len(result['recent_chunks']), 5)

    @patch('mcp_server.tools.firestore_client.get_activity_summary')
    @patch('mcp_server.tools.firestore_client.get_recently_added')
    def test_get_recent_empty_results(self, mock_get_recently_added, mock_get_activity_summary):
        """Test get_recent with no recent chunks (AC 8)."""
        # Mock empty results
        mock_get_recently_added.return_value = []
        mock_get_activity_summary.return_value = {
            'period': 'last_7_days',
            'total_chunks_added': 0,
            'chunks_per_day': {},
            'top_sources': [],
            'top_authors': []
        }

        # Execute get_recent
        result = tools.get_recent(period='last_7_days', limit=10)

        # AC 8: Verify graceful handling of empty results
        self.assertEqual(len(result['recent_chunks']), 0)
        self.assertEqual(result['activity_summary']['total_chunks_added'], 0)
        self.assertEqual(result['cluster_distribution'], {})

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.get_activity_summary')
    @patch('mcp_server.tools.firestore_client.get_recently_added')
    def test_get_recent_url_fields_included(self, mock_get_recently_added, mock_get_activity_summary, mock_get_cluster):
        """Test get_recent includes all URL fields (AC 9)."""
        # Mock chunk with all URL fields
        mock_get_recently_added.return_value = [
            {
                'id': 'chunk-1',
                'chunk_id': 'chunk-1',
                'title': 'Recent Book',
                'author': 'Test Author',
                'source': 'kindle',
                'tags': [],
                'content': 'Content.',
                'chunk_index': 0,
                'total_chunks': 1,
                'cluster_id': ['cluster-1'],
                'readwise_url': 'https://readwise.io/book/123',
                'source_url': 'https://amazon.com/book/456',
                'highlight_url': 'https://readwise.io/highlight/789'
            }
        ]

        mock_get_activity_summary.return_value = {
            'period': 'last_7_days',
            'total_chunks_added': 1
        }

        mock_get_cluster.return_value = {'name': 'Test', 'description': 'Test'}

        # Execute get_recent
        result = tools.get_recent()

        # AC 9: Verify all URL fields included
        chunk = result['recent_chunks'][0]
        self.assertIn('readwise_url', chunk)
        self.assertIn('source_url', chunk)
        self.assertIn('highlight_url', chunk)
        self.assertEqual(chunk['readwise_url'], 'https://readwise.io/book/123')
        self.assertEqual(chunk['source_url'], 'https://amazon.com/book/456')
        self.assertEqual(chunk['highlight_url'], 'https://readwise.io/highlight/789')

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.get_activity_summary')
    @patch('mcp_server.tools.firestore_client.get_recently_added')
    def test_get_recent_cluster_distribution_calculation(self, mock_get_recently_added, mock_get_activity_summary, mock_get_cluster):
        """Test get_recent calculates cluster distribution correctly (AC 4)."""
        # Mock 3 chunks: 2 in cluster-1, 1 in cluster-2
        mock_get_recently_added.return_value = [
            {
                'id': 'chunk-1',
                'chunk_id': 'chunk-1',
                'title': 'Book 1',
                'author': 'Author',
                'source': 'kindle',
                'tags': [],
                'content': 'Content 1',
                'chunk_index': 0,
                'total_chunks': 1,
                'cluster_id': ['cluster-1']
            },
            {
                'id': 'chunk-2',
                'chunk_id': 'chunk-2',
                'title': 'Book 2',
                'author': 'Author',
                'source': 'kindle',
                'tags': [],
                'content': 'Content 2',
                'chunk_index': 0,
                'total_chunks': 1,
                'cluster_id': ['cluster-1']
            },
            {
                'id': 'chunk-3',
                'chunk_id': 'chunk-3',
                'title': 'Book 3',
                'author': 'Author',
                'source': 'reader',
                'tags': [],
                'content': 'Content 3',
                'chunk_index': 0,
                'total_chunks': 1,
                'cluster_id': ['cluster-2']
            }
        ]

        mock_get_activity_summary.return_value = {
            'period': 'last_7_days',
            'total_chunks_added': 3
        }

        # Mock cluster metadata calls
        def mock_get_cluster_side_effect(cluster_id):
            if cluster_id == 'cluster-1':
                return {'name': 'Cluster One', 'description': 'First cluster'}
            elif cluster_id == 'cluster-2':
                return {'name': 'Cluster Two', 'description': 'Second cluster'}
            return None

        mock_get_cluster.side_effect = mock_get_cluster_side_effect

        # Execute get_recent
        result = tools.get_recent()

        # AC 4: Verify cluster distribution calculated correctly
        self.assertEqual(len(result['cluster_distribution']), 2)
        self.assertEqual(result['cluster_distribution']['cluster-1']['count'], 2)
        self.assertEqual(result['cluster_distribution']['cluster-1']['name'], 'Cluster One')
        self.assertEqual(result['cluster_distribution']['cluster-2']['count'], 1)
        self.assertEqual(result['cluster_distribution']['cluster-2']['name'], 'Cluster Two')

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    @patch('mcp_server.tools.firestore_client.get_activity_summary')
    @patch('mcp_server.tools.firestore_client.get_recently_added')
    def test_get_recent_top_sources_and_authors(self, mock_get_recently_added, mock_get_activity_summary, mock_get_cluster):
        """Test get_recent includes top sources and authors in activity summary (AC 10)."""
        # Mock chunks
        mock_get_recently_added.return_value = []

        # Mock activity summary with top sources/authors
        mock_get_activity_summary.return_value = {
            'period': 'last_7_days',
            'total_chunks_added': 20,
            'chunks_per_day': {},
            'top_sources': [
                {'source': 'kindle', 'count': 15},
                {'source': 'reader', 'count': 5}
            ],
            'top_authors': [
                {'author': 'Author One', 'count': 10},
                {'author': 'Author Two', 'count': 6},
                {'author': 'Author Three', 'count': 4}
            ]
        }

        # Execute get_recent
        result = tools.get_recent()

        # AC 10: Verify top sources and authors included
        self.assertIn('top_sources', result['activity_summary'])
        self.assertEqual(len(result['activity_summary']['top_sources']), 2)
        self.assertEqual(result['activity_summary']['top_sources'][0]['source'], 'kindle')
        self.assertEqual(result['activity_summary']['top_sources'][0]['count'], 15)

        self.assertIn('top_authors', result['activity_summary'])
        self.assertEqual(len(result['activity_summary']['top_authors']), 3)
        self.assertEqual(result['activity_summary']['top_authors'][0]['author'], 'Author One')
        self.assertEqual(result['activity_summary']['top_authors'][0]['count'], 10)

    @patch('mcp_server.tools.firestore_client.get_activity_summary')
    @patch('mcp_server.tools.firestore_client.get_recently_added')
    def test_get_recent_period_mapping(self, mock_get_recently_added, mock_get_activity_summary):
        """Test get_recent maps all period values to correct days (AC 5)."""
        # Mock empty results
        mock_get_recently_added.return_value = []
        mock_get_activity_summary.return_value = {
            'period': 'today',
            'total_chunks_added': 0
        }

        # Test all period mappings
        period_mappings = {
            'today': 1,
            'yesterday': 1,
            'last_3_days': 3,
            'last_week': 7,
            'last_7_days': 7,
            'last_month': 30,
            'last_30_days': 30
        }

        for period, expected_days in period_mappings.items():
            mock_get_recently_added.reset_mock()
            result = tools.get_recent(period=period, limit=10)

            # Verify correct days mapping
            mock_get_recently_added.assert_called_once_with(limit=10, days=expected_days)
            self.assertEqual(result['period'], period)


class TestGetClusterEnhanced(unittest.TestCase):
    """Test suite for enhanced get_cluster tool (Story 4.4)."""

    @patch('mcp_server.tools.firestore_client.get_firestore_client')
    @patch('mcp_server.tools.firestore_client.get_chunks_by_cluster')
    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_with_members_and_related(self, mock_get_cluster, mock_get_chunks, mock_get_db):
        """Test get_cluster with both members and related clusters (AC 1, 2, 3)."""
        # Mock cluster data
        mock_get_cluster.return_value = {
            'name': 'AI Agents & LLMs',
            'description': 'Content about AI agents',
            'size': 25,
            'created_at': '2025-01-01',
            'centroid_768d': [0.1] * 768
        }

        # Mock member chunks
        mock_get_chunks.return_value = [
            {
                'id': 'chunk-1',
                'title': 'Test Book',
                'author': 'Test Author',
                'source': 'kindle',
                'knowledge_card': {
                    'summary': 'AI summary',
                    'takeaways': ['Point 1']
                }
            }
        ]

        # Mock Firestore db and vector search
        mock_doc1 = MagicMock()
        mock_doc1.id = 'cluster-2'
        mock_doc1.to_dict.return_value = {
            'name': 'Related Cluster',
            'description': 'Related content',
            'size': 15,
            'vector_distance': 0.3
        }

        mock_doc2 = MagicMock()
        mock_doc2.id = 'cluster-test'  # Source cluster (should be filtered)
        mock_doc2.to_dict.return_value = {
            'name': 'Source Cluster',
            'size': 25,
            'vector_distance': 0.0
        }

        mock_vector_query = MagicMock()
        mock_vector_query.stream.return_value = [mock_doc2, mock_doc1]

        mock_collection = MagicMock()
        mock_collection.find_nearest.return_value = mock_vector_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        # Execute get_cluster
        result = tools.get_cluster(
            cluster_id='cluster-test',
            include_members=True,
            include_related=True,
            member_limit=20,
            related_limit=5
        )

        # AC 1: Cluster metadata returned
        self.assertEqual(result['cluster_id'], 'cluster-test')
        self.assertEqual(result['name'], 'AI Agents & LLMs')
        self.assertEqual(result['size'], 25)

        # AC 2: Member chunks included
        self.assertIn('members', result)
        self.assertEqual(len(result['members']), 1)
        self.assertEqual(result['members'][0]['chunk_id'], 'chunk-1')

        # AC 3: Related clusters included
        self.assertIn('related_clusters', result)
        self.assertEqual(len(result['related_clusters']), 1)
        self.assertEqual(result['related_clusters'][0]['cluster_id'], 'cluster-2')
        self.assertIn('similarity_score', result['related_clusters'][0])

    @patch('mcp_server.tools.firestore_client.get_chunks_by_cluster')
    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_with_include_members_false(self, mock_get_cluster, mock_get_chunks):
        """Test get_cluster with include_members=False (AC 4)."""
        # Mock cluster data
        mock_get_cluster.return_value = {
            'name': 'Test Cluster',
            'description': 'Test',
            'size': 10,
            'created_at': '2025-01-01'
        }

        # Execute get_cluster with include_members=False
        result = tools.get_cluster(
            cluster_id='cluster-1',
            include_members=False,
            include_related=False
        )

        # AC 4: Members should not be included
        self.assertNotIn('members', result)
        self.assertNotIn('member_count', result)

        # Verify get_chunks_by_cluster was NOT called
        mock_get_chunks.assert_not_called()

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_with_include_related_false(self, mock_get_cluster):
        """Test get_cluster with include_related=False (AC 5)."""
        # Mock cluster data with centroid
        mock_get_cluster.return_value = {
            'name': 'Test Cluster',
            'description': 'Test',
            'size': 10,
            'created_at': '2025-01-01',
            'centroid_768d': [0.1] * 768
        }

        # Execute get_cluster with include_related=False
        result = tools.get_cluster(
            cluster_id='cluster-1',
            include_members=False,
            include_related=False
        )

        # AC 5: Related clusters should not be included
        self.assertNotIn('related_clusters', result)
        self.assertNotIn('related_count', result)

    @patch('mcp_server.tools.firestore_client.get_firestore_client')
    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_custom_limits(self, mock_get_cluster, mock_get_db):
        """Test get_cluster with custom member_limit and related_limit (AC 6, 7)."""
        # Mock cluster data
        mock_get_cluster.return_value = {
            'name': 'Test Cluster',
            'size': 50,
            'centroid_768d': [0.1] * 768
        }

        # Mock vector search
        mock_vector_query = MagicMock()
        mock_vector_query.stream.return_value = []

        mock_collection = MagicMock()
        mock_collection.find_nearest.return_value = mock_vector_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        # Execute get_cluster with custom limits
        result = tools.get_cluster(
            cluster_id='cluster-1',
            member_limit=10,
            related_limit=3
        )

        # Verify vector search called with correct limit (+1 for source)
        mock_collection.find_nearest.assert_called_once()
        call_kwargs = mock_collection.find_nearest.call_args[1]
        self.assertEqual(call_kwargs['limit'], 4)  # related_limit + 1

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_no_centroid(self, mock_get_cluster):
        """Test get_cluster when cluster has no centroid (AC 8)."""
        # Mock cluster without centroid
        mock_get_cluster.return_value = {
            'name': 'Test Cluster',
            'description': 'Test',
            'size': 10
        }

        # Execute get_cluster with include_related=True
        result = tools.get_cluster(
            cluster_id='cluster-1',
            include_members=False,
            include_related=True
        )

        # AC 8: Related clusters should be empty (no centroid available)
        self.assertEqual(result['related_count'], 0)
        self.assertEqual(result['related_clusters'], [])

    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_not_found(self, mock_get_cluster):
        """Test get_cluster with non-existent cluster_id (AC 9)."""
        # Mock cluster not found
        mock_get_cluster.return_value = None

        # Execute get_cluster
        result = tools.get_cluster(cluster_id='nonexistent')

        # AC 9: Error returned
        self.assertIn('error', result)
        self.assertIn('not found', result['error'])
        self.assertEqual(result['cluster_id'], 'nonexistent')

    @patch('mcp_server.tools.firestore_client.get_firestore_client')
    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_filters_source_cluster(self, mock_get_cluster, mock_get_db):
        """Test get_cluster filters out source cluster from related results (AC 10)."""
        # Mock cluster data
        mock_get_cluster.return_value = {
            'name': 'Source Cluster',
            'size': 25,
            'centroid_768d': [0.1] * 768
        }

        # Mock vector search returning source cluster
        mock_source_doc = MagicMock()
        mock_source_doc.id = 'cluster-source'
        mock_source_doc.to_dict.return_value = {
            'name': 'Source Cluster',
            'size': 25,
            'vector_distance': 0.0
        }

        mock_related_doc = MagicMock()
        mock_related_doc.id = 'cluster-related'
        mock_related_doc.to_dict.return_value = {
            'name': 'Related Cluster',
            'size': 15,
            'vector_distance': 0.4
        }

        mock_vector_query = MagicMock()
        mock_vector_query.stream.return_value = [mock_source_doc, mock_related_doc]

        mock_collection = MagicMock()
        mock_collection.find_nearest.return_value = mock_vector_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        # Execute get_cluster
        result = tools.get_cluster(
            cluster_id='cluster-source',
            include_members=False,
            include_related=True
        )

        # AC 10: Source cluster filtered out from related
        self.assertEqual(len(result['related_clusters']), 1)
        self.assertEqual(result['related_clusters'][0]['cluster_id'], 'cluster-related')

    @patch('mcp_server.tools.firestore_client.get_firestore_client')
    @patch('mcp_server.tools.firestore_client.get_cluster_by_id')
    def test_get_cluster_filters_noise_clusters(self, mock_get_cluster, mock_get_db):
        """Test get_cluster filters out noise clusters from related results."""
        # Mock cluster data
        mock_get_cluster.return_value = {
            'name': 'Source Cluster',
            'size': 25,
            'centroid_768d': [0.1] * 768
        }

        # Mock vector search returning noise cluster
        mock_noise_doc = MagicMock()
        mock_noise_doc.id = 'noise'
        mock_noise_doc.to_dict.return_value = {
            'name': 'Noise / Outliers',
            'size': 100,
            'vector_distance': 0.5
        }

        mock_valid_doc = MagicMock()
        mock_valid_doc.id = 'cluster-valid'
        mock_valid_doc.to_dict.return_value = {
            'name': 'Valid Cluster',
            'size': 20,
            'vector_distance': 0.3
        }

        mock_vector_query = MagicMock()
        mock_vector_query.stream.return_value = [mock_noise_doc, mock_valid_doc]

        mock_collection = MagicMock()
        mock_collection.find_nearest.return_value = mock_vector_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        # Execute get_cluster
        result = tools.get_cluster(
            cluster_id='cluster-source',
            include_members=False,
            include_related=True
        )

        # Noise cluster should be filtered out
        self.assertEqual(len(result['related_clusters']), 1)
        self.assertEqual(result['related_clusters'][0]['cluster_id'], 'cluster-valid')


class TestConfigureKB(unittest.TestCase):
    """Test suite for configure_kb unified configuration tool (Story 4.5)."""

    @patch('mcp_server.tools.get_hot_sites_config')
    @patch('mcp_server.tools.get_recommendation_config')
    @patch('mcp_server.tools.get_ranking_config')
    def test_show_all_action(self, mock_ranking, mock_domains, mock_hot_sites):
        """Test show_all action returns all configuration (AC 1, 2)."""
        # Mock configuration data
        mock_ranking.return_value = {
            'weights': {'relevance': 0.5, 'recency': 0.25, 'depth': 0.15, 'authority': 0.1}
        }
        mock_domains.return_value = {
            'quality_domains': ['martinfowler.com', 'thoughtworks.com'],
            'domain_count': 2
        }
        mock_hot_sites.return_value = {
            'categories': {'tech': ['hckrnews.com'], 'ai': ['anthropic.com']},
            'total_domains': 2
        }

        result = tools.configure_kb(action='show_all')

        # Verify all three configs returned
        self.assertEqual(result['action'], 'show_all')
        self.assertIn('ranking', result)
        self.assertIn('domains', result)
        self.assertIn('hot_sites', result)
        self.assertEqual(result['ranking']['weights']['relevance'], 0.5)
        self.assertEqual(result['domains']['domain_count'], 2)
        self.assertEqual(result['hot_sites']['total_domains'], 2)

    @patch('mcp_server.tools.get_ranking_config')
    def test_show_ranking_action(self, mock_get_ranking):
        """Test show_ranking action (AC 3)."""
        mock_get_ranking.return_value = {
            'weights': {'relevance': 0.5, 'recency': 0.25, 'depth': 0.15, 'authority': 0.1},
            'settings': {'recency': {'half_life_days': 90}}
        }

        result = tools.configure_kb(action='show_ranking')

        self.assertEqual(result['action'], 'show_ranking')
        self.assertIn('weights', result)
        self.assertIn('settings', result)
        self.assertEqual(result['weights']['relevance'], 0.5)

    @patch('mcp_server.tools.get_recommendation_config')
    def test_show_domains_action(self, mock_get_domains):
        """Test show_domains action (AC 4)."""
        mock_get_domains.return_value = {
            'quality_domains': ['site1.com', 'site2.com'],
            'excluded_domains': ['spam.com'],
            'domain_count': 2
        }

        result = tools.configure_kb(action='show_domains')

        self.assertEqual(result['action'], 'show_domains')
        self.assertIn('quality_domains', result)
        self.assertEqual(result['domain_count'], 2)
        self.assertEqual(len(result['quality_domains']), 2)

    @patch('mcp_server.tools.get_hot_sites_config')
    def test_show_hot_sites_action(self, mock_get_hot_sites):
        """Test show_hot_sites action (AC 5)."""
        mock_get_hot_sites.return_value = {
            'categories': {
                'tech': ['site1.com', 'site2.com'],
                'ai': ['anthropic.com']
            },
            'category_summary': [
                {'category': 'tech', 'domain_count': 2},
                {'category': 'ai', 'domain_count': 1}
            ],
            'total_domains': 3
        }

        result = tools.configure_kb(action='show_hot_sites')

        self.assertEqual(result['action'], 'show_hot_sites')
        self.assertIn('categories', result)
        self.assertIn('category_summary', result)
        self.assertEqual(result['total_domains'], 3)

    @patch('mcp_server.tools.update_ranking_config')
    def test_update_ranking_action(self, mock_update_ranking):
        """Test update_ranking action with weights (AC 6)."""
        mock_update_ranking.return_value = {
            'success': True,
            'config': {'weights': {'relevance': 0.6, 'recency': 0.2, 'depth': 0.1, 'authority': 0.1}},
            'changes': {'weights_updated': True}
        }

        params = {
            'weights': {'relevance': 0.6, 'recency': 0.2, 'depth': 0.1, 'authority': 0.1}
        }
        result = tools.configure_kb(action='update_ranking', params=params)

        self.assertEqual(result['action'], 'update_ranking')
        self.assertTrue(result['success'])
        self.assertIn('changes', result)
        mock_update_ranking.assert_called_once_with(
            weights={'relevance': 0.6, 'recency': 0.2, 'depth': 0.1, 'authority': 0.1},
            settings=None
        )

    @patch('mcp_server.tools.update_recommendation_domains')
    def test_update_domains_action(self, mock_update_domains):
        """Test update_domains action (AC 7)."""
        mock_update_domains.return_value = {
            'success': True,
            'quality_domains': ['martinfowler.com', 'newsite.com'],
            'changes': {'domains_added': ['newsite.com']}
        }

        params = {'add': ['newsite.com'], 'remove': ['oldsite.com']}
        result = tools.configure_kb(action='update_domains', params=params)

        self.assertEqual(result['action'], 'update_domains')
        self.assertTrue(result['success'])
        self.assertIn('changes', result)
        mock_update_domains.assert_called_once_with(
            add_domains=['newsite.com'],
            remove_domains=['oldsite.com']
        )

    @patch('mcp_server.tools.update_hot_sites_config')
    def test_update_hot_sites_action(self, mock_update_hot_sites):
        """Test update_hot_sites action (AC 8)."""
        mock_update_hot_sites.return_value = {
            'success': True,
            'category': 'ai',
            'domains': ['anthropic.com', 'newaisite.com'],
            'changes': {'domains_added': ['newaisite.com']}
        }

        params = {'category': 'ai', 'add': ['newaisite.com']}
        result = tools.configure_kb(action='update_hot_sites', params=params)

        self.assertEqual(result['action'], 'update_hot_sites')
        self.assertTrue(result['success'])
        self.assertEqual(result['category'], 'ai')
        mock_update_hot_sites.assert_called_once_with(
            category='ai',
            add_domains=['newaisite.com'],
            remove_domains=None,
            description=None
        )

    def test_invalid_action(self):
        """Test error handling for invalid action (AC 9)."""
        result = tools.configure_kb(action='invalid_action')

        self.assertIn('error', result)
        self.assertIn('Invalid action', result['error'])
        self.assertIn('valid_actions', result)

    def test_update_ranking_missing_params(self):
        """Test error handling when update_ranking missing required params (AC 10)."""
        result = tools.configure_kb(action='update_ranking', params={})

        self.assertIn('error', result)
        self.assertIn('requires weights or settings', result['error'])
        self.assertIn('example', result)

    def test_update_domains_missing_params(self):
        """Test error handling when update_domains missing required params (AC 10)."""
        result = tools.configure_kb(action='update_domains', params={})

        self.assertIn('error', result)
        self.assertIn('requires add or remove', result['error'])
        self.assertIn('example', result)

    def test_update_hot_sites_missing_category(self):
        """Test error handling when update_hot_sites missing category (AC 10)."""
        result = tools.configure_kb(action='update_hot_sites', params={'add': ['site.com']})

        self.assertIn('error', result)
        self.assertIn('requires category', result['error'])
        self.assertIn('example', result)


if __name__ == '__main__':
    unittest.main()
