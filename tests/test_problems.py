"""
Unit tests for Epic 10 Problems Tool.

Tests the Feynman-style problems functionality including:
- Creating problems with embeddings
- Listing active/archived problems
- Analyzing problems with evidence grouping
- Archiving problems

Mocks Firestore and Vertex AI to test tool logic without GCP dependencies.
"""

import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/mcp_server"))

from mcp_server import tools


class TestProblemsAdd(unittest.TestCase):
    """Test suite for problems(action='add')."""

    @patch("mcp_server.tools.firestore_client.create_problem")
    @patch("mcp_server.tools.embeddings.generate_query_embedding")
    def test_add_problem_success(self, mock_embedding, mock_create):
        """Test creating a problem successfully."""
        # Mock embedding generation
        mock_embedding.return_value = [0.1] * 768

        # Mock Firestore create
        mock_create.return_value = {
            "problem_id": "prob_abc123",
            "problem": "Why do feature flags fail?",
            "description": "Teams adopt them but still have issues",
            "status": "active",
            "created_at": "2026-01-10T10:00:00Z",
        }

        # Execute
        result = tools.problems(
            action="add",
            problem="Why do feature flags fail?",
            description="Teams adopt them but still have issues",
        )

        # Assertions
        self.assertEqual(result["problem_id"], "prob_abc123")
        self.assertEqual(result["problem"], "Why do feature flags fail?")
        self.assertEqual(result["status"], "active")

        # Verify embedding was generated from combined text
        mock_embedding.assert_called_once_with(
            "Why do feature flags fail? Teams adopt them but still have issues"
        )

        # Verify Firestore was called with embedding
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        self.assertEqual(call_args.kwargs["problem"], "Why do feature flags fail?")
        self.assertEqual(
            call_args.kwargs["description"], "Teams adopt them but still have issues"
        )
        self.assertEqual(len(call_args.kwargs["embedding"]), 768)

    @patch("mcp_server.tools.firestore_client.create_problem")
    @patch("mcp_server.tools.embeddings.generate_query_embedding")
    def test_add_problem_without_description(self, mock_embedding, mock_create):
        """Test creating a problem without description."""
        mock_embedding.return_value = [0.1] * 768
        mock_create.return_value = {
            "problem_id": "prob_xyz789",
            "problem": "How to scale teams?",
            "description": "",
            "status": "active",
            "created_at": "2026-01-10T10:00:00Z",
        }

        result = tools.problems(action="add", problem="How to scale teams?")

        # Should work without description
        self.assertNotIn("error", result)
        self.assertEqual(result["problem_id"], "prob_xyz789")

        # Embedding generated from problem only
        mock_embedding.assert_called_once_with("How to scale teams?")

    def test_add_problem_missing_problem_text(self):
        """Test that add fails without problem text."""
        result = tools.problems(action="add")

        self.assertIn("error", result)
        self.assertIn("required", result["error"].lower())

    @patch("mcp_server.tools.embeddings.generate_query_embedding")
    def test_add_problem_embedding_failure(self, mock_embedding):
        """Test handling of embedding generation failure."""
        mock_embedding.side_effect = Exception("Vertex AI error")

        result = tools.problems(
            action="add",
            problem="Test problem",
        )

        self.assertIn("error", result)
        self.assertIn("embedding", result["error"].lower())


class TestProblemsList(unittest.TestCase):
    """Test suite for problems(action='list')."""

    @patch("mcp_server.tools.firestore_client.list_problems")
    def test_list_problems_success(self, mock_list):
        """Test listing problems."""
        # Mock active and archived problems
        mock_list.side_effect = [
            # First call: active problems
            [
                {
                    "problem_id": "prob_001",
                    "problem": "Why do feature flags fail?",
                    "status": "active",
                    "evidence_count": 5,
                    "contradiction_count": 1,
                    "created_at": "2026-01-10T10:00:00Z",
                    "last_evidence_at": "2026-01-12T10:00:00Z",
                },
                {
                    "problem_id": "prob_002",
                    "problem": "How to scale teams?",
                    "status": "active",
                    "evidence_count": 3,
                    "contradiction_count": 0,
                    "created_at": "2026-01-11T10:00:00Z",
                    "last_evidence_at": None,
                },
            ],
            # Second call: archived problems
            [
                {
                    "problem_id": "prob_000",
                    "problem": "Old problem",
                    "status": "archived",
                    "evidence_count": 10,
                    "contradiction_count": 2,
                    "created_at": "2025-01-10T10:00:00Z",
                    "last_evidence_at": "2025-06-01T10:00:00Z",
                },
            ],
        ]

        result = tools.problems(action="list")

        # Assertions
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["active"], 2)
        self.assertEqual(result["archived"], 1)
        self.assertEqual(len(result["problems"]), 2)  # Only active shown
        self.assertEqual(result["problems"][0]["problem_id"], "prob_001")
        self.assertEqual(result["problems"][0]["evidence_count"], 5)

        # Verify both calls made
        self.assertEqual(mock_list.call_count, 2)

    @patch("mcp_server.tools.firestore_client.list_problems")
    def test_list_problems_empty(self, mock_list):
        """Test listing when no problems exist."""
        mock_list.return_value = []

        result = tools.problems(action="list")

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["active"], 0)
        self.assertEqual(result["problems"], [])


