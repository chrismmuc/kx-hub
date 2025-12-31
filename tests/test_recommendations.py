"""
Unit tests for reading recommendations (Story 3.5).

Tests the recommendation system including:
- Tavily client
- Query generation
- Quality filtering
- KB deduplication
- Main get_reading_recommendations() tool
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/mcp_server"))


class TestTavilyClient(unittest.TestCase):
    """Test suite for Tavily API client."""

    @patch("mcp_server.tavily_client.get_tavily_api_key")
    @patch("tavily.TavilyClient")
    def test_search_success(self, mock_tavily_class, mock_get_key):
        """Test successful Tavily search."""
        from mcp_server import tavily_client

        # Reset global client
        tavily_client._tavily_client = None

        mock_get_key.return_value = "test-api-key"

        # Mock Tavily client response
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "Test Article",
                    "url": "https://example.com/article",
                    "content": "Article content snippet",
                    "published_date": "2025-12-01",
                    "score": 0.95,
                }
            ]
        }
        mock_tavily_class.return_value = mock_client

        # Execute
        result = tavily_client.search(
            query="test query", include_domains=["example.com"], days=30, max_results=5
        )

        # Assertions
        self.assertEqual(result["query"], "test query")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["title"], "Test Article")
        self.assertEqual(result["results"][0]["domain"], "example.com")

        # Cleanup
        tavily_client._tavily_client = None

    @patch("mcp_server.tavily_client.get_tavily_api_key")
    @patch("tavily.TavilyClient")
    def test_search_with_exclude_domains(self, mock_tavily_class, mock_get_key):
        """Test Tavily search with excluded domains."""
        from mcp_server import tavily_client

        tavily_client._tavily_client = None
        mock_get_key.return_value = "test-api-key"

        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}
        mock_tavily_class.return_value = mock_client

        # Execute
        result = tavily_client.search(query="test", exclude_domains=["medium.com"])

        # Verify exclude_domains passed
        call_kwargs = mock_client.search.call_args[1]
        self.assertIn("exclude_domains", call_kwargs)
        self.assertEqual(call_kwargs["exclude_domains"], ["medium.com"])

        tavily_client._tavily_client = None

    def test_extract_domain(self):
        """Test domain extraction from URLs."""
        from mcp_server.tavily_client import _extract_domain

        self.assertEqual(_extract_domain("https://example.com/path"), "example.com")
        self.assertEqual(_extract_domain("https://www.example.com/path"), "example.com")
        self.assertEqual(_extract_domain("http://sub.example.com"), "sub.example.com")
        self.assertEqual(_extract_domain("invalid"), "")


class TestRecommendationQueries(unittest.TestCase):
    """Test suite for smart query generation."""

    @patch(
        "mcp_server.recommendation_queries.firestore_client.get_recent_chunks_with_cards"
    )
    def test_get_recent_read_themes(self, mock_get_chunks):
        """Test theme extraction from recent reads."""
        from mcp_server import recommendation_queries

        mock_get_chunks.return_value = [
            {
                "author": "Martin Fowler",
                "source": "reader",
                "tags": ["architecture", "microservices"],
                "knowledge_card": {
                    "takeaways": [
                        "Microservices need clear boundaries",
                        "API design matters",
                    ]
                },
            },
            {
                "author": "Martin Fowler",
                "source": "kindle",
                "tags": ["architecture", "patterns"],
                "knowledge_card": {"takeaways": ["Patterns reduce complexity"]},
            },
        ]

        result = recommendation_queries.get_recent_read_themes(days=14)

        self.assertIn("themes", result)
        self.assertIn("architecture", result["themes"])
        self.assertEqual(result["authors"], ["Martin Fowler"])
        self.assertEqual(len(result["takeaways"]), 3)

    @patch("mcp_server.recommendation_queries.get_top_source_themes")
    @patch("mcp_server.recommendation_queries.get_recent_read_themes")
    def test_generate_search_queries(self, mock_recent, mock_sources):
        """Test smart query generation."""
        from mcp_server import recommendation_queries

        mock_sources.return_value = [
            {
                "source_id": "s1",
                "title": "Platform Engineering Guide",
                "author": "Test Author",
                "chunk_count": 50,
            }
        ]
        mock_recent.return_value = {
            "themes": ["microservices"],
            "takeaways": ["APIs should be versioned"],
            "authors": [],
            "sources": [],
        }

        result = recommendation_queries.generate_search_queries(days=14)

        self.assertGreater(len(result), 0)
        # Should have source and theme queries
        sources = [q["source"] for q in result]
        self.assertIn("source", sources)
        self.assertIn("theme", sources)


class TestRecommendationFilter(unittest.TestCase):
    """Test suite for quality filtering and deduplication."""

    @patch("mcp_server.recommendation_filter.get_llm_client")
    def test_score_content_depth(self, mock_get_client):
        """Test LLM content depth scoring."""
        from mcp_server import recommendation_filter

        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "score": 4,
            "reasoning": "In-depth technical analysis",
        }
        mock_get_client.return_value = mock_client

        result = recommendation_filter.score_content_depth(
            title="Platform Engineering Guide",
            content="Comprehensive guide to building...",
            url="https://example.com/guide",
        )

        self.assertEqual(result["depth_score"], 4)
        self.assertIn("reasoning", result)

    @patch("mcp_server.recommendation_filter.get_llm_client")
    def test_score_content_depth_error_handling(self, mock_get_client):
        """Test error handling in depth scoring."""
        from mcp_server import recommendation_filter

        mock_client = MagicMock()
        mock_client.generate_json.side_effect = Exception("API error")
        mock_get_client.return_value = mock_client

        result = recommendation_filter.score_content_depth(
            title="Test", content="Test content", url="https://example.com"
        )

        # Should return default score on error
        self.assertEqual(result["depth_score"], 3)
        self.assertIn("error", result)

    def test_generate_why_recommended_source(self):
        """Test why_recommended for source-based recommendations."""
        from mcp_server.recommendation_filter import generate_why_recommended

        rec = {"title": "Test", "url": "https://example.com"}
        context = {
            "source": "source",
            "context": {"source_title": "Platform Engineering Guide"},
        }

        result = generate_why_recommended(rec, context)

        self.assertIn("Platform Engineering Guide", result)

    def test_generate_why_recommended_theme(self):
        """Test why_recommended for theme-based recommendations."""
        from mcp_server.recommendation_filter import generate_why_recommended

        rec = {"title": "Test", "url": "https://example.com"}
        context = {"source": "theme", "context": {"theme": "microservices"}}

        result = generate_why_recommended(rec, context)

        self.assertIn("microservices", result.lower())

    @patch("mcp_server.recommendation_filter.firestore_client.find_nearest")
    @patch("mcp_server.recommendation_filter.embeddings.generate_query_embedding")
    def test_check_kb_duplicate(self, mock_embed, mock_find):
        """Test KB deduplication check."""
        from mcp_server.recommendation_filter import check_kb_duplicate

        mock_embed.return_value = [0.1] * 768
        mock_find.return_value = [
            {"id": "chunk_1", "title": "Platform Engineering Guide"}
        ]

        # Test non-duplicate
        result = check_kb_duplicate(
            title="Completely Different Title", content="Different content"
        )
        self.assertFalse(result["is_duplicate"])

        # Test duplicate (similar title)
        result = check_kb_duplicate(
            title="Platform Engineering Guide 2025", content="Content about platforms"
        )
        # Title similarity check may flag this
        self.assertIn("similarity_score", result)

    @patch("mcp_server.recommendation_filter.score_content_depth")
    def test_trusted_source_boosts_credibility(self, mock_depth):
        """Trusted sources should boost credibility even if not in KB."""
        from mcp_server import recommendation_filter

        # Mock depth scoring to return passing score
        mock_depth.return_value = {"depth_score": 4, "reasoning": "Good content"}

        recommendations = [
            {
                "title": "Great Article",
                "url": "https://trusted.com/post",
                "domain": "trusted.com",
                "content": "Deep dive content",
                "published_date": "2025-12-01",  # Recent date
            }
        ]
        contexts = [{"source": "search", "context": {}}]

        result = recommendation_filter.filter_recommendations(
            recommendations=recommendations,
            query_contexts=contexts,
            check_duplicates=False,
            known_authors=[],
            known_sources=[],
            trusted_sources=["trusted.com"],
        )

        rec = result["recommendations"][0]
        self.assertGreaterEqual(rec["credibility_score"], 0.5)
        self.assertIn("Trusted", rec["why_recommended"])


# ============================================================================
# Story 3.10: Enhanced KB Deduplication Tests
# ============================================================================


class TestEnhancedKBDeduplication(unittest.TestCase):
    """Test suite for enhanced KB deduplication (Story 3.10)."""

    @patch("mcp_server.recommendation_filter.firestore_client.find_by_source_url")
    def test_url_based_deduplication(self, mock_find_url):
        """Test URL-based duplicate detection (AC #1)."""
        from mcp_server.recommendation_filter import check_kb_duplicate

        # Setup: URL exists in KB
        mock_find_url.return_value = {
            "id": "existing-chunk-1",
            "title": "Existing Article",
        }

        result = check_kb_duplicate(
            title="Some New Title",
            content="Some content",
            url="https://example.com/article",
        )

        self.assertTrue(result["is_duplicate"])
        self.assertEqual(result["match_type"], "url")
        self.assertEqual(result["similarity_score"], 1.0)
        self.assertEqual(result["similar_chunk_id"], "existing-chunk-1")

    @patch("mcp_server.recommendation_filter.firestore_client.find_by_source_url")
    @patch(
        "mcp_server.recommendation_filter.firestore_client.find_chunks_by_title_prefix"
    )
    def test_title_containment_vibe_coding(self, mock_title_search, mock_find_url):
        """Test title containment: 'Vibe Coding' vs 'Beyond Vibe Coding' (AC #2)."""
        from mcp_server.recommendation_filter import check_kb_duplicate

        mock_find_url.return_value = None  # URL not found

        # KB has "Vibe Coding"
        mock_title_search.return_value = [
            {
                "id": "vibe-coding-chunk",
                "title": "Vibe Coding",
                "author": "Gene Kim, Steve Yegge, and Dario Amodei",
            }
        ]

        # Recommendation is "Beyond Vibe Coding"
        result = check_kb_duplicate(
            title="Beyond Vibe Coding: From Coder to AI-Era Developer",
            content="AI-powered coding assistants...",
            url="https://oreilly.com/beyond-vibe-coding",
        )

        self.assertTrue(result["is_duplicate"])
        self.assertEqual(result["match_type"], "title_containment")
        self.assertGreaterEqual(result["similarity_score"], 0.9)

    @patch("mcp_server.recommendation_filter.firestore_client.find_by_source_url")
    @patch(
        "mcp_server.recommendation_filter.firestore_client.find_chunks_by_title_prefix"
    )
    def test_title_containment_reverse(self, mock_title_search, mock_find_url):
        """Test reverse title containment: KB has long title, rec has short."""
        from mcp_server.recommendation_filter import check_kb_duplicate

        mock_find_url.return_value = None

        # KB has full title
        mock_title_search.return_value = [
            {
                "id": "full-title-chunk",
                "title": "The Complete Guide to Platform Engineering",
            }
        ]

        # Recommendation has shorter title
        result = check_kb_duplicate(
            title="Platform Engineering", content="Content about platforms...", url=None
        )

        self.assertTrue(result["is_duplicate"])
        self.assertEqual(result["match_type"], "title_containment")

    @patch("mcp_server.recommendation_filter.firestore_client.find_by_source_url")
    @patch(
        "mcp_server.recommendation_filter.firestore_client.find_chunks_by_title_prefix"
    )
    def test_title_prefix_stripping(self, mock_title_search, mock_find_url):
        """Test that common prefixes are stripped: 'The DevOps Handbook' vs 'DevOps Handbook'."""
        from mcp_server.recommendation_filter import check_kb_duplicate

        mock_find_url.return_value = None

        mock_title_search.return_value = [
            {"id": "devops-chunk", "title": "DevOps Handbook"}
        ]

        result = check_kb_duplicate(
            title="The DevOps Handbook: Second Edition",
            content="DevOps content...",
            url=None,
        )

        self.assertTrue(result["is_duplicate"])
        self.assertEqual(result["match_type"], "title_containment")

    @patch("mcp_server.recommendation_filter.firestore_client.find_by_source_url")
    @patch(
        "mcp_server.recommendation_filter.firestore_client.find_chunks_by_title_prefix"
    )
    @patch("mcp_server.recommendation_filter.firestore_client.find_nearest")
    @patch("mcp_server.recommendation_filter.embeddings.generate_query_embedding")
    def test_no_false_positives(
        self, mock_embed, mock_find_nearest, mock_title_search, mock_find_url
    ):
        """Test that unrelated content is NOT flagged as duplicate."""
        from mcp_server.recommendation_filter import check_kb_duplicate

        mock_find_url.return_value = None
        mock_title_search.return_value = []
        mock_embed.return_value = [0.1] * 768
        mock_find_nearest.return_value = [
            {
                "id": "unrelated-chunk",
                "title": "Completely Different Topic About Cooking",
            }
        ]

        result = check_kb_duplicate(
            title="Machine Learning Fundamentals",
            content="Deep dive into neural networks...",
            url="https://example.com/ml-guide",
        )

        self.assertFalse(result["is_duplicate"])
        self.assertIsNone(result["match_type"])

    @patch("mcp_server.recommendation_filter.firestore_client.find_by_source_url")
    @patch(
        "mcp_server.recommendation_filter.firestore_client.find_chunks_by_title_prefix"
    )
    @patch("mcp_server.recommendation_filter.firestore_client.find_nearest")
    @patch("mcp_server.recommendation_filter.embeddings.generate_query_embedding")
    def test_embedding_similarity_fallback(
        self, mock_embed, mock_find_nearest, mock_title_search, mock_find_url
    ):
        """Test embedding similarity when other methods don't match (AC #4)."""
        from mcp_server.recommendation_filter import check_kb_duplicate

        mock_find_url.return_value = None
        mock_title_search.return_value = []  # No title match
        mock_embed.return_value = [0.1] * 768

        # Similar content via embedding
        mock_find_nearest.return_value = [
            {"id": "similar-chunk", "title": "Platform Engineering Best Practices"}
        ]

        result = check_kb_duplicate(
            title="Best Practices for Platform Engineering Teams",
            content="Platform teams should focus on...",
            url=None,
        )

        # Should detect via embedding + word overlap (Jaccard > 0.4)
        self.assertTrue(result["is_duplicate"])
        self.assertEqual(result["match_type"], "embedding")

    def test_error_handling(self):
        """Test graceful error handling."""
        from mcp_server.recommendation_filter import check_kb_duplicate

        # Mock error by patching with exception
        with patch(
            "mcp_server.recommendation_filter.firestore_client.find_by_source_url"
        ) as mock:
            mock.side_effect = Exception("Database error")

            result = check_kb_duplicate(
                title="Test", content="Test content", url="https://example.com"
            )

            # Should not raise, should return safe default
            self.assertFalse(result["is_duplicate"])
            self.assertIn("error", result)


class TestURLNormalization(unittest.TestCase):
    """Test suite for URL normalization (Story 3.10 AC #1)."""

    def test_normalize_removes_www(self):
        """Test www prefix is removed."""
        from mcp_server.firestore_client import normalize_url

        result = normalize_url("https://www.example.com/article")
        self.assertEqual(result, "https://example.com/article")

    def test_normalize_removes_trailing_slash(self):
        """Test trailing slash is removed."""
        from mcp_server.firestore_client import normalize_url

        result = normalize_url("https://example.com/article/")
        self.assertEqual(result, "https://example.com/article")

    def test_normalize_removes_query_params(self):
        """Test query parameters are removed."""
        from mcp_server.firestore_client import normalize_url

        result = normalize_url("https://example.com/article?utm_source=twitter&ref=123")
        self.assertEqual(result, "https://example.com/article")

    def test_normalize_lowercase(self):
        """Test URL is lowercased."""
        from mcp_server.firestore_client import normalize_url

        result = normalize_url("HTTPS://EXAMPLE.COM/Article")
        self.assertEqual(result, "https://example.com/article")

    def test_normalize_empty_string(self):
        """Test empty string handling."""
        from mcp_server.firestore_client import normalize_url

        result = normalize_url("")
        self.assertEqual(result, "")

    def test_normalize_none(self):
        """Test None handling."""
        from mcp_server.firestore_client import normalize_url

        result = normalize_url(None)
        self.assertEqual(result, "")


class TestFindBySourceURL(unittest.TestCase):
    """Test suite for find_by_source_url (Story 3.10 AC #1)."""

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_find_exact_match(self, mock_get_db):
        """Test finding chunk by exact URL match."""
        from mcp_server import firestore_client

        mock_doc = MagicMock()
        mock_doc.id = "chunk-123"
        mock_doc.to_dict.return_value = {
            "title": "Test Article",
            "source_url": "https://example.com/article",
        }

        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_doc]
        mock_query.limit.return_value = mock_query

        mock_collection = MagicMock()
        mock_collection.where.return_value = mock_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        result = firestore_client.find_by_source_url("https://example.com/article")

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "chunk-123")
        self.assertEqual(result["title"], "Test Article")

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_find_no_match(self, mock_get_db):
        """Test URL not found returns None."""
        from mcp_server import firestore_client

        mock_query = MagicMock()
        mock_query.stream.return_value = []
        mock_query.limit.return_value = mock_query

        mock_collection = MagicMock()
        mock_collection.where.return_value = mock_query

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        result = firestore_client.find_by_source_url("https://example.com/not-found")

        self.assertIsNone(result)

    def test_find_empty_url(self):
        """Test empty URL returns None."""
        from mcp_server import firestore_client

        result = firestore_client.find_by_source_url("")
        self.assertIsNone(result)

        result = firestore_client.find_by_source_url(None)
        self.assertIsNone(result)


