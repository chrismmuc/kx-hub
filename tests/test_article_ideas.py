"""
Unit tests for Article Ideas functionality.

Story 6.1: Blog Idea Extraction from Knowledge Base

Tests:
- Source cluster discovery
- Takeaway extraction
- Thesis generation
- Timeliness assessment
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


class TestMediumScoreCalculation(unittest.TestCase):
    """Test medium suitability score calculation."""

    def test_linkedin_post_low_sources(self):
        """LinkedIn post scores high with single source."""
        scores = article_ideas.calculate_medium_scores(
            source_count=1,
            chunk_count=2,
            has_contradictions=False,
            takeaway_count=2,
        )
        self.assertIn("linkedin_post", scores)
        self.assertGreater(scores["linkedin_post"], 0.5)

    def test_linkedin_post_low_with_many_sources(self):
        """LinkedIn post scores lower with many sources."""
        scores = article_ideas.calculate_medium_scores(
            source_count=4,
            chunk_count=15,
            has_contradictions=False,
            takeaway_count=8,
        )
        self.assertLess(scores["linkedin_post"], 0.5)

    def test_blog_high_sources(self):
        """Blog scores high with many sources and chunks."""
        scores = article_ideas.calculate_medium_scores(
            source_count=4,
            chunk_count=15,
            has_contradictions=False,
            takeaway_count=6,
        )
        self.assertIn("blog", scores)
        self.assertGreater(scores["blog"], 0.7)

    def test_substack_contradiction_bonus(self):
        """Substack gets bonus for contradictions."""
        scores_no_contradiction = article_ideas.calculate_medium_scores(
            source_count=2, chunk_count=5, has_contradictions=False, takeaway_count=3
        )
        scores_with_contradiction = article_ideas.calculate_medium_scores(
            source_count=2, chunk_count=5, has_contradictions=True, takeaway_count=3
        )
        self.assertGreater(
            scores_with_contradiction["substack"], scores_no_contradiction["substack"]
        )

    def test_twitter_thread_high_takeaways(self):
        """Twitter thread scores high with many takeaways."""
        scores = article_ideas.calculate_medium_scores(
            source_count=2, chunk_count=5, has_contradictions=False, takeaway_count=7
        )
        self.assertGreater(scores["twitter_thread"], 0.9)

    def test_all_mediums_present(self):
        """All medium types are present in output."""
        scores = article_ideas.calculate_medium_scores(
            source_count=2, chunk_count=5, has_contradictions=False, takeaway_count=4
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

    def test_scores_are_rounded(self):
        """Scores are rounded to 2 decimal places."""
        scores = article_ideas.calculate_medium_scores(
            source_count=3, chunk_count=7, has_contradictions=False, takeaway_count=5
        )
        for score in scores.values():
            self.assertEqual(score, round(score, 2))


class TestStrengthCalculation(unittest.TestCase):
    """Test idea strength calculation."""

    def test_strength_with_multiple_sources(self):
        """Multiple sources increase strength."""
        strength = article_ideas._calculate_strength(
            source_count=3, chunk_count=10, takeaway_count=5, has_contradictions=False
        )
        self.assertGreater(strength, 0.5)

    def test_strength_with_single_source(self):
        """Single source has lower strength."""
        strength = article_ideas._calculate_strength(
            source_count=1, chunk_count=3, takeaway_count=2, has_contradictions=False
        )
        self.assertLess(strength, 0.5)

    def test_strength_capped_at_one(self):
        """Strength is capped at 1.0."""
        strength = article_ideas._calculate_strength(
            source_count=10, chunk_count=50, takeaway_count=20, has_contradictions=True
        )
        self.assertLessEqual(strength, 1.0)

    def test_contradiction_bonus(self):
        """Contradictions add to strength."""
        strength_no = article_ideas._calculate_strength(
            source_count=2, chunk_count=5, takeaway_count=3, has_contradictions=False
        )
        strength_yes = article_ideas._calculate_strength(
            source_count=2, chunk_count=5, takeaway_count=3, has_contradictions=True
        )
        self.assertGreater(strength_yes, strength_no)


class TestTitleSimilarity(unittest.TestCase):
    """Test title similarity detection."""

    def test_exact_match(self):
        """Exact match is detected."""
        self.assertTrue(article_ideas._titles_similar("Deep Work", "Deep Work"))

    def test_case_insensitive(self):
        """Case insensitive matching."""
        self.assertTrue(article_ideas._titles_similar("Deep Work", "deep work"))

    def test_one_contains_other(self):
        """Substring matching."""
        self.assertTrue(
            article_ideas._titles_similar("Deep Work", "Deep Work for Developers")
        )

    def test_word_overlap(self):
        """High word overlap is detected."""
        self.assertTrue(
            article_ideas._titles_similar("Deep Work and Focus", "Focus and Deep Work")
        )

    def test_different_titles(self):
        """Different titles are not similar."""
        self.assertFalse(article_ideas._titles_similar("Deep Work", "Atomic Habits"))


class TestExtractTopTakeaways(unittest.TestCase):
    """Test takeaway extraction from sources."""

    @patch("mcp_server.article_ideas.firestore_client")
    def test_extract_takeaways_from_sources(self, mock_firestore):
        """Takeaways are extracted from knowledge cards."""
        mock_firestore.get_source_by_id.return_value = {
            "title": "Deep Work",
            "author": "Cal Newport",
        }
        mock_firestore.get_chunks_by_source_id.return_value = [
            {
                "chunk_id": "chunk-1",
                "knowledge_card": {
                    "takeaways": [
                        "Focus is essential for deep work",
                        "Shallow work should be minimized",
                    ]
                },
            },
            {
                "chunk_id": "chunk-2",
                "knowledge_card": {
                    "takeaways": ["Rituals help establish deep work habits"]
                },
            },
        ]

        takeaways = article_ideas.extract_top_takeaways(
            source_ids=["source-1"], max_per_source=3
        )

        self.assertEqual(len(takeaways), 3)
        self.assertEqual(takeaways[0]["source"], "Deep Work")
        self.assertEqual(takeaways[0]["author"], "Cal Newport")

    @patch("mcp_server.article_ideas.firestore_client")
    def test_skip_short_takeaways(self, mock_firestore):
        """Short takeaways are filtered out."""
        mock_firestore.get_source_by_id.return_value = {
            "title": "Test",
            "author": "Author",
        }
        mock_firestore.get_chunks_by_source_id.return_value = [
            {
                "chunk_id": "chunk-1",
                "knowledge_card": {
                    "takeaways": [
                        "Short",  # Too short (< 20 chars)
                        "This is a longer takeaway that should be included",
                    ]
                },
            }
        ]

        takeaways = article_ideas.extract_top_takeaways(
            source_ids=["source-1"], max_per_source=5
        )

        self.assertEqual(len(takeaways), 1)
        self.assertIn("longer takeaway", takeaways[0]["quote"])


class TestAssessTimeliness(unittest.TestCase):
    """Test timeliness assessment."""

    @patch("mcp_server.article_ideas.firestore_client")
    def test_recent_sources_high_timeliness(self, mock_firestore):
        """Recent sources get high timeliness."""
        recent_time = datetime.utcnow() - timedelta(days=3)
        mock_timestamp = MagicMock()
        mock_timestamp.timestamp.return_value = recent_time.timestamp()

        mock_firestore.get_source_by_id.return_value = {"updated_at": mock_timestamp}

        result = article_ideas.assess_timeliness(["source-1"])

        self.assertIn("Woche", result["recency"])
        self.assertEqual(result["recent_source_count"], 1)

    @patch("mcp_server.article_ideas.firestore_client")
    def test_old_sources_low_timeliness(self, mock_firestore):
        """Old sources get lower timeliness."""
        old_time = datetime.utcnow() - timedelta(days=60)
        mock_timestamp = MagicMock()
        mock_timestamp.timestamp.return_value = old_time.timestamp()

        mock_firestore.get_source_by_id.return_value = {"updated_at": mock_timestamp}

        result = article_ideas.assess_timeliness(["source-1"])

        self.assertEqual(result["recent_source_count"], 0)
        self.assertGreaterEqual(result["oldest_days_ago"], 60)


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
            "thesis": "This is the thesis",
            "unique_angle": "Why this is unique",
            "sources": ["source-1"],
            "strength": 0.8,
            "medium_scores": {"blog": 0.9},
        }

        idea_id = article_ideas.save_article_idea(idea)

        self.assertIsNotNone(idea_id)
        self.assertTrue(idea_id.startswith("idea-"))
        mock_db.collection.assert_called_with("article_ideas")
        mock_doc.set.assert_called_once()

    @patch("mcp_server.article_ideas.firestore_client.get_firestore_client")
    def test_get_article_ideas(self, mock_get_client):
        """Getting ideas queries Firestore correctly."""
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
        mock_doc.to_dict.return_value = {
            "idea_id": "idea-1",
            "title": "Test Idea",
            "strength": 0.8,
        }
        mock_query.stream.return_value = [mock_doc]

        ideas = article_ideas.get_article_ideas(limit=10)

        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["idea_id"], "idea-1")


class TestThesisGeneration(unittest.TestCase):
    """Test thesis and angle generation."""

    @patch("mcp_server.article_ideas.get_client")
    def test_generate_thesis_and_angle(self, mock_get_client):
        """Thesis generation calls LLM correctly."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.generate.return_value = MagicMock(
            text='{"title": "Test Title", "thesis": "Test thesis", "unique_angle": "Test angle"}'
        )

        takeaways = [
            {"quote": "Takeaway 1", "author": "Author 1", "source": "Source 1"},
            {"quote": "Takeaway 2", "author": "Author 2", "source": "Source 2"},
        ]

        result = article_ideas.generate_thesis_and_angle(takeaways)

        self.assertEqual(result["title"], "Test Title")
        self.assertEqual(result["thesis"], "Test thesis")
        self.assertEqual(result["unique_angle"], "Test angle")
        mock_get_client.assert_called_with(model="gemini-3-pro-preview")

    @patch("mcp_server.article_ideas.get_client")
    def test_generate_thesis_handles_markdown(self, mock_get_client):
        """Thesis generation handles markdown code blocks."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.generate.return_value = MagicMock(
            text='```json\n{"title": "Test", "thesis": "Thesis", "unique_angle": "Angle"}\n```'
        )

        takeaways = [{"quote": "Test", "author": "A", "source": "S"}]
        result = article_ideas.generate_thesis_and_angle(takeaways)

        self.assertEqual(result["title"], "Test")

    def test_generate_thesis_empty_takeaways(self):
        """Empty takeaways returns empty result."""
        result = article_ideas.generate_thesis_and_angle([])

        self.assertEqual(result["title"], "")
        self.assertEqual(result["thesis"], "")
        self.assertEqual(result["unique_angle"], "")


class TestGenerateArticleIdea(unittest.TestCase):
    """Test complete article idea generation."""

    @patch("mcp_server.article_ideas.firestore_client")
    @patch("mcp_server.article_ideas.get_client")
    def test_generate_article_idea_full(self, mock_get_client, mock_firestore):
        """Full idea generation flow."""
        # Mock LLM
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.generate.return_value = MagicMock(
            text='{"title": "Deep Work for Developers", "thesis": "Focus matters", "unique_angle": "Unique view"}'
        )

        # Mock Firestore
        mock_firestore.get_source_by_id.return_value = {
            "title": "Deep Work",
            "author": "Cal Newport",
        }
        mock_firestore.get_chunks_by_source_id.return_value = [
            {
                "chunk_id": "chunk-1",
                "knowledge_card": {
                    "takeaways": ["This is a long enough takeaway to be included"]
                },
            }
        ]
        mock_firestore.get_source_relationships.return_value = []

        recent_time = datetime.utcnow() - timedelta(days=5)
        mock_timestamp = MagicMock()
        mock_timestamp.timestamp.return_value = recent_time.timestamp()
        mock_firestore.get_source_by_id.return_value["updated_at"] = mock_timestamp

        result = article_ideas.generate_article_idea(["source-1"])

        self.assertEqual(result["title"], "Deep Work for Developers")
        self.assertEqual(result["thesis"], "Focus matters")
        self.assertIn("medium_scores", result)
        self.assertIn("timeliness", result)
        self.assertIn("key_highlights", result)

    @patch("mcp_server.article_ideas.firestore_client")
    def test_generate_article_idea_no_takeaways(self, mock_firestore):
        """Returns error if no takeaways found."""
        mock_firestore.get_source_by_id.return_value = {
            "title": "Test",
            "author": "Author",
        }
        mock_firestore.get_chunks_by_source_id.return_value = []

        result = article_ideas.generate_article_idea(["source-1"])

        self.assertIn("error", result)


class TestMCPToolHandlers(unittest.TestCase):
    """Test MCP tool handler functions."""

    def test_suggest_article_ideas_auto(self):
        """suggest_article_ideas auto-generation mode."""
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

    def test_suggest_article_ideas_list_existing(self):
        """suggest_article_ideas list_existing mode."""
        mock_module = MagicMock()
        mock_module.get_article_ideas.return_value = [
            {
                "idea_id": "idea-1",
                "title": "Test Idea",
                "thesis": "Test thesis",
                "suggested_at": "2026-01-07T10:00:00Z",
                "strength": 0.8,
                "sources": ["source-1"],
                "medium_scores": {"blog": 0.9, "linkedin_post": 0.5},
            }
        ]

        with patch.dict("sys.modules", {"article_ideas": mock_module}):
            from mcp_server import tools

            result = tools.suggest_article_ideas(list_existing=True, limit=10)

            self.assertEqual(result["mode"], "list")
            self.assertEqual(result["idea_count"], 1)
            self.assertEqual(result["ideas"][0]["idea_id"], "idea-1")
            self.assertIn("top_mediums", result["ideas"][0])


class TestSourceClusterDiscovery(unittest.TestCase):
    """Test source cluster discovery."""

    @patch("mcp_server.article_ideas.firestore_client")
    def test_find_source_clusters(self, mock_firestore):
        """Find clusters with relationships."""
        mock_firestore.list_sources.return_value = [
            {"source_id": "source-1", "title": "Deep Work", "author": "Cal Newport"},
            {"source_id": "source-2", "title": "Flow", "author": "Mihaly"},
        ]

        # Source 1 has 2 relationships
        mock_firestore.get_source_relationships.side_effect = [
            [
                {"target_source_id": "source-2", "relationship_types": {"extends": 2}},
                {"target_source_id": "source-3", "relationship_types": {"relates": 1}},
            ],
            [],  # Source 2 has no relationships
        ]

        mock_firestore.get_source_by_id.return_value = {}

        clusters = article_ideas.find_source_clusters(min_relationships=2)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["primary_source"]["source_id"], "source-1")
        self.assertEqual(clusters[0]["relationship_count"], 2)

    @patch("mcp_server.article_ideas.firestore_client")
    def test_find_source_clusters_empty(self, mock_firestore):
        """Returns empty when no clusters found."""
        mock_firestore.list_sources.return_value = []

        clusters = article_ideas.find_source_clusters()

        self.assertEqual(clusters, [])


class TestSuggestIdeasFromSources(unittest.TestCase):
    """Test auto-suggestion from sources."""

    @patch("mcp_server.article_ideas.save_article_idea")
    @patch("mcp_server.article_ideas.generate_article_idea")
    @patch("mcp_server.article_ideas.find_source_clusters")
    def test_suggest_ideas_generates_from_clusters(
        self, mock_find_clusters, mock_generate, mock_save
    ):
        """Generates ideas from found clusters."""
        mock_find_clusters.return_value = [
            {
                "primary_source": {"source_id": "source-1"},
                "related_sources": [{"target_source_id": "source-2"}],
            }
        ]
        mock_generate.return_value = {
            "title": "Test Idea",
            "thesis": "Test thesis",
            "unique_angle": "Test angle",
            "medium_scores": {"blog": 0.9},
        }
        mock_save.return_value = "idea-123"

        ideas = article_ideas.suggest_ideas_from_sources(limit=5, save=True)

        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["title"], "Test Idea")
        self.assertEqual(ideas[0]["idea_id"], "idea-123")

    @patch("mcp_server.article_ideas.find_source_clusters")
    def test_suggest_ideas_empty_clusters(self, mock_find_clusters):
        """Returns empty when no clusters found."""
        mock_find_clusters.return_value = []

        ideas = article_ideas.suggest_ideas_from_sources()

        self.assertEqual(ideas, [])


class TestSuggestIdeaForTopic(unittest.TestCase):
    """Test topic-specific idea suggestion."""

    @patch("mcp_server.article_ideas.save_article_idea")
    @patch("mcp_server.article_ideas.generate_article_idea")
    @patch("mcp_server.article_ideas.get_article_ideas")
    @patch("mcp_server.article_ideas.firestore_client")
    def test_suggest_idea_for_topic_with_sources(
        self, mock_firestore, mock_get_ideas, mock_generate, mock_save
    ):
        """Suggests idea for topic with provided sources."""
        mock_get_ideas.return_value = []
        mock_generate.return_value = {
            "title": "Deep Work for Developers",
            "thesis": "Focus matters",
        }
        mock_save.return_value = "idea-123"

        result = article_ideas.suggest_idea_for_topic(
            topic="Deep Work",
            source_ids=["source-1", "source-2"],
            save=True,
        )

        self.assertIn("idea", result)
        self.assertEqual(result["idea"]["title"], "Deep Work for Developers")

    @patch("mcp_server.article_ideas.get_article_ideas")
    def test_suggest_idea_detects_duplicate(self, mock_get_ideas):
        """Detects duplicate ideas by title similarity."""
        mock_get_ideas.return_value = [
            {"idea_id": "existing-123", "title": "Deep Work for Developers"}
        ]

        result = article_ideas.suggest_idea_for_topic(
            topic="deep work for developers",
            source_ids=["source-1"],
        )

        self.assertTrue(result.get("is_duplicate"))
        self.assertEqual(result["duplicate_of"], "existing-123")


if __name__ == "__main__":
    unittest.main()
