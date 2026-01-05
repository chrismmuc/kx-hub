"""
Unit tests for Article Ideas functionality.

Story 6.1: Blog Idea Extraction from Knowledge Base

Tests:
- Source scoring algorithm
- Medium score calculation
- Idea generation and deduplication
- MCP tool handlers
"""

import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/mcp_server"))

from mcp_server import article_ideas


class TestSourceScoring(unittest.TestCase):
    """Test source scoring algorithm."""

    def test_calculate_source_score_high_chunks(self):
        """Source with many chunks gets high score."""
        source = {"chunk_count": 15, "tags": ["productivity", "pkm", "tools"]}
        score = article_ideas.calculate_source_score(source)
        self.assertGreaterEqual(score, 0.35)  # 0.3 for chunks + 0.1 for tags

    def test_calculate_source_score_low_chunks(self):
        """Source with few chunks gets lower score."""
        source = {"chunk_count": 2, "tags": []}
        score = article_ideas.calculate_source_score(source)
        self.assertLessEqual(score, 0.1)

    def test_calculate_source_score_empty(self):
        """Empty source gets zero score."""
        source = {}
        score = article_ideas.calculate_source_score(source)
        self.assertEqual(score, 0.0)


class TestChunkScoring(unittest.TestCase):
    """Test chunk scoring algorithm."""

    def test_calculate_chunk_score_many_chunks(self):
        """Many chunks with takeaways gets high score."""
        chunks = [
            {"knowledge_card": {"takeaways": ["takeaway 1", "takeaway 2"]}}
            for _ in range(10)
        ]
        score = article_ideas.calculate_chunk_score(chunks)
        self.assertGreaterEqual(score, 0.85)

    def test_calculate_chunk_score_few_chunks(self):
        """Few chunks gets moderate score."""
        chunks = [{"knowledge_card": {}} for _ in range(2)]
        score = article_ideas.calculate_chunk_score(chunks)
        self.assertLessEqual(score, 0.5)

    def test_calculate_chunk_score_empty(self):
        """Empty chunks list returns zero."""
        score = article_ideas.calculate_chunk_score([])
        self.assertEqual(score, 0.0)


class TestRecencyScoring(unittest.TestCase):
    """Test recency score calculation."""

    def test_recency_score_recent(self):
        """Recent date gets high score."""
        now = datetime.now()
        score = article_ideas.calculate_recency_score(now)
        self.assertGreaterEqual(score, 0.95)

    def test_recency_score_old(self):
        """Old date gets lower score."""
        old_date = datetime.now() - timedelta(days=90)
        score = article_ideas.calculate_recency_score(old_date)
        self.assertLess(score, 0.5)

    def test_recency_score_none(self):
        """None date returns default score."""
        score = article_ideas.calculate_recency_score(None)
        self.assertEqual(score, 0.5)

    def test_recency_score_string_date(self):
        """String date is parsed correctly."""
        date_str = datetime.now().isoformat()
        score = article_ideas.calculate_recency_score(date_str)
        self.assertGreaterEqual(score, 0.95)


class TestMediumScoreCalculation(unittest.TestCase):
    """Test medium suitability score calculation."""

    def test_linkedin_post_low_sources(self):
        """LinkedIn post scores high with few sources."""
        scores = article_ideas.calculate_medium_scores(
            source_count=1,
            chunk_count=2,
            tag_count=1,
            has_contradictions=False,
        )
        self.assertIn("linkedin_post", scores)
        self.assertGreater(scores["linkedin_post"], 0.5)

    def test_blog_high_sources(self):
        """Blog scores high with many sources and chunks."""
        scores = article_ideas.calculate_medium_scores(
            source_count=5,
            chunk_count=20,
            tag_count=4,
            has_contradictions=False,
        )
        self.assertIn("blog", scores)
        self.assertGreater(scores["blog"], 0.7)

    def test_substack_contradiction_bonus(self):
        """Substack gets bonus for contradictions."""
        # Use lower base scores so bonus is visible (not capped at 1.0)
        scores_no_contradiction = article_ideas.calculate_medium_scores(
            source_count=2, chunk_count=5, tag_count=1, has_contradictions=False
        )
        scores_with_contradiction = article_ideas.calculate_medium_scores(
            source_count=2, chunk_count=5, tag_count=1, has_contradictions=True
        )
        self.assertGreaterEqual(
            scores_with_contradiction["substack"], scores_no_contradiction["substack"]
        )

    def test_all_mediums_present(self):
        """All medium types are present in output."""
        scores = article_ideas.calculate_medium_scores(
            source_count=2, chunk_count=5, tag_count=2, has_contradictions=False
        )
        expected_mediums = [
            "linkedin_post",
            "linkedin_article",
            "blog",
            "newsletter",
            "twitter_thread",
            "substack",
        ]
        for medium in expected_mediums:
            self.assertIn(medium, scores)
            self.assertGreaterEqual(scores[medium], 0.0)
            self.assertLessEqual(scores[medium], 1.0)