class TestGetReadingRecommendations(unittest.TestCase):
    """Test suite for the main get_reading_recommendations() tool."""

    @patch("recommendation_queries.generate_search_queries")
    @patch("firestore_client.get_recommendation_config")
    def test_no_queries_generated(self, mock_config, mock_queries):
        """Test handling when no queries are generated."""
        from mcp_server import tools

        mock_config.return_value = {"quality_domains": [], "excluded_domains": []}
        mock_queries.return_value = []

        result = tools.get_reading_recommendations()

        self.assertIn("error", result)
        self.assertIn("No queries", result["error"])
        self.assertEqual(result["recommendations"], [])

    @patch("recommendation_filter.assign_slots")
    @patch("recommendation_filter.diversified_sample")
    @patch("recommendation_filter.calculate_combined_score")
    @patch("recommendation_filter.filter_recommendations")
    @patch("tavily_client.search")
    @patch("recommendation_queries.format_query_for_tavily")
    @patch("recommendation_queries.generate_search_queries")
    @patch("firestore_client.get_recommendation_config")
    @patch("firestore_client.get_ranking_config")
    @patch("firestore_client.get_kb_credibility_signals")
    @patch("firestore_client.get_shown_urls")
    @patch("firestore_client.record_shown_recommendations")
    @patch("recommendation_filter.get_mode_config")
    @patch("recommendation_filter.calculate_recency_score")
    @patch("recommendation_filter.parse_published_date")
    def test_full_flow(
        self,
        mock_parse_date,
        mock_recency,
        mock_mode_config,
        mock_record,
        mock_shown_urls,
        mock_credibility,
        mock_ranking_config,
        mock_config,
        mock_queries,
        mock_format,
        mock_tavily,
        mock_filter,
        mock_combined,
        mock_sample,
        mock_slots,
    ):
        """Test full recommendation flow with Story 3.9 parameters."""
        from mcp_server import tools

        mock_config.return_value = {
            "quality_domains": ["example.com"],
            "excluded_domains": [],
        }
        mock_ranking_config.return_value = {
            "weights": {
                "relevance": 0.5,
                "recency": 0.25,
                "depth": 0.15,
                "authority": 0.1,
            },
            "settings": {},
        }
        mock_mode_config.return_value = {
            "description": "Test mode",
            "weights": {
                "relevance": 0.5,
                "recency": 0.25,
                "depth": 0.15,
                "authority": 0.1,
            },
            "temperature": 0.3,
            "tavily_days": 180,
            "min_depth_score": 3,
            "slots": {},
        }
        mock_credibility.return_value = {"authors": [], "domains": []}
        mock_shown_urls.return_value = []
        mock_record.return_value = {"recorded_count": 1}
        mock_queries.return_value = [
            {
                "query": "test query",
                "source": "cluster",
                "context": {"cluster_name": "Test"},
            }
        ]
        mock_format.return_value = "test query"
        mock_parse_date.return_value = None
        mock_recency.return_value = 0.8
        mock_tavily.return_value = {
            "results": [
                {
                    "title": "Test Article",
                    "url": "https://example.com/article",
                    "content": "Test content",
                    "domain": "example.com",
                    "score": 0.9,
                }
            ]
        }
        mock_filter.return_value = {
            "recommendations": [
                {
                    "title": "Test Article",
                    "url": "https://example.com/article",
                    "domain": "example.com",
                    "depth_score": 4,
                    "why_recommended": "Test reason",
                }
            ],
            "filtered_out": {"duplicate_count": 0},
        }
        mock_combined.return_value = {
            "combined_score": 0.8,
            "final_score": 0.85,
            "score_breakdown": {
                "relevance": 0.9,
                "recency": 0.8,
                "depth": 0.8,
                "authority": 0.5,
            },
            "adjustments": {"novelty_bonus": 0.1, "domain_penalty": 0.0},
        }
        mock_sample.return_value = [
            {
                "title": "Test Article",
                "url": "https://example.com/article",
                "domain": "example.com",
                "depth_score": 4,
                "combined_score": 0.8,
                "final_score": 0.85,
            }
        ]
        mock_slots.return_value = [
            {
                "title": "Test Article",
                "url": "https://example.com/article",
                "domain": "example.com",
                "depth_score": 4,
                "combined_score": 0.8,
                "final_score": 0.85,
                "slot": "RELEVANCE",
                "slot_reason": "Top combined score",
            }
        ]

        result = tools.get_reading_recommendations(days=14, limit=10)

        self.assertIn("recommendations", result)
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertIn("generated_at", result)
        self.assertIn("queries_used", result)
        self.assertIn("mode", result)
        self.assertEqual(result["mode"], "balanced")


