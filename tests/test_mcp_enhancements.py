"""
Unit tests for Story 2.6: MCP Server Enhancements - Knowledge Cards.

Tests knowledge card tools and enhanced existing tools.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
# Add mcp_server to path so firestore_client and embeddings can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/mcp_server"))

from mcp_server import tools


class TestKnowledgeCardTools(unittest.TestCase):
    """Test suite for knowledge card tools (AC #2)."""

    @patch("mcp_server.tools.firestore_client.get_chunk_by_id")
    def test_get_knowledge_card_success(self, mock_get_chunk):
        """Test get_knowledge_card returns summary and takeaways (AC #2)."""
        # Mock chunk with knowledge card
        mock_get_chunk.return_value = {
            "id": "test-chunk-1",
            "title": "Atomic Habits",
            "author": "James Clear",
            "source": "kindle",
            "knowledge_card": {
                "summary": "Small habits compound over time to create remarkable results.",
                "takeaways": [
                    "Focus on systems, not goals",
                    "Make habits obvious, attractive, easy, and satisfying",
                    "1% improvement daily leads to 37x improvement in a year",
                ],
            },
        }

        result = tools.get_knowledge_card("test-chunk-1")

        # Verify result structure
        self.assertEqual(result["chunk_id"], "test-chunk-1")
        self.assertEqual(result["title"], "Atomic Habits")
        self.assertIn("knowledge_card", result)
        self.assertIn("summary", result["knowledge_card"])
        self.assertIn("takeaways", result["knowledge_card"])
        self.assertEqual(len(result["knowledge_card"]["takeaways"]), 3)

    @patch("mcp_server.tools.firestore_client.get_chunk_by_id")
    def test_get_knowledge_card_missing(self, mock_get_chunk):
        """Test get_knowledge_card handles missing knowledge card (AC #8)."""
        # Mock chunk without knowledge card
        mock_get_chunk.return_value = {
            "id": "test-chunk-2",
            "title": "Test Book",
            "author": "Test Author",
            "source": "reader",
        }

        result = tools.get_knowledge_card("test-chunk-2")

        # Should return error when knowledge card is missing
        self.assertIn("error", result)
        self.assertIn("not available", result["error"])

    @patch("mcp_server.tools.firestore_client.get_chunk_by_id")
    def test_get_knowledge_card_chunk_not_found(self, mock_get_chunk):
        """Test get_knowledge_card handles non-existent chunk (AC #8)."""
        mock_get_chunk.return_value = None

        result = tools.get_knowledge_card("non-existent-chunk")

        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    @patch("mcp_server.tools.embeddings.generate_query_embedding")
    @patch("mcp_server.tools.firestore_client.find_nearest")
    def test_search_knowledge_cards_success(
        self, mock_find_nearest, mock_generate_embedding
    ):
        """Test search_knowledge_cards returns only summaries (AC #2)."""
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock results with knowledge cards
        mock_find_nearest.return_value = [
            {
                "id": "chunk-1",
                "title": "Book 1",
                "author": "Author 1",
                "source": "kindle",
                "knowledge_card": {
                    "summary": "Summary 1",
                    "takeaways": ["Takeaway A", "Takeaway B"],
                },
            },
            {
                "id": "chunk-2",
                "title": "Book 2",
                "author": "Author 2",
                "source": "reader",
                "knowledge_card": {"summary": "Summary 2", "takeaways": ["Takeaway C"]},
            },
        ]

        result = tools.search_knowledge_cards("productivity tips", limit=10)

        # Verify results contain only knowledge card data, not full content
        self.assertEqual(result["result_count"], 2)
        self.assertEqual(len(result["results"]), 2)

        # Verify first result has knowledge card
        first_result = result["results"][0]
        self.assertIn("knowledge_card", first_result)
        self.assertEqual(first_result["knowledge_card"]["summary"], "Summary 1")
        self.assertEqual(len(first_result["knowledge_card"]["takeaways"]), 2)

        # Verify no full content in results
        self.assertNotIn("full_content", first_result)
        self.assertNotIn("snippet", first_result)


class TestEnhancedSearchTools(unittest.TestCase):
    """Test suite for enhanced existing tools with knowledge cards (AC #1, #6)."""

    @patch("mcp_server.tools.embeddings.generate_query_embedding")
    @patch("mcp_server.tools.firestore_client.find_nearest")
    def test_search_semantic_includes_knowledge_card(
        self, mock_find_nearest, mock_generate_embedding
    ):
        """Test search_semantic includes knowledge_card field (AC #1)."""
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock search results
        mock_find_nearest.return_value = [
            {
                "id": "chunk-1",
                "title": "Test Book",
                "author": "Test Author",
                "source": "kindle",
                "tags": ["productivity"],
                "content": "Test content here.",
                "chunk_index": 0,
                "total_chunks": 1,
                "knowledge_card": {
                    "summary": "This is a test summary",
                    "takeaways": ["Takeaway 1", "Takeaway 2"],
                },
            }
        ]

        result = tools.search_semantic("productivity tips", limit=10)

        # Verify backward compatibility (AC #6)
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 1)

        first_result = result["results"][0]

        # Verify original fields still present
        self.assertIn("chunk_id", first_result)
        self.assertIn("title", first_result)
        self.assertIn("author", first_result)
        self.assertIn("snippet", first_result)
        self.assertIn("full_content", first_result)

        # Verify new fields added (AC #1)
        self.assertIn("knowledge_card", first_result)

        # Verify knowledge_card structure
        self.assertEqual(
            first_result["knowledge_card"]["summary"], "This is a test summary"
        )
        self.assertEqual(len(first_result["knowledge_card"]["takeaways"]), 2)

    @patch("mcp_server.tools.firestore_client.query_by_metadata")
    def test_search_by_metadata_includes_new_fields(self, mock_query):
        """Test search_by_metadata includes knowledge_card field (AC #1)."""
        mock_query.return_value = [
            {
                "id": "chunk-1",
                "title": "Test Book",
                "author": "Test Author",
                "source": "kindle",
                "tags": ["psychology"],
                "content": "Test content",
                "chunk_index": 0,
                "total_chunks": 1,
                "knowledge_card": {"summary": "Test summary", "takeaways": []},
            }
        ]

        result = tools.search_by_metadata(tags=["psychology"], limit=20)

        first_result = result["results"][0]
        self.assertIn("knowledge_card", first_result)

    @patch("mcp_server.tools.firestore_client.get_chunk_by_id")
    @patch("mcp_server.tools.firestore_client.find_nearest")
    def test_get_related_chunks_includes_new_fields(
        self, mock_find_nearest, mock_get_chunk
    ):
        """Test get_related_chunks includes knowledge_card field (AC #1)."""
        # Mock source chunk
        mock_get_chunk.return_value = {
            "id": "source-chunk",
            "title": "Source Book",
            "embedding": [0.1] * 768,
        }

        # Mock related chunks
        mock_find_nearest.return_value = [
            {
                "id": "source-chunk"  # Will be filtered out
            },
            {
                "id": "related-chunk-1",
                "title": "Related Book",
                "author": "Author",
                "source": "kindle",
                "content": "Related content",
                "chunk_index": 0,
                "total_chunks": 1,
                "knowledge_card": {
                    "summary": "Related summary",
                    "takeaways": ["Related takeaway"],
                },
            },
        ]

        result = tools.get_related_chunks("source-chunk", limit=5)

        self.assertEqual(len(result["results"]), 1)
        first_result = result["results"][0]

        self.assertIn("knowledge_card", first_result)


class TestEdgeCases(unittest.TestCase):
    """Test edge case handling (AC #8)."""

    @patch("mcp_server.tools.firestore_client.find_nearest")
    @patch("mcp_server.tools.embeddings.generate_query_embedding")
    def test_missing_knowledge_card_handled_gracefully(
        self, mock_generate_embedding, mock_find_nearest
    ):
        """Test that missing knowledge_card field doesn't break search (AC #8)."""
        mock_generate_embedding.return_value = [0.1] * 768

        mock_find_nearest.return_value = [
            {
                "id": "chunk-without-card",
                "title": "Old Chunk",
                "author": "Author",
                "source": "kindle",
                "tags": [],
                "content": "Content without knowledge card",
                "chunk_index": 0,
                "total_chunks": 1,
                # No knowledge_card field
            }
        ]

        result = tools.search_semantic("test query", limit=10)

        # Should not crash, should return None for knowledge_card
        first_result = result["results"][0]
        self.assertIsNone(first_result["knowledge_card"])


if __name__ == "__main__":
    unittest.main()
