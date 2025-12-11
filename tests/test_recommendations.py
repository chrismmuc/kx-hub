"""
Unit tests for reading recommendations (Story 3.5).

Tests the recommendation system including:
- Tavily client
- Query generation
- Quality filtering
- KB deduplication
- Main get_reading_recommendations() tool
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src/mcp_server'))


class TestTavilyClient(unittest.TestCase):
    """Test suite for Tavily API client."""

    @patch('mcp_server.tavily_client.get_tavily_api_key')
    @patch('tavily.TavilyClient')
    def test_search_success(self, mock_tavily_class, mock_get_key):
        """Test successful Tavily search."""
        from mcp_server import tavily_client

        # Reset global client
        tavily_client._tavily_client = None

        mock_get_key.return_value = 'test-api-key'

        # Mock Tavily client response
        mock_client = MagicMock()
        mock_client.search.return_value = {
            'results': [
                {
                    'title': 'Test Article',
                    'url': 'https://example.com/article',
                    'content': 'Article content snippet',
                    'published_date': '2025-12-01',
                    'score': 0.95
                }
            ]
        }
        mock_tavily_class.return_value = mock_client

        # Execute
        result = tavily_client.search(
            query='test query',
            include_domains=['example.com'],
            days=30,
            max_results=5
        )

        # Assertions
        self.assertEqual(result['query'], 'test query')
        self.assertEqual(result['result_count'], 1)
        self.assertEqual(result['results'][0]['title'], 'Test Article')
        self.assertEqual(result['results'][0]['domain'], 'example.com')

        # Cleanup
        tavily_client._tavily_client = None

    @patch('mcp_server.tavily_client.get_tavily_api_key')
    @patch('tavily.TavilyClient')
    def test_search_with_exclude_domains(self, mock_tavily_class, mock_get_key):
        """Test Tavily search with excluded domains."""
        from mcp_server import tavily_client

        tavily_client._tavily_client = None
        mock_get_key.return_value = 'test-api-key'

        mock_client = MagicMock()
        mock_client.search.return_value = {'results': []}
        mock_tavily_class.return_value = mock_client

        # Execute
        result = tavily_client.search(
            query='test',
            exclude_domains=['medium.com']
        )

        # Verify exclude_domains passed
        call_kwargs = mock_client.search.call_args[1]
        self.assertIn('exclude_domains', call_kwargs)
        self.assertEqual(call_kwargs['exclude_domains'], ['medium.com'])

        tavily_client._tavily_client = None

    def test_extract_domain(self):
        """Test domain extraction from URLs."""
        from mcp_server.tavily_client import _extract_domain

        self.assertEqual(_extract_domain('https://example.com/path'), 'example.com')
        self.assertEqual(_extract_domain('https://www.example.com/path'), 'example.com')
        self.assertEqual(_extract_domain('http://sub.example.com'), 'sub.example.com')
        self.assertEqual(_extract_domain('invalid'), '')


class TestRecommendationQueries(unittest.TestCase):
    """Test suite for smart query generation."""

    @patch('mcp_server.recommendation_queries.firestore_client.get_recent_chunks_with_cards')
    def test_get_recent_read_themes(self, mock_get_chunks):
        """Test theme extraction from recent reads."""
        from mcp_server import recommendation_queries

        mock_get_chunks.return_value = [
            {
                'author': 'Martin Fowler',
                'source': 'reader',
                'tags': ['architecture', 'microservices'],
                'knowledge_card': {
                    'takeaways': ['Microservices need clear boundaries', 'API design matters']
                }
            },
            {
                'author': 'Martin Fowler',
                'source': 'kindle',
                'tags': ['architecture', 'patterns'],
                'knowledge_card': {
                    'takeaways': ['Patterns reduce complexity']
                }
            }
        ]

        result = recommendation_queries.get_recent_read_themes(days=14)

        self.assertIn('themes', result)
        self.assertIn('architecture', result['themes'])
        self.assertEqual(result['authors'], ['Martin Fowler'])
        self.assertEqual(len(result['takeaways']), 3)

    @patch('mcp_server.recommendation_queries.firestore_client.get_top_clusters')
    def test_get_top_cluster_themes(self, mock_get_clusters):
        """Test cluster theme extraction."""
        from mcp_server import recommendation_queries

        mock_get_clusters.return_value = [
            {
                'id': 'cluster_1',
                'name': 'Platform Engineering',
                'description': 'Building developer platforms',
                'size': 50
            },
            {
                'id': 'cluster_2',
                'name': 'AI and Machine Learning',
                'description': 'ML concepts',
                'size': 40
            }
        ]

        result = recommendation_queries.get_top_cluster_themes(limit=5)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'Platform Engineering')
        self.assertEqual(result[1]['cluster_id'], 'cluster_2')

    @patch('mcp_server.recommendation_queries.get_top_cluster_themes')
    @patch('mcp_server.recommendation_queries.get_recent_read_themes')
    @patch('mcp_server.recommendation_queries.get_stale_cluster_themes')
    def test_generate_search_queries(self, mock_stale, mock_recent, mock_clusters):
        """Test smart query generation."""
        from mcp_server import recommendation_queries

        mock_clusters.return_value = [
            {'cluster_id': 'c1', 'name': 'Platform Engineering', 'description': '', 'size': 50}
        ]
        mock_recent.return_value = {
            'themes': ['microservices'],
            'takeaways': ['APIs should be versioned'],
            'authors': [],
            'sources': []
        }
        mock_stale.return_value = []

        result = recommendation_queries.generate_search_queries(scope='both', days=14)

        self.assertGreater(len(result), 0)
        # Should have at least cluster and theme queries
        sources = [q['source'] for q in result]
        self.assertIn('cluster', sources)
        self.assertIn('theme', sources)


class TestRecommendationFilter(unittest.TestCase):
    """Test suite for quality filtering and deduplication."""

    @patch('mcp_server.recommendation_filter.get_gemini_model')
    def test_score_content_depth(self, mock_get_model):
        """Test Gemini content depth scoring."""
        from mcp_server import recommendation_filter

        mock_model = MagicMock()
        mock_model.generate_content.return_value = MagicMock(
            text='{"score": 4, "reasoning": "In-depth technical analysis"}'
        )
        mock_get_model.return_value = mock_model

        result = recommendation_filter.score_content_depth(
            title='Platform Engineering Guide',
            content='Comprehensive guide to building...',
            url='https://example.com/guide'
        )

        self.assertEqual(result['depth_score'], 4)
        self.assertIn('reasoning', result)

    @patch('mcp_server.recommendation_filter.get_gemini_model')
    def test_score_content_depth_error_handling(self, mock_get_model):
        """Test error handling in depth scoring."""
        from mcp_server import recommendation_filter

        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception('API error')
        mock_get_model.return_value = mock_model

        result = recommendation_filter.score_content_depth(
            title='Test',
            content='Test content',
            url='https://example.com'
        )

        # Should return default score on error
        self.assertEqual(result['depth_score'], 3)
        self.assertIn('error', result)

    def test_generate_why_recommended_cluster(self):
        """Test why_recommended for cluster-based recommendations."""
        from mcp_server.recommendation_filter import generate_why_recommended

        rec = {'title': 'Test', 'url': 'https://example.com'}
        context = {
            'source': 'cluster',
            'context': {'cluster_name': 'Platform Engineering'}
        }

        result = generate_why_recommended(rec, context)

        self.assertIn('Platform Engineering', result)
        self.assertIn('cluster', result.lower())

    def test_generate_why_recommended_theme(self):
        """Test why_recommended for theme-based recommendations."""
        from mcp_server.recommendation_filter import generate_why_recommended

        rec = {'title': 'Test', 'url': 'https://example.com'}
        context = {
            'source': 'theme',
            'context': {'theme': 'microservices'}
        }

        result = generate_why_recommended(rec, context)

        self.assertIn('microservices', result.lower())

    @patch('mcp_server.recommendation_filter.firestore_client.find_nearest')
    @patch('mcp_server.recommendation_filter.embeddings.generate_query_embedding')
    def test_check_kb_duplicate(self, mock_embed, mock_find):
        """Test KB deduplication check."""
        from mcp_server.recommendation_filter import check_kb_duplicate

        mock_embed.return_value = [0.1] * 768
        mock_find.return_value = [
            {'id': 'chunk_1', 'title': 'Platform Engineering Guide'}
        ]

        # Test non-duplicate
        result = check_kb_duplicate(
            title='Completely Different Title',
            content='Different content'
        )
        self.assertFalse(result['is_duplicate'])

        # Test duplicate (similar title)
        result = check_kb_duplicate(
            title='Platform Engineering Guide 2025',
            content='Content about platforms'
        )
        # Title similarity check may flag this
        self.assertIn('similarity_score', result)

    @patch('mcp_server.recommendation_filter.score_content_depth')
    def test_trusted_source_boosts_credibility(self, mock_depth):
        """Trusted sources should boost credibility even if not in KB."""
        from mcp_server import recommendation_filter

        # Mock depth scoring to return passing score
        mock_depth.return_value = {'depth_score': 4, 'reasoning': 'Good content'}

        recommendations = [{
            'title': 'Great Article',
            'url': 'https://trusted.com/post',
            'domain': 'trusted.com',
            'content': 'Deep dive content',
            'published_date': '2025-12-01'  # Recent date
        }]
        contexts = [{'source': 'search', 'context': {}}]

        result = recommendation_filter.filter_recommendations(
            recommendations=recommendations,
            query_contexts=contexts,
            check_duplicates=False,
            known_authors=[],
            known_sources=[],
            trusted_sources=['trusted.com']
        )

        rec = result['recommendations'][0]
        self.assertGreaterEqual(rec['credibility_score'], 0.5)
        self.assertIn('Trusted', rec['why_recommended'])


class TestGetReadingRecommendations(unittest.TestCase):
    """Test suite for the main get_reading_recommendations() tool."""

    @patch('mcp_server.tools.firestore_client.get_recommendation_config')
    def test_invalid_scope(self, mock_config):
        """Test error handling for invalid scope."""
        from mcp_server import tools

        result = tools.get_reading_recommendations(scope='invalid')

        self.assertIn('error', result)
        self.assertIn('Invalid scope', result['error'])

    @patch('recommendation_queries.generate_search_queries')
    @patch('firestore_client.get_recommendation_config')
    def test_no_queries_generated(self, mock_config, mock_queries):
        """Test handling when no queries are generated."""
        from mcp_server import tools

        mock_config.return_value = {'quality_domains': [], 'excluded_domains': []}
        mock_queries.return_value = []

        result = tools.get_reading_recommendations(scope='both')

        self.assertIn('error', result)
        self.assertIn('No queries', result['error'])
        self.assertEqual(result['recommendations'], [])

    @patch('recommendation_filter.filter_recommendations')
    @patch('tavily_client.search')
    @patch('recommendation_queries.format_query_for_tavily')
    @patch('recommendation_queries.generate_search_queries')
    @patch('firestore_client.get_recommendation_config')
    def test_full_flow(self, mock_config, mock_queries, mock_format, mock_tavily, mock_filter):
        """Test full recommendation flow."""
        from mcp_server import tools

        mock_config.return_value = {
            'quality_domains': ['example.com'],
            'excluded_domains': []
        }
        mock_queries.return_value = [
            {'query': 'test query', 'source': 'cluster', 'context': {'cluster_name': 'Test'}}
        ]
        mock_format.return_value = 'test query'
        mock_tavily.return_value = {
            'results': [
                {
                    'title': 'Test Article',
                    'url': 'https://example.com/article',
                    'content': 'Test content',
                    'domain': 'example.com',
                    'score': 0.9
                }
            ]
        }
        mock_filter.return_value = {
            'recommendations': [
                {
                    'title': 'Test Article',
                    'url': 'https://example.com/article',
                    'depth_score': 4,
                    'why_recommended': 'Test reason'
                }
            ],
            'filtered_out': {'duplicate_count': 0}
        }

        result = tools.get_reading_recommendations(scope='both', days=14, limit=10)

        self.assertIn('recommendations', result)
        self.assertEqual(len(result['recommendations']), 1)
        self.assertIn('generated_at', result)
        self.assertIn('queries_used', result)


class TestUpdateRecommendationDomains(unittest.TestCase):
    """Test suite for update_recommendation_domains() tool."""

    @patch('mcp_server.tools.firestore_client.update_recommendation_config')
    def test_add_domains(self, mock_update):
        """Test adding domains to whitelist."""
        from mcp_server import tools

        mock_update.return_value = {
            'success': True,
            'config': {
                'quality_domains': ['example.com', 'newsite.com'],
                'excluded_domains': []
            },
            'changes': {'domains_added': ['newsite.com']}
        }

        result = tools.update_recommendation_domains(add_domains=['newsite.com'])

        self.assertTrue(result['success'])
        self.assertIn('newsite.com', result['quality_domains'])
        self.assertEqual(result['changes']['domains_added'], ['newsite.com'])

    @patch('mcp_server.tools.firestore_client.update_recommendation_config')
    def test_remove_domains(self, mock_update):
        """Test removing domains from whitelist."""
        from mcp_server import tools

        mock_update.return_value = {
            'success': True,
            'config': {
                'quality_domains': ['example.com'],
                'excluded_domains': []
            },
            'changes': {'domains_removed': ['oldsite.com']}
        }

        result = tools.update_recommendation_domains(remove_domains=['oldsite.com'])

        self.assertTrue(result['success'])
        self.assertNotIn('oldsite.com', result['quality_domains'])

    @patch('mcp_server.tools.firestore_client.update_recommendation_config')
    def test_update_error(self, mock_update):
        """Test error handling in domain update."""
        from mcp_server import tools

        mock_update.return_value = {
            'success': False,
            'error': 'Database error'
        }

        result = tools.update_recommendation_domains(add_domains=['test.com'])

        self.assertFalse(result['success'])
        self.assertIn('error', result)


class TestFirestoreConfigMethods(unittest.TestCase):
    """Test suite for Firestore config methods."""

    @patch('mcp_server.firestore_client.get_firestore_client')
    def test_get_recommendation_config_creates_default(self, mock_get_db):
        """Test that default config is created if not exists."""
        from mcp_server import firestore_client

        mock_doc = MagicMock()
        mock_doc.exists = False

        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value = mock_doc

        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc_ref

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        result = firestore_client.get_recommendation_config()

        # Should create default config
        self.assertIn('quality_domains', result)
        self.assertIn('martinfowler.com', result['quality_domains'])
        mock_doc_ref.set.assert_called_once()

    @patch('mcp_server.firestore_client.get_firestore_client')
    def test_get_recommendation_config_returns_existing(self, mock_get_db):
        """Test retrieval of existing config."""
        from mcp_server import firestore_client

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            'quality_domains': ['custom.com'],
            'excluded_domains': ['blocked.com']
        }

        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value = mock_doc

        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc_ref

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        result = firestore_client.get_recommendation_config()

        self.assertEqual(result['quality_domains'], ['custom.com'])
        self.assertEqual(result['excluded_domains'], ['blocked.com'])


if __name__ == '__main__':
    unittest.main()