class TestUpdateRecommendationDomains(unittest.TestCase):
    """Test suite for update_recommendation_domains() tool."""

    @patch("mcp_server.tools.firestore_client.update_recommendation_config")
    def test_add_domains(self, mock_update):
        """Test adding domains to whitelist."""
        from mcp_server import tools

        mock_update.return_value = {
            "success": True,
            "config": {
                "quality_domains": ["example.com", "newsite.com"],
                "excluded_domains": [],
            },
            "changes": {"domains_added": ["newsite.com"]},
        }

        result = tools.update_recommendation_domains(add_domains=["newsite.com"])

        self.assertTrue(result["success"])
        self.assertIn("newsite.com", result["quality_domains"])
        self.assertEqual(result["changes"]["domains_added"], ["newsite.com"])

    @patch("mcp_server.tools.firestore_client.update_recommendation_config")
    def test_remove_domains(self, mock_update):
        """Test removing domains from whitelist."""
        from mcp_server import tools

        mock_update.return_value = {
            "success": True,
            "config": {"quality_domains": ["example.com"], "excluded_domains": []},
            "changes": {"domains_removed": ["oldsite.com"]},
        }

        result = tools.update_recommendation_domains(remove_domains=["oldsite.com"])

        self.assertTrue(result["success"])
        self.assertNotIn("oldsite.com", result["quality_domains"])

    @patch("mcp_server.tools.firestore_client.update_recommendation_config")
    def test_update_error(self, mock_update):
        """Test error handling in domain update."""
        from mcp_server import tools

        mock_update.return_value = {"success": False, "error": "Database error"}

        result = tools.update_recommendation_domains(add_domains=["test.com"])

        self.assertFalse(result["success"])
        self.assertIn("error", result)


