"""
Unit tests for Epic 10 Problem Matcher.

Tests the pipeline integration for matching new chunks to problems:
- Cosine similarity calculation
- Problem matching with threshold
- Contradiction detection
- Evidence addition

Mocks Firestore to test logic without GCP dependencies.
"""

import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/embed"))


class TestCosineSimilarity(unittest.TestCase):
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        """Test similarity of identical vectors is 1.0."""
        from problem_matcher import cosine_similarity

        vec = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = cosine_similarity(vec, vec)
        self.assertAlmostEqual(result, 1.0, places=5)

    def test_orthogonal_vectors(self):
        """Test similarity of orthogonal vectors is 0.0."""
        from problem_matcher import cosine_similarity

        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        result = cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(result, 0.0, places=5)

    def test_opposite_vectors(self):
        """Test similarity of opposite vectors is -1.0."""
        from problem_matcher import cosine_similarity

        vec1 = [1.0, 0.0]
        vec2 = [-1.0, 0.0]
        result = cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(result, -1.0, places=5)

    def test_empty_vectors(self):
        """Test empty vectors return 0.0."""
        from problem_matcher import cosine_similarity

        self.assertEqual(cosine_similarity([], []), 0.0)
        self.assertEqual(cosine_similarity([1.0], []), 0.0)
        self.assertEqual(cosine_similarity([], [1.0]), 0.0)

    def test_different_length_vectors(self):
        """Test different length vectors return 0.0."""
        from problem_matcher import cosine_similarity

        vec1 = [1.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        result = cosine_similarity(vec1, vec2)
        self.assertEqual(result, 0.0)


class TestCheckForContradiction(unittest.TestCase):
    """Test contradiction detection logic."""

    def test_no_contradiction(self):
        """Test when no contradiction exists."""
        from problem_matcher import check_for_contradiction

        existing_evidence = [
            {"source_id": "source-a"},
            {"source_id": "source-b"},
        ]
        relationships = [
            {"type": "extends", "target_source": "source-c"},
        ]

        result = check_for_contradiction("source-new", existing_evidence, relationships)
        self.assertFalse(result)

    def test_contradiction_found(self):
        """Test when contradiction is found."""
        from problem_matcher import check_for_contradiction

        existing_evidence = [
            {"source_id": "source-a"},
            {"source_id": "source-b"},
        ]
        relationships = [
            {"type": "contradicts", "target_source": "source-a"},
        ]

        result = check_for_contradiction("source-new", existing_evidence, relationships)
        self.assertTrue(result)

    def test_no_relationships(self):
        """Test with no relationships."""
        from problem_matcher import check_for_contradiction

        existing_evidence = [{"source_id": "source-a"}]
        result = check_for_contradiction("source-new", existing_evidence, [])
        self.assertFalse(result)


class TestMatchChunksToProblems(unittest.TestCase):
    """Test the main matching function."""

    @patch("problem_matcher.add_evidence_to_problem")
    @patch("problem_matcher.get_source_relationships")
    @patch("problem_matcher.get_chunk_with_embedding")
    @patch("problem_matcher.get_active_problems_with_embeddings")
    def test_successful_match(
        self, mock_get_problems, mock_get_chunk, mock_get_rels, mock_add_evidence
    ):
        """Test successful chunk-to-problem matching."""
        from problem_matcher import match_chunks_to_problems

        # Create normalized vectors that will have high similarity
        # Both point roughly in the same direction
        problem_embedding = [0.5] * 768
        chunk_embedding = [0.52] * 768  # Very similar direction

        # Mock active problems with embeddings
        mock_get_problems.return_value = [
            {
                "problem_id": "prob_001",
                "problem": "Why do feature flags fail?",
                "embedding": problem_embedding,
                "evidence": [],
            }
        ]

        # Mock chunk with similar embedding
        mock_get_chunk.return_value = {
            "chunk_id": "chunk_123",
            "source_id": "accelerate",
            "title": "Accelerate",
            "content": "Elite performers deploy 208x more frequently",
            "embedding": chunk_embedding,
        }

        mock_get_rels.return_value = []
        mock_add_evidence.return_value = True

        result = match_chunks_to_problems(["chunk_123"], similarity_threshold=0.7)

        # Should find a match
        self.assertEqual(result["chunks_processed"], 1)
        self.assertEqual(result["matches_found"], 1)
        self.assertEqual(result["contradictions_found"], 0)
        self.assertIn("prob_001", result["problems_updated"])

        # Verify evidence was added
        mock_add_evidence.assert_called_once()
        call_args = mock_add_evidence.call_args
        self.assertEqual(call_args[0][0], "prob_001")  # problem_id
        evidence = call_args[0][1]
        self.assertEqual(evidence["chunk_id"], "chunk_123")
        self.assertFalse(evidence["is_contradiction"])

    @patch("problem_matcher.get_active_problems_with_embeddings")
    def test_no_active_problems(self, mock_get_problems):
        """Test when no active problems exist."""
        from problem_matcher import match_chunks_to_problems

        mock_get_problems.return_value = []

        result = match_chunks_to_problems(["chunk_123"])

        self.assertEqual(result["chunks_processed"], 1)
        self.assertEqual(result["matches_found"], 0)

    @patch("problem_matcher.get_chunk_with_embedding")
    @patch("problem_matcher.get_active_problems_with_embeddings")
    def test_below_threshold(self, mock_get_problems, mock_get_chunk):
        """Test when similarity is below threshold."""
        from problem_matcher import match_chunks_to_problems

        # Problem embedding
        mock_get_problems.return_value = [
            {
                "problem_id": "prob_001",
                "problem": "Feature flags",
                "embedding": [1.0] + [0.0] * 767,
                "evidence": [],
            }
        ]

        # Chunk with orthogonal embedding (low similarity)
        mock_get_chunk.return_value = {
            "chunk_id": "chunk_123",
            "source_id": "unrelated",
            "title": "Unrelated Topic",
            "content": "Something completely different",
            "embedding": [0.0] + [1.0] + [0.0] * 766,  # Orthogonal
        }

        result = match_chunks_to_problems(["chunk_123"], similarity_threshold=0.7)

        # Should not match
        self.assertEqual(result["matches_found"], 0)

    @patch("problem_matcher.add_evidence_to_problem")
    @patch("problem_matcher.get_source_relationships")
    @patch("problem_matcher.get_chunk_with_embedding")
    @patch("problem_matcher.get_active_problems_with_embeddings")
    def test_contradiction_detected(
        self, mock_get_problems, mock_get_chunk, mock_get_rels, mock_add_evidence
    ):
        """Test contradiction detection."""
        from problem_matcher import match_chunks_to_problems

        # Create similar embeddings for matching
        problem_embedding = [0.5] * 768
        chunk_embedding = [0.52] * 768

        # Problem with existing evidence
        mock_get_problems.return_value = [
            {
                "problem_id": "prob_001",
                "problem": "Feature flags",
                "embedding": problem_embedding,
                "evidence": [{"source_id": "accelerate"}],
            }
        ]

        # Chunk that contradicts existing evidence
        mock_get_chunk.return_value = {
            "chunk_id": "chunk_456",
            "source_id": "move-fast",
            "title": "Move Fast and Break Things",
            "content": "Speed requires accepting bugs",
            "embedding": chunk_embedding,
        }

        # Relationship showing contradiction
        mock_get_rels.return_value = [
            {"type": "contradicts", "target_source": "accelerate", "context": "Different philosophy"}
        ]

        mock_add_evidence.return_value = True

        result = match_chunks_to_problems(["chunk_456"], similarity_threshold=0.7)

        self.assertEqual(result["matches_found"], 1)
        self.assertEqual(result["contradictions_found"], 1)

        # Verify evidence marked as contradiction
        call_args = mock_add_evidence.call_args
        evidence = call_args[0][1]
        self.assertTrue(evidence["is_contradiction"])
        self.assertIn("relationship", evidence)

    def test_empty_chunk_list(self):
        """Test with empty chunk list."""
        from problem_matcher import match_chunks_to_problems

        result = match_chunks_to_problems([])

        self.assertEqual(result["chunks_processed"], 0)
        self.assertEqual(result["matches_found"], 0)

    @patch("problem_matcher.get_chunk_with_embedding")
    @patch("problem_matcher.get_active_problems_with_embeddings")
    def test_chunk_not_found(self, mock_get_problems, mock_get_chunk):
        """Test when chunk is not found."""
        from problem_matcher import match_chunks_to_problems

        mock_get_problems.return_value = [
            {
                "problem_id": "prob_001",
                "problem": "Test problem",
                "embedding": [1.0] + [0.0] * 767,
                "evidence": [],
            }
        ]

        mock_get_chunk.return_value = None  # Chunk not found

        result = match_chunks_to_problems(["missing_chunk"])

        self.assertEqual(result["chunks_processed"], 1)
        self.assertEqual(result["matches_found"], 0)

    @patch("problem_matcher.get_chunk_with_embedding")
    @patch("problem_matcher.get_active_problems_with_embeddings")
    def test_chunk_without_embedding(self, mock_get_problems, mock_get_chunk):
        """Test when chunk has no embedding."""
        from problem_matcher import match_chunks_to_problems

        mock_get_problems.return_value = [
            {
                "problem_id": "prob_001",
                "problem": "Test problem",
                "embedding": [1.0] + [0.0] * 767,
                "evidence": [],
            }
        ]

        mock_get_chunk.return_value = {
            "chunk_id": "chunk_no_embed",
            "source_id": "test",
            "title": "Test",
            "content": "Content",
            "embedding": None,  # No embedding
        }

        result = match_chunks_to_problems(["chunk_no_embed"])

        self.assertEqual(result["matches_found"], 0)


if __name__ == "__main__":
    unittest.main()