class TestProblemsAnalyze(unittest.TestCase):
    """Test suite for problems(action='analyze')."""

    @patch("mcp_server.tools.firestore_client.get_problem")
    def test_analyze_single_problem(self, mock_get):
        """Test analyzing a single problem."""
        mock_get.return_value = {
            "problem_id": "prob_001",
            "problem": "Why do feature flags fail?",
            "description": "Teams adopt them but still have issues",
            "evidence": [
                {
                    "chunk_id": "chunk_123",
                    "source_title": "Accelerate",
                    "quote": "Elite performers deploy 208x more frequently",
                    "similarity": 0.85,
                    "is_contradiction": False,
                    "relationship": {
                        "type": "extends",
                        "target_source": "Continuous Delivery",
                    },
                },
                {
                    "chunk_id": "chunk_456",
                    "source_title": "Move Fast and Break Things",
                    "quote": "Speed requires accepting some bugs",
                    "similarity": 0.78,
                    "is_contradiction": True,
                    "relationship": {
                        "type": "contradicts",
                        "target_source": "Accelerate",
                    },
                },
            ],
        }

        result = tools.problems(action="analyze", problem_id="prob_001")

        # Assertions
        self.assertEqual(result["problem_id"], "prob_001")
        self.assertEqual(result["problem"], "Why do feature flags fail?")

        # Evidence grouping
        self.assertEqual(len(result["evidence"]["supporting"]), 1)
        self.assertEqual(len(result["evidence"]["contradicting"]), 1)
        self.assertEqual(
            result["evidence"]["supporting"][0]["source_title"], "Accelerate"
        )
        self.assertEqual(
            result["evidence"]["contradicting"][0]["source_title"],
            "Move Fast and Break Things",
        )

        # Connections
        self.assertEqual(len(result["connections"]), 2)

        # Summary
        self.assertEqual(result["summary"]["evidence_count"], 2)
        self.assertEqual(result["summary"]["contradiction_count"], 1)
        self.assertIn("Accelerate", result["summary"]["sources"])
        self.assertFalse(
            result["summary"]["ready_for_article"]
        )  # Need 3 evidence, 1 contradiction

    @patch("mcp_server.tools.firestore_client.get_problem")
    def test_analyze_problem_not_found(self, mock_get):
        """Test analyzing a non-existent problem."""
        mock_get.return_value = None

        result = tools.problems(action="analyze", problem_id="prob_missing")

        self.assertIn("error", result)
        self.assertIn("not found", result["error"].lower())

    @patch("mcp_server.tools.firestore_client.get_problem")
    @patch("mcp_server.tools.firestore_client.list_problems")
    def test_analyze_all_problems(self, mock_list, mock_get):
        """Test analyzing all active problems."""
        mock_list.return_value = [
            {"problem_id": "prob_001", "problem": "Problem 1"},
            {"problem_id": "prob_002", "problem": "Problem 2"},
        ]

        mock_get.side_effect = [
            {
                "problem_id": "prob_001",
                "problem": "Problem 1",
                "description": "",
                "evidence": [
                    {
                        "chunk_id": "chunk_1",
                        "source_title": "Source A",
                        "quote": "Quote 1",
                        "similarity": 0.8,
                        "is_contradiction": False,
                    }
                ],
            },
            {
                "problem_id": "prob_002",
                "problem": "Problem 2",
                "description": "",
                "evidence": [],
            },
        ]

        result = tools.problems(action="analyze")

        # Should analyze all problems
        self.assertEqual(result["total_analyzed"], 2)
        self.assertEqual(len(result["problems"]), 2)
        self.assertEqual(result["problems"][0]["summary"]["evidence_count"], 1)
        self.assertEqual(result["problems"][1]["summary"]["evidence_count"], 0)

    @patch("mcp_server.tools.firestore_client.get_problem")
    def test_analyze_ready_for_article(self, mock_get):
        """Test ready_for_article flag logic."""
        mock_get.return_value = {
            "problem_id": "prob_001",
            "problem": "Well-researched problem",
            "description": "",
            "evidence": [
                {
                    "chunk_id": "chunk_1",
                    "source_title": "Source A",
                    "quote": "Quote 1",
                    "similarity": 0.8,
                    "is_contradiction": False,
                },
                {
                    "chunk_id": "chunk_2",
                    "source_title": "Source B",
                    "quote": "Quote 2",
                    "similarity": 0.75,
                    "is_contradiction": False,
                },
                {
                    "chunk_id": "chunk_3",
                    "source_title": "Source C",
                    "quote": "Quote 3",
                    "similarity": 0.7,
                    "is_contradiction": True,
                },
            ],
        }

        result = tools.problems(action="analyze", problem_id="prob_001")

        # 3 evidence + 1 contradiction = ready
        self.assertTrue(result["summary"]["ready_for_article"])