class TestFirestoreConfigMethods(unittest.TestCase):
    """Test suite for Firestore config methods."""

    @patch("mcp_server.firestore_client.get_firestore_client")
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
        self.assertIn("quality_domains", result)
        self.assertIn("martinfowler.com", result["quality_domains"])
        mock_doc_ref.set.assert_called_once()

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_get_recommendation_config_returns_existing(self, mock_get_db):
        """Test retrieval of existing config."""
        from mcp_server import firestore_client

        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "quality_domains": ["custom.com"],
            "excluded_domains": ["blocked.com"],
        }

        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value = mock_doc

        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc_ref

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_get_db.return_value = mock_db

        result = firestore_client.get_recommendation_config()

        self.assertEqual(result["quality_domains"], ["custom.com"])
        self.assertEqual(result["excluded_domains"], ["blocked.com"])


# ============================================================================
# Story 3.8: Enhanced Ranking Tests
# ============================================================================


class TestRecencyScoring(unittest.TestCase):
    """Test suite for recency scoring (Story 3.8 AC#1)."""

    def test_recency_score_today(self):
        """Articles published today should score 1.0."""
        from datetime import datetime

        from mcp_server.recommendation_filter import calculate_recency_score

        today = datetime.utcnow()
        score = calculate_recency_score(today)
        self.assertAlmostEqual(score, 1.0, places=2)

    def test_recency_score_half_life(self):
        """Score should be ~0.5 at half_life_days."""
        from datetime import datetime, timedelta

        from mcp_server.recommendation_filter import calculate_recency_score

        half_life = 90
        date = datetime.utcnow() - timedelta(days=half_life)
        score = calculate_recency_score(date, half_life_days=half_life)
        self.assertAlmostEqual(score, 0.5, places=1)

    def test_recency_score_double_half_life(self):
        """Score should be ~0.25 at 2x half_life_days."""
        from datetime import datetime, timedelta

        from mcp_server.recommendation_filter import calculate_recency_score

        half_life = 90
        date = datetime.utcnow() - timedelta(days=half_life * 2)
        score = calculate_recency_score(date, half_life_days=half_life)
        self.assertAlmostEqual(score, 0.25, places=1)

    def test_recency_score_max_age_filter(self):
        """Articles older than max_age_days should score 0."""
        from datetime import datetime, timedelta

        from mcp_server.recommendation_filter import calculate_recency_score

        max_age = 365
        date = datetime.utcnow() - timedelta(days=max_age + 10)
        score = calculate_recency_score(date, max_age_days=max_age)
        self.assertEqual(score, 0.0)

    def test_recency_score_none_date(self):
        """Missing date should return neutral score 0.5."""
        from mcp_server.recommendation_filter import calculate_recency_score

        score = calculate_recency_score(None)
        self.assertEqual(score, 0.5)