class TestIdeaGeneration(unittest.TestCase):
    """Test idea generation helpers."""

    def test_generate_idea_id_deterministic(self):
        """Same inputs produce same ID."""
        id1 = article_ideas.generate_idea_id("Test Title", ["source-a", "source-b"])
        id2 = article_ideas.generate_idea_id("Test Title", ["source-a", "source-b"])
        self.assertEqual(id1, id2)

    def test_generate_idea_id_different_for_different_inputs(self):
        """Different inputs produce different IDs."""
        id1 = article_ideas.generate_idea_id("Title A", ["source-a"])
        id2 = article_ideas.generate_idea_id("Title B", ["source-b"])
        self.assertNotEqual(id1, id2)

    def test_determine_idea_type_deep_dive(self):
        """Single source results in deep_dive type."""
        idea_type = article_ideas.determine_idea_type(
            source_count=1, has_contradictions=False, relationship_types=[]
        )
        self.assertEqual(idea_type, "deep_dive")

    def test_determine_idea_type_comparison(self):
        """Two sources result in comparison type."""
        idea_type = article_ideas.determine_idea_type(
            source_count=2, has_contradictions=False, relationship_types=[]
        )
        self.assertEqual(idea_type, "comparison")

    def test_determine_idea_type_contradiction(self):
        """Contradictions override other types."""
        idea_type = article_ideas.determine_idea_type(
            source_count=2, has_contradictions=True, relationship_types=[]
        )
        self.assertEqual(idea_type, "contradiction")

    def test_determine_idea_type_synthesis(self):
        """Related sources result in synthesis type."""
        idea_type = article_ideas.determine_idea_type(
            source_count=3, has_contradictions=False, relationship_types=["extends"]
        )
        self.assertEqual(idea_type, "synthesis")

    def test_extract_themes_from_sources(self):
        """Common themes are extracted from sources."""
        sources = [
            {"tags": ["productivity", "pkm", "tools"]},
            {"tags": ["productivity", "automation", "pkm"]},
        ]
        themes = article_ideas.extract_themes_from_sources(sources)
        self.assertIn("productivity", themes)
        self.assertIn("pkm", themes)

    def test_generate_idea_title_deep_dive(self):
        """Deep dive generates appropriate title."""
        sources = [{"title": "Deep Work", "author": "Cal Newport"}]
        title = article_ideas.generate_idea_title("deep_dive", sources, [])
        self.assertIn("Deep Work", title)

    def test_generate_idea_title_comparison(self):
        """Comparison generates vs title."""
        sources = [
            {"title": "Deep Work", "author": "Cal Newport"},
            {"title": "Flow", "author": "Mihaly"},
        ]
        title = article_ideas.generate_idea_title("comparison", sources, [])
        self.assertIn("vs", title)


class TestIdeaScoring(unittest.TestCase):
    """Test idea scoring logic."""

    @patch("mcp_server.article_ideas.firestore_client")
    def test_score_idea_basic(self, mock_firestore):
        """Basic idea scoring works correctly."""
        mock_firestore.find_contradictions.return_value = []

        sources = [{"source_id": "test", "chunk_count": 5, "tags": ["productivity"]}]
        chunks = [{"knowledge_card": {"takeaways": ["t1"]}} for _ in range(5)]
        relationships = []

        result = article_ideas.score_idea(sources, chunks, relationships)

        self.assertIn("strength", result)
        self.assertIn("reasoning_details", result)
        self.assertGreater(result["strength"], 0.0)
        self.assertLessEqual(result["strength"], 1.0)

        details = result["reasoning_details"]
        self.assertIn("source_score", details)
        self.assertIn("chunk_score", details)
        self.assertIn("relationship_score", details)
        self.assertIn("recency_score", details)
        self.assertIn("contradiction_bonus", details)