class TestProblemsArchive(unittest.TestCase):
    """Test suite for problems(action='archive')."""

    @patch("mcp_server.tools.firestore_client.archive_problem")
    def test_archive_problem_success(self, mock_archive):
        """Test archiving a problem."""
        mock_archive.return_value = {
            "problem_id": "prob_001",
            "status": "archived",
            "evidence_preserved": True,
        }

        result = tools.problems(action="archive", problem_id="prob_001")

        self.assertEqual(result["problem_id"], "prob_001")
        self.assertEqual(result["status"], "archived")
        self.assertTrue(result["evidence_preserved"])

        mock_archive.assert_called_once_with("prob_001")

    def test_archive_without_problem_id(self):
        """Test archive requires problem_id."""
        result = tools.problems(action="archive")

        self.assertIn("error", result)
        self.assertIn("required", result["error"].lower())

    @patch("mcp_server.tools.firestore_client.archive_problem")
    def test_archive_problem_not_found(self, mock_archive):
        """Test archiving non-existent problem."""
        mock_archive.return_value = {
            "success": False,
            "error": "Problem prob_missing not found",
        }

        result = tools.problems(action="archive", problem_id="prob_missing")

        self.assertIn("error", result)


class TestProblemsUnknownAction(unittest.TestCase):
    """Test unknown action handling."""

    def test_unknown_action(self):
        """Test that unknown action returns error."""
        result = tools.problems(action="invalid_action")

        self.assertIn("error", result)
        self.assertIn("unknown", result["error"].lower())


class TestFirestoreProblems(unittest.TestCase):
    """Test suite for problems Firestore functions."""

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_create_problem(self, mock_get_client):
        """Test creating a problem in Firestore."""
        from mcp_server import firestore_client

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        result = firestore_client.create_problem(
            problem="Test problem",
            description="Test description",
            embedding=[0.1] * 768,
        )

        # Verify document created
        mock_db.collection.assert_called_with("problems")
        mock_doc_ref.set.assert_called_once()

        # Check result
        self.assertIn("problem_id", result)
        self.assertEqual(result["problem"], "Test problem")
        self.assertEqual(result["status"], "active")

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_list_problems_active(self, mock_get_client):
        """Test listing active problems."""
        from mcp_server import firestore_client

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        # Mock query chain
        mock_query = MagicMock()
        mock_db.collection.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query

        # Mock document
        mock_doc = MagicMock()
        mock_doc.id = "prob_001"
        mock_doc.to_dict.return_value = {
            "problem": "Test problem",
            "description": "Description",
            "status": "active",
            "evidence": [],
            "evidence_count": 0,
            "contradiction_count": 0,
            "created_at": datetime.utcnow(),
        }
        mock_query.stream.return_value = [mock_doc]

        result = firestore_client.list_problems(status="active")

        # Verify query
        mock_query.where.assert_called_with("status", "==", "active")

        # Check result
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["problem_id"], "prob_001")

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_add_evidence_to_problem(self, mock_get_client):
        """Test adding evidence to a problem."""
        from mcp_server import firestore_client

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        # Mock document retrieval
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "evidence": [],
            "evidence_count": 0,
            "contradiction_count": 0,
        }
        mock_doc_ref.get.return_value = mock_doc
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        result = firestore_client.add_evidence_to_problem(
            problem_id="prob_001",
            evidence={
                "chunk_id": "chunk_123",
                "source_title": "Test Source",
                "quote": "Test quote",
                "similarity": 0.8,
                "is_contradiction": False,
            },
        )

        self.assertTrue(result)
        mock_doc_ref.update.assert_called_once()

    @patch("mcp_server.firestore_client.get_firestore_client")
    def test_archive_problem(self, mock_get_client):
        """Test archiving a problem."""
        from mcp_server import firestore_client

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc_ref.get.return_value = mock_doc
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        result = firestore_client.archive_problem("prob_001")

        self.assertEqual(result["problem_id"], "prob_001")
        self.assertEqual(result["status"], "archived")
        self.assertTrue(result["evidence_preserved"])
        mock_doc_ref.update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