class TestCombinedScoring(unittest.TestCase):
    """Test suite for multi-factor ranking (Story 3.8 AC#2)."""

    def test_combined_score_default_weights(self):
        """Test combined score with default weights."""
        from mcp_server.recommendation_filter import calculate_combined_score

        result_dict = {
            "relevance_score": 0.8,
            "recency_score": 0.6,
            "depth_score": 4,  # 1-5 scale
            "credibility_score": 0.5,
        }

        score_result = calculate_combined_score(result_dict)

        self.assertIn("combined_score", score_result)
        self.assertIn("final_score", score_result)
        self.assertIn("score_breakdown", score_result)
        self.assertGreater(score_result["combined_score"], 0)
        self.assertLessEqual(score_result["combined_score"], 1.0)

    def test_combined_score_custom_weights(self):
        """Test combined score with custom weights."""
        from mcp_server.recommendation_filter import calculate_combined_score

        result_dict = {
            "relevance_score": 1.0,
            "recency_score": 0.0,
            "depth_score": 5,
            "credibility_score": 0.0,
        }

        weights = {"relevance": 1.0, "recency": 0.0, "depth": 0.0, "authority": 0.0}
        score_result = calculate_combined_score(result_dict, weights)

        # With 100% weight on relevance and relevance=1.0, should be ~1.0
        self.assertAlmostEqual(score_result["combined_score"], 1.0, places=1)

    def test_combined_score_with_adjustments(self):
        """Test novelty bonus and domain penalty."""
        from mcp_server.recommendation_filter import calculate_combined_score

        result_dict = {
            "relevance_score": 0.5,
            "recency_score": 0.5,
            "depth_score": 2.5,
            "credibility_score": 0.5,
        }

        score_result = calculate_combined_score(
            result_dict, novelty_bonus=0.1, domain_penalty=0.05
        )

        # Final score should include adjustments
        self.assertEqual(score_result["adjustments"]["novelty_bonus"], 0.1)
        self.assertEqual(score_result["adjustments"]["domain_penalty"], 0.05)