class TestFirestoreOperations(unittest.TestCase):
    """Test Firestore operations for article ideas."""

    @patch("mcp_server.article_ideas.firestore_client.get_firestore_client")
    def test_save_article_idea(self, mock_get_client):
        """Saving an idea creates document in Firestore."""
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_doc = MagicMock()
        mock_collection.document.return_value = mock_doc

        idea = {
            "title": "Test Idea",
            "source_ids": ["source-1"],
            "strength": 0.8,
            "medium_scores": {"blog": 0.9},
        }

        idea_id = article_ideas.save_article_idea(idea)

        self.assertIsNotNone(idea_id)
        mock_db.collection.assert_called_with("article_ideas")
        mock_doc.set.assert_called_once()

    @patch("mcp_server.article_ideas.firestore_client.get_firestore_client")
    def test_list_article_ideas(self, mock_get_client):
        """Listing ideas queries Firestore correctly."""
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection

        # Mock query chain
        mock_query = MagicMock()
        mock_collection.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query

        # Mock stream results
        mock_doc = MagicMock()
        mock_doc.id = "idea-1"
        mock_doc.to_dict.return_value = {
            "title": "Test Idea",
            "status": "suggested",
            "strength": 0.8,
        }
        mock_query.stream.return_value = [mock_doc]

        ideas = article_ideas.list_article_ideas(limit=10)

        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["idea_id"], "idea-1")

    @patch("mcp_server.article_ideas.firestore_client.get_firestore_client")
    def test_update_idea_status(self, mock_get_client):
        """Updating idea status works correctly."""
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_doc = MagicMock()
        mock_collection.document.return_value = mock_doc

        success = article_ideas.update_idea_status("idea-1", "accepted")

        self.assertTrue(success)
        mock_doc.update.assert_called_once()
        call_args = mock_doc.update.call_args[0][0]
        self.assertEqual(call_args["status"], "accepted")


class TestDeduplication(unittest.TestCase):
    """Test idea deduplication logic."""

    @patch("mcp_server.article_ideas.firestore_client.get_firestore_client")
    def test_check_duplicate_by_sources(self, mock_get_client):
        """Duplicate detected by same source_ids."""
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection

        # Mock existing idea with same sources
        mock_doc = MagicMock()
        mock_doc.id = "existing-idea"
        mock_doc.to_dict.return_value = {
            "title": "Existing Idea",
            "source_ids": ["source-a", "source-b"],
        }
        mock_collection.limit.return_value.stream.return_value = [mock_doc]

        result = article_ideas.check_idea_duplicate(
            title="New Idea", source_ids=["source-a", "source-b"]
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["idea_id"], "existing-idea")

    @patch("mcp_server.article_ideas.firestore_client.get_firestore_client")
    def test_check_duplicate_by_title(self, mock_get_client):
        """Duplicate detected by similar title."""
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection

        # Mock existing idea with similar title
        mock_doc = MagicMock()
        mock_doc.id = "existing-idea"
        mock_doc.to_dict.return_value = {
            "title": "Deep Work for Developers",
            "source_ids": ["source-x"],
        }
        mock_collection.limit.return_value.stream.return_value = [mock_doc]

        result = article_ideas.check_idea_duplicate(
            title="deep work for developers", source_ids=["source-y"]
        )

        self.assertIsNotNone(result)

    @patch("mcp_server.article_ideas.firestore_client.get_firestore_client")
    def test_no_duplicate_found(self, mock_get_client):
        """No duplicate when ideas are different."""
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection

        # Mock empty results
        mock_collection.limit.return_value.stream.return_value = []

        result = article_ideas.check_idea_duplicate(
            title="Unique New Idea", source_ids=["unique-source"]
        )

        self.assertIsNone(result)