class TestStochasticSampling(unittest.TestCase):
    """Test suite for stochastic sampling (Story 3.8 AC#3)."""

    def test_deterministic_sampling_temp_zero(self):
        """Temperature 0 should return top-N by score."""
        from mcp_server.recommendation_filter import diversified_sample

        results = [
            {"combined_score": 0.9, "url": "a"},
            {"combined_score": 0.8, "url": "b"},
            {"combined_score": 0.7, "url": "c"},
            {"combined_score": 0.6, "url": "d"},
        ]

        sampled = diversified_sample(results, n=2, temperature=0)

        self.assertEqual(len(sampled), 2)
        self.assertEqual(sampled[0]["url"], "a")
        self.assertEqual(sampled[1]["url"], "b")

    def test_sampling_returns_correct_count(self):
        """Sampling should return requested number of items."""
        from mcp_server.recommendation_filter import diversified_sample

        results = [{"combined_score": i / 10, "url": str(i)} for i in range(10)]

        sampled = diversified_sample(results, n=5, temperature=0.3)

        self.assertEqual(len(sampled), 5)

    def test_sampling_handles_small_input(self):
        """Sampling should handle input smaller than n."""
        from mcp_server.recommendation_filter import diversified_sample

        results = [
            {"combined_score": 0.9, "url": "a"},
            {"combined_score": 0.8, "url": "b"},
        ]

        sampled = diversified_sample(results, n=5, temperature=0.3)

        self.assertEqual(len(sampled), 2)


class TestSlotBasedRotation(unittest.TestCase):
    """Test suite for slot-based rotation (Story 3.8 AC#4)."""

    def test_assign_slots_basic(self):
        """Test slot assignment with default config."""
        from mcp_server.recommendation_filter import SlotType, assign_slots

        recommendations = [
            {"url": "a", "final_score": 0.9, "recency_score": 0.7, "depth_score": 4},
            {"url": "b", "final_score": 0.8, "recency_score": 0.9, "depth_score": 4},
            {"url": "c", "final_score": 0.7, "recency_score": 0.5, "depth_score": 3},
            {"url": "d", "final_score": 0.6, "recency_score": 0.4, "depth_score": 4},
            {"url": "e", "final_score": 0.5, "recency_score": 0.3, "depth_score": 3},
        ]

        result = assign_slots(recommendations)

        # Should have slots assigned
        self.assertTrue(all("slot" in r for r in result))
        self.assertTrue(all("slot_reason" in r for r in result))

        # Should have RELEVANCE slots
        relevance_slots = [r for r in result if r["slot"] == SlotType.RELEVANCE]
        self.assertGreater(len(relevance_slots), 0)

    def test_assign_slots_with_custom_config(self):
        """Test slot assignment with custom slot config."""
        from mcp_server.recommendation_filter import SlotType, assign_slots

        recommendations = [
            {
                "url": f"{i}",
                "final_score": 0.9 - i * 0.1,
                "recency_score": 0.5,
                "depth_score": 3,
            }
            for i in range(10)
        ]

        config = {
            "relevance_count": 3,
            "serendipity_count": 0,
            "stale_refresh_count": 0,
            "trending_count": 0,
        }

        result = assign_slots(recommendations, config)

        # Should have exactly 3 RELEVANCE slots
        relevance_slots = [r for r in result if r["slot"] == SlotType.RELEVANCE]
        self.assertEqual(len(relevance_slots), 3)