class TestMCPToolHandlers(unittest.TestCase):
    """Test MCP tool handler functions.

    Note: These tests verify the tool handlers work by mocking
    the article_ideas module that gets imported inside each function.
    """

    def test_suggest_article_ideas_auto(self):
        """suggest_article_ideas auto-generation mode."""
        # Create a mock module
        mock_module = MagicMock()
        mock_module.suggest_ideas_from_sources.return_value = [
            {
                "idea_id": "idea-1",
                "title": "Test Idea",
                "strength": 0.8,
                "medium_scores": {"blog": 0.9},
            }
        ]

        with patch.dict("sys.modules", {"article_ideas": mock_module}):
            from mcp_server import tools

            result = tools.suggest_article_ideas(limit=5, save=True)

            self.assertEqual(result["mode"], "auto_discovery")
            self.assertEqual(result["idea_count"], 1)

    def test_suggest_article_ideas_topic(self):
        """suggest_article_ideas topic evaluation mode."""
        mock_module = MagicMock()
        mock_module.suggest_idea_for_topic.return_value = {
            "idea": {
                "idea_id": "idea-1",
                "title": "Deep Work for Developers",
                "strength": 0.85,
            },
            "is_duplicate": False,
        }

        with patch.dict("sys.modules", {"article_ideas": mock_module}):
            from mcp_server import tools

            result = tools.suggest_article_ideas(topic="Deep Work for Developers")

            self.assertEqual(result["mode"], "topic_evaluation")
            self.assertEqual(result["topic"], "Deep Work for Developers")

    def test_list_ideas_handler(self):
        """list_ideas MCP handler works correctly."""
        mock_module = MagicMock()
        mock_module.list_article_ideas.return_value = [
            {
                "idea_id": "idea-1",
                "title": "Test Idea",
                "suggested_at": datetime.now(),
                "strength": 0.8,
                "status": "suggested",
                "source_ids": ["source-1"],
                "medium_scores": {"blog": 0.9, "linkedin_post": 0.5},
            }
        ]

        with patch.dict("sys.modules", {"article_ideas": mock_module}):
            from mcp_server import tools

            result = tools.list_ideas(status="suggested", limit=10)

            self.assertEqual(result["idea_count"], 1)
            self.assertEqual(result["ideas"][0]["idea_id"], "idea-1")
            self.assertIn("top_mediums", result["ideas"][0])

    def test_accept_idea_handler(self):
        """accept_idea MCP handler works correctly."""
        mock_module = MagicMock()
        mock_module.update_idea_status.return_value = True

        with patch.dict("sys.modules", {"article_ideas": mock_module}):
            from mcp_server import tools

            result = tools.accept_idea(idea_id="idea-1")

            self.assertTrue(result["success"])
            self.assertEqual(result["status"], "accepted")

    def test_reject_idea_handler(self):
        """reject_idea MCP handler works correctly."""
        mock_module = MagicMock()
        mock_module.update_idea_status.return_value = True

        with patch.dict("sys.modules", {"article_ideas": mock_module}):
            from mcp_server import tools

            result = tools.reject_idea(idea_id="idea-1", reason="Not relevant")

            self.assertTrue(result["success"])
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(result["reason"], "Not relevant")


class TestWebEnrichment(unittest.TestCase):
    """Test web enrichment helper functions."""

    def test_generate_suggested_angle_low_competition(self):
        """Suggested angle for low competition."""
        idea = {"type": "deep_dive", "source_ids": ["a"]}
        angle = article_ideas._generate_suggested_angle(idea, [], "low")
        self.assertIn("Low competition", angle)

    def test_generate_suggested_angle_high_competition(self):
        """Suggested angle for high competition."""
        idea = {"type": "deep_dive", "source_ids": ["a"]}
        angle = article_ideas._generate_suggested_angle(idea, [], "high")
        self.assertIn("High competition", angle)

    def test_generate_suggested_angle_contradiction(self):
        """Suggested angle for contradiction type."""
        idea = {"type": "contradiction", "source_ids": ["a", "b"]}
        angle = article_ideas._generate_suggested_angle(idea, [], "high")
        self.assertIn("controversy", angle)

    def test_generate_suggested_angle_synthesis(self):
        """Suggested angle for synthesis with many sources."""
        idea = {"type": "synthesis", "source_ids": ["a", "b", "c", "d"]}
        angle = article_ideas._generate_suggested_angle(idea, [], "high")
        self.assertIn("synthesis", angle)

    def test_generate_suggested_angle_medium_comparison(self):
        """Suggested angle for comparison at medium competition."""
        idea = {"type": "comparison", "source_ids": ["a", "b"]}
        angle = article_ideas._generate_suggested_angle(idea, [], "medium")
        self.assertIn("Compare", angle)


if __name__ == "__main__":
    unittest.main()