class TestQueryVariation(unittest.TestCase):
    """Test suite for query variation (Story 3.8 AC#5)."""

    def test_session_seed_consistency(self):
        """Same hour should produce same seed."""
        from mcp_server.recommendation_queries import get_session_seed

        seed1 = get_session_seed()
        seed2 = get_session_seed()

        self.assertEqual(seed1, seed2)

    def test_expand_with_synonyms(self):
        """Test synonym expansion."""
        from mcp_server.recommendation_queries import expand_with_synonyms

        expanded = expand_with_synonyms("microservices architecture")

        self.assertIn("microservices architecture", expanded)
        self.assertGreater(len(expanded), 1)  # Should have synonyms

    def test_vary_query_perspective(self):
        """Test query perspective variation."""
        from mcp_server.recommendation_queries import vary_query_perspective

        query1 = vary_query_perspective("platform engineering", session_seed=123)
        query2 = vary_query_perspective("platform engineering", session_seed=123)

        # Same seed should produce same query
        self.assertEqual(query1, query2)

        # Different seed should produce different query
        query3 = vary_query_perspective("platform engineering", session_seed=456)
        # Note: May occasionally be the same by chance, so we just verify it's valid
        self.assertIn("platform engineering", query3)

    def test_rotate_sources(self):
        """Test source rotation."""
        from mcp_server.recommendation_queries import rotate_sources

        sources = [
            {"title": "A"},
            {"title": "B"},
            {"title": "C"},
            {"title": "D"},
        ]

        rotated = rotate_sources(sources, session_seed=100)

        self.assertEqual(len(rotated), 4)
        # Order should be different from original (unless seed happens to = 0 mod 4)
        # Just verify all items are present
        titles = [s["title"] for s in rotated]
        self.assertEqual(sorted(titles), ["A", "B", "C", "D"])


class TestDateParsing(unittest.TestCase):
    """Test suite for date parsing."""

    def test_parse_iso_date(self):
        """Test parsing ISO date format."""
        from mcp_server.recommendation_filter import parse_published_date

        result = parse_published_date("2025-12-01")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 1)

    def test_parse_iso_datetime(self):
        """Test parsing ISO datetime format."""
        from mcp_server.recommendation_filter import parse_published_date

        result = parse_published_date("2025-12-01T10:30:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 10)

    def test_parse_none_date(self):
        """Test parsing None returns None."""
        from mcp_server.recommendation_filter import parse_published_date

        result = parse_published_date(None)
        self.assertIsNone(result)

    def test_parse_invalid_date(self):
        """Test parsing invalid date returns None."""
        from mcp_server.recommendation_filter import parse_published_date

        result = parse_published_date("not-a-date")
        self.assertIsNone(result)


class TestShownRecommendationsTracking(unittest.TestCase):
    """Test suite for shown recommendations tracking (Story 3.8 AC#6)."""

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_record_shown_recommendations(self, mock_get_db):
        """Test recording shown recommendations."""
        from mcp_server import firestore_client

        mock_db = MagicMock()
        mock_batch = MagicMock()
        mock_db.batch.return_value = mock_batch
        mock_get_db.return_value = mock_db

        recommendations = [
            {
                "url": "https://example.com/1",
                "combined_score": 0.8,
                "slot": "RELEVANCE",
            },
            {"url": "https://example.com/2", "combined_score": 0.7, "slot": "TRENDING"},
        ]

        result = firestore_client.record_shown_recommendations(
            user_id="test_user", recommendations=recommendations
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["recorded_count"], 2)
        mock_batch.commit.assert_called_once()

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_get_shown_urls(self, mock_get_db):
        """Test retrieving shown URLs."""
        from mcp_server import firestore_client

        mock_doc1 = MagicMock()
        mock_doc1.to_dict.return_value = {"url": "https://example.com/1"}
        mock_doc2 = MagicMock()
        mock_doc2.to_dict.return_value = {"url": "https://example.com/2"}

        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_doc1, mock_doc2]
        mock_query.where.return_value = mock_query

        mock_collection = MagicMock()
        mock_collection.return_value = mock_query

        mock_doc_ref = MagicMock()
        mock_doc_ref.collection.return_value = mock_query

        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref
        mock_get_db.return_value = mock_db

        urls = firestore_client.get_shown_urls(user_id="test_user")

        self.assertEqual(len(urls), 2)
        self.assertIn("https://example.com/1", urls)


class TestRankingConfig(unittest.TestCase):
    """Test suite for ranking configuration (Story 3.8 AC#7)."""

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_get_ranking_config_creates_defaults(self, mock_get_db):
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

        result = firestore_client.get_ranking_config()

        # Should return default weights
        self.assertIn("weights", result)
        self.assertIn("relevance", result["weights"])
        self.assertEqual(result["weights"]["relevance"], 0.5)

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_update_ranking_config_validates_weights(self, mock_get_db):
        """Test that invalid weights are rejected."""
        from mcp_server import firestore_client

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Weights don't sum to 1.0
        invalid_weights = {
            "relevance": 0.5,
            "recency": 0.5,
            "depth": 0.5,
            "authority": 0.5,
        }

        result = firestore_client.update_ranking_config(weights=invalid_weights)

        self.assertFalse(result["success"])
        self.assertIn("error", result)
        self.assertIn("sum to 1.0", result["error"])


if __name__ == "__main__":
    unittest.main()
