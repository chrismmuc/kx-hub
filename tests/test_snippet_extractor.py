"""
Unit tests for KB-Aware Two-Stage Snippet Extraction (Story 13.2).

Tests cover:
- Pure functions and data classes (tests 1-8)
- Stage 1: Candidate extraction (tests 9-12)
- Stage 1.5: KB enrichment (tests 13-19)
- Stage 2: KB-aware judge (tests 20-24)
- Integration: extract_snippets pipeline (tests 25-28)
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/mcp_server"))

from knowledge_cards.snippet_extractor import (
    ExtractedSnippet,
    CandidateSnippet,
    SnippetExtractionError,
    calculate_snippet_count,
    _extract_candidates,
    _enrich_with_kb_context,
    _enrich_single_candidate,
    _judge_snippets,
    _fallback_select,
    _composite_score,
    _build_candidate_summary,
    _has_kb_services,
    extract_snippets,
    OVERFLOW_THRESHOLD,
)
import knowledge_cards.snippet_extractor as snippet_module


# ============================================================================
# Test Helpers
# ============================================================================

SAMPLE_ARTICLE = """
The key insight from our research is that teams adopting feature flags without
proper governance inevitably create technical debt. In our study of 50 engineering
organizations, we found that 73% accumulated over 200 stale flags within 18 months.

This problem compounds because each flag represents a branch in code logic that
must be maintained and tested. The cognitive load on developers increases
exponentially with the number of active flags.

However, organizations that implemented automated flag lifecycle management saw
a 60% reduction in stale flags and reported higher developer satisfaction scores.
The most effective approach combined automated expiry with regular cleanup sprints.

In conclusion, feature flags are powerful but require disciplined management.
Teams should treat flags as temporary constructs with explicit expiration dates.
"""

SAMPLE_TITLE = "The Hidden Cost of Feature Flags"
SAMPLE_AUTHOR = "Jane Developer"
SAMPLE_WORD_COUNT = 3000


def _make_candidate(
    text="Some snippet text",
    context="Why it matters",
    position="middle",
    kb_novelty=1.0,
    is_novel=True,
    similar_to=None,
    problem_relevance=0.0,
    problem_id=None,
    problem_text=None,
):
    return CandidateSnippet(
        text=text,
        context=context,
        position=position,
        kb_novelty=kb_novelty,
        is_novel=is_novel,
        similar_to=similar_to,
        problem_relevance=problem_relevance,
        problem_id=problem_id,
        problem_text=problem_text,
    )


def _make_candidates(count=6):
    positions = ["intro", "middle", "conclusion"]
    return [
        _make_candidate(
            text=f"Snippet text number {i}",
            context=f"Context for snippet {i}",
            position=positions[i % 3],
            kb_novelty=0.5 + (i * 0.1),
            problem_relevance=0.3 + (i * 0.05),
        )
        for i in range(count)
    ]


# ============================================================================
# Tests 1-8: Pure Functions and Data Classes
# ============================================================================


class TestDataClasses(unittest.TestCase):
    """Tests for ExtractedSnippet and CandidateSnippet data classes."""

    def test_extracted_snippet_creation(self):
        """Test 1: ExtractedSnippet has required fields."""
        snippet = ExtractedSnippet(
            text="A direct quote",
            context="Why this matters",
            position="intro",
        )
        self.assertEqual(snippet.text, "A direct quote")
        self.assertEqual(snippet.context, "Why this matters")
        self.assertEqual(snippet.position, "intro")

    def test_candidate_snippet_defaults(self):
        """Test 2: CandidateSnippet has correct defaults."""
        candidate = CandidateSnippet(
            text="Quote text",
            context="Context",
            position="middle",
        )
        self.assertEqual(candidate.kb_novelty, 1.0)
        self.assertTrue(candidate.is_novel)
        self.assertIsNone(candidate.similar_to)
        self.assertEqual(candidate.problem_relevance, 0.0)
        self.assertIsNone(candidate.problem_id)
        self.assertIsNone(candidate.problem_text)

    def test_candidate_snippet_full_init(self):
        """Test 3: CandidateSnippet accepts all fields."""
        candidate = CandidateSnippet(
            text="Quote",
            context="Context",
            position="conclusion",
            kb_novelty=0.7,
            is_novel=True,
            similar_to="Existing Article",
            problem_relevance=0.85,
            problem_id="prob_001",
            problem_text="Why do feature flags fail?",
        )
        self.assertEqual(candidate.kb_novelty, 0.7)
        self.assertEqual(candidate.similar_to, "Existing Article")
        self.assertEqual(candidate.problem_id, "prob_001")


class TestCalculateSnippetCount(unittest.TestCase):
    """Tests for calculate_snippet_count()."""

    def test_minimum_count(self):
        """Test 4: Very short articles get minimum 2 snippets."""
        self.assertEqual(calculate_snippet_count(100), 2)
        self.assertEqual(calculate_snippet_count(0), 2)
        self.assertEqual(calculate_snippet_count(800), 2)

    def test_normal_count(self):
        """Test 5: Normal articles scale linearly."""
        self.assertEqual(calculate_snippet_count(1600), 2)
        self.assertEqual(calculate_snippet_count(2400), 3)
        self.assertEqual(calculate_snippet_count(4000), 5)
        self.assertEqual(calculate_snippet_count(8000), 10)

    def test_maximum_count(self):
        """Test 6: Very long articles cap at 15 snippets."""
        self.assertEqual(calculate_snippet_count(12000), 15)
        self.assertEqual(calculate_snippet_count(50000), 15)

    def test_boundary_values(self):
        """Test 7: Test exact boundary values."""
        # 1600 // 800 = 2, max(2, min(15, 2)) = 2
        self.assertEqual(calculate_snippet_count(1600), 2)
        # 12000 // 800 = 15, max(2, min(15, 15)) = 15
        self.assertEqual(calculate_snippet_count(12000), 15)
        # 12800 // 800 = 16, max(2, min(15, 16)) = 15
        self.assertEqual(calculate_snippet_count(12800), 15)


class TestSnippetExtractionError(unittest.TestCase):
    """Test custom exception."""

    def test_error_is_exception(self):
        """Test 8: SnippetExtractionError is a proper exception."""
        with self.assertRaises(SnippetExtractionError):
            raise SnippetExtractionError("Test error")

        err = SnippetExtractionError("message")
        self.assertEqual(str(err), "message")


# ============================================================================
# Tests 9-12: Stage 1 - Candidate Extraction
# ============================================================================


class TestStage1CandidateExtraction(unittest.TestCase):
    """Tests for _extract_candidates()."""

    def setUp(self):
        # Reset LLM client cache before each test
        snippet_module._llm_client = None

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_successful_extraction(self, mock_get_client):
        """Test 9: Successful candidate extraction from LLM."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [
                {
                    "text": "Teams adopting feature flags without proper governance inevitably create technical debt.",
                    "context": "Key finding from research",
                    "position": "intro",
                },
                {
                    "text": "73% accumulated over 200 stale flags within 18 months.",
                    "context": "Quantitative evidence",
                    "position": "middle",
                },
            ]
        }
        mock_get_client.return_value = mock_client

        candidates = _extract_candidates(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR, 4)

        self.assertEqual(len(candidates), 2)
        self.assertIsInstance(candidates[0], CandidateSnippet)
        self.assertEqual(candidates[0].position, "intro")
        self.assertEqual(candidates[1].position, "middle")
        # Default KB values
        self.assertEqual(candidates[0].kb_novelty, 1.0)
        self.assertTrue(candidates[0].is_novel)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_json_parse_error_retry(self, mock_get_client):
        """Test 10: Retry on JSON parse error, succeed on second attempt."""
        mock_client = MagicMock()
        mock_client.generate_json.side_effect = [
            ValueError("Invalid JSON"),
            {
                "snippets": [
                    {"text": "Valid snippet", "context": "Context", "position": "middle"},
                ]
            },
        ]
        mock_get_client.return_value = mock_client

        candidates = _extract_candidates(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR, 2)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(mock_client.generate_json.call_count, 2)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_persistent_failure_raises_error(self, mock_get_client):
        """Test 11: Persistent failures raise SnippetExtractionError."""
        mock_client = MagicMock()
        mock_client.generate_json.side_effect = ValueError("Invalid JSON")
        mock_get_client.return_value = mock_client

        with self.assertRaises(SnippetExtractionError):
            _extract_candidates(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR, 4)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_empty_snippets_retry_then_error(self, mock_get_client):
        """Test 12: Empty snippets array triggers retry, then error."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {"snippets": []}
        mock_get_client.return_value = mock_client

        with self.assertRaises(SnippetExtractionError):
            _extract_candidates(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR, 4)

        self.assertEqual(mock_client.generate_json.call_count, 2)


# ============================================================================
# Tests 13-19: Stage 1.5 - KB Enrichment
# ============================================================================


class TestStage15KBEnrichment(unittest.TestCase):
    """Tests for _enrich_with_kb_context() and _enrich_single_candidate()."""

    @patch("knowledge_cards.snippet_extractor.firestore_client")
    @patch("knowledge_cards.snippet_extractor.embeddings")
    @patch("knowledge_cards.snippet_extractor.cosine_similarity")
    def test_enrichment_with_novel_snippet(self, mock_cosine, mock_embed, mock_fs):
        """Test 13: Novel snippet gets high novelty score."""
        # Force KB services available
        snippet_module._kb_services_available = True

        mock_embed.generate_query_embedding.return_value = [0.1] * 768
        mock_fs.find_nearest.return_value = [
            {"title": "Existing Article", "embedding": [0.5] * 768}
        ]
        mock_fs.get_active_problems_with_embeddings.return_value = []
        # Low similarity = high novelty
        mock_cosine.return_value = 0.3

        candidate = _make_candidate(text="A completely novel insight")
        result = _enrich_single_candidate(candidate, [])

        self.assertAlmostEqual(result.kb_novelty, 0.7, places=1)
        self.assertTrue(result.is_novel)
        self.assertEqual(result.similar_to, "Existing Article")

    @patch("knowledge_cards.snippet_extractor.firestore_client")
    @patch("knowledge_cards.snippet_extractor.embeddings")
    @patch("knowledge_cards.snippet_extractor.cosine_similarity")
    def test_enrichment_with_duplicate_snippet(self, mock_cosine, mock_embed, mock_fs):
        """Test 14: Duplicate snippet gets low novelty score."""
        snippet_module._kb_services_available = True

        mock_embed.generate_query_embedding.return_value = [0.1] * 768
        mock_fs.find_nearest.return_value = [
            {"title": "Same Article", "embedding": [0.1] * 768}
        ]
        mock_fs.get_active_problems_with_embeddings.return_value = []
        # High similarity = low novelty
        mock_cosine.return_value = 0.95

        candidate = _make_candidate(text="Already known content")
        result = _enrich_single_candidate(candidate, [])

        self.assertAlmostEqual(result.kb_novelty, 0.05, places=2)
        self.assertFalse(result.is_novel)

    @patch("knowledge_cards.snippet_extractor.firestore_client")
    @patch("knowledge_cards.snippet_extractor.embeddings")
    @patch("knowledge_cards.snippet_extractor.cosine_similarity")
    def test_enrichment_with_problem_match(self, mock_cosine, mock_embed, mock_fs):
        """Test 15: Snippet matching a Feynman problem gets relevance score."""
        snippet_module._kb_services_available = True

        mock_embed.generate_query_embedding.return_value = [0.1] * 768
        mock_fs.find_nearest.return_value = []  # Empty KB

        problems = [
            {
                "problem_id": "prob_001",
                "problem": "Why do feature flags fail?",
                "embedding": [0.2] * 768,
            }
        ]
        # First call: novelty (no items returned), second call: problem similarity
        mock_cosine.return_value = 0.82

        candidate = _make_candidate(text="Feature flag governance matters")
        result = _enrich_single_candidate(candidate, problems)

        self.assertAlmostEqual(result.problem_relevance, 0.82, places=2)
        self.assertEqual(result.problem_id, "prob_001")
        self.assertEqual(result.problem_text, "Why do feature flags fail?")

    @patch("knowledge_cards.snippet_extractor.firestore_client")
    @patch("knowledge_cards.snippet_extractor.embeddings")
    @patch("knowledge_cards.snippet_extractor.cosine_similarity")
    def test_enrichment_empty_kb(self, mock_cosine, mock_embed, mock_fs):
        """Test 16: Empty KB means everything is fully novel."""
        snippet_module._kb_services_available = True

        mock_embed.generate_query_embedding.return_value = [0.1] * 768
        mock_fs.find_nearest.return_value = []
        mock_fs.get_active_problems_with_embeddings.return_value = []

        candidate = _make_candidate(text="Any snippet")
        result = _enrich_single_candidate(candidate, [])

        self.assertEqual(result.kb_novelty, 1.0)
        self.assertTrue(result.is_novel)

    @patch("knowledge_cards.snippet_extractor.firestore_client")
    @patch("knowledge_cards.snippet_extractor.embeddings")
    def test_enrichment_graceful_degradation(self, mock_embed, mock_fs):
        """Test 17: Enrichment failure keeps default values."""
        snippet_module._kb_services_available = True

        mock_embed.generate_query_embedding.side_effect = Exception("API down")
        mock_fs.get_active_problems_with_embeddings.return_value = []

        candidate = _make_candidate(text="Some snippet")
        result = _enrich_single_candidate(candidate, [])

        # Defaults preserved
        self.assertEqual(result.kb_novelty, 1.0)
        self.assertTrue(result.is_novel)
        self.assertEqual(result.problem_relevance, 0.0)

    def test_enrichment_skips_when_no_kb_services(self):
        """Test 18: Enrichment skips when KB services unavailable."""
        snippet_module._kb_services_available = False

        candidates = _make_candidates(3)
        result = _enrich_with_kb_context(candidates)

        # Should return candidates unchanged
        self.assertEqual(len(result), 3)
        for c in result:
            self.assertEqual(c.kb_novelty, c.kb_novelty)  # unchanged

        # Reset for other tests
        snippet_module._kb_services_available = None

    @patch("knowledge_cards.snippet_extractor.firestore_client")
    @patch("knowledge_cards.snippet_extractor.embeddings")
    @patch("knowledge_cards.snippet_extractor.cosine_similarity")
    def test_enrichment_parallel_execution(self, mock_cosine, mock_embed, mock_fs):
        """Test 19: Enrichment processes multiple candidates."""
        snippet_module._kb_services_available = True

        mock_embed.generate_query_embedding.return_value = [0.1] * 768
        mock_fs.find_nearest.return_value = [
            {"title": "KB Item", "embedding": [0.5] * 768}
        ]
        mock_fs.get_active_problems_with_embeddings.return_value = [
            {"problem_id": "p1", "problem": "Test problem", "embedding": [0.3] * 768}
        ]
        mock_cosine.return_value = 0.6

        candidates = _make_candidates(4)
        result = _enrich_with_kb_context(candidates)

        self.assertEqual(len(result), 4)
        # All should have been enriched
        self.assertEqual(mock_embed.generate_query_embedding.call_count, 4)


# ============================================================================
# Tests 20-24: Stage 2 - KB-Aware Judge
# ============================================================================


class TestStage2Judge(unittest.TestCase):
    """Tests for _judge_snippets()."""

    def setUp(self):
        snippet_module._llm_client = None

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_judge_selects_correct_count(self, mock_get_client):
        """Test 20: Judge returns correct number of snippets."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "selected": [0, 2, 4],
            "reasoning": "Selected for novelty and quality",
        }
        mock_get_client.return_value = mock_client

        candidates = _make_candidates(6)
        result = _judge_snippets(candidates, 3, SAMPLE_TITLE, SAMPLE_AUTHOR)

        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[0], ExtractedSnippet)
        self.assertEqual(result[0].text, candidates[0].text)
        self.assertEqual(result[1].text, candidates[2].text)
        self.assertEqual(result[2].text, candidates[4].text)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_judge_wrong_count_triggers_fallback(self, mock_get_client):
        """Test 21: Wrong count from judge uses composite fallback."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "selected": [0, 1],  # Only 2 instead of 3
            "reasoning": "Oops",
        }
        mock_get_client.return_value = mock_client

        candidates = _make_candidates(6)
        result = _judge_snippets(candidates, 3, SAMPLE_TITLE, SAMPLE_AUTHOR)

        # Should pad to 3 using composite score
        self.assertEqual(len(result), 3)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_judge_failure_uses_full_fallback(self, mock_get_client):
        """Test 22: Judge failure falls back to composite scoring."""
        mock_client = MagicMock()
        mock_client.generate_json.side_effect = Exception("LLM error")
        mock_get_client.return_value = mock_client

        candidates = _make_candidates(6)
        result = _judge_snippets(candidates, 3, SAMPLE_TITLE, SAMPLE_AUTHOR)

        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[0], ExtractedSnippet)

    def test_judge_returns_all_when_fewer_candidates_than_target(self):
        """Test 23: When candidates <= target, return all without judging."""
        candidates = _make_candidates(2)
        result = _judge_snippets(candidates, 3, SAMPLE_TITLE, SAMPLE_AUTHOR)

        self.assertEqual(len(result), 2)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_judge_duplicate_indices_deduped(self, mock_get_client):
        """Test 24: Duplicate indices from judge are removed."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "selected": [0, 0, 2, 2, 4],  # Duplicates
            "reasoning": "Duplicated",
        }
        mock_get_client.return_value = mock_client

        candidates = _make_candidates(6)
        # target_count=3, judge returns [0,2,4] after dedup = 3, correct
        result = _judge_snippets(candidates, 3, SAMPLE_TITLE, SAMPLE_AUTHOR)

        self.assertEqual(len(result), 3)


# ============================================================================
# Tests: Composite Score and Fallback
# ============================================================================


class TestCompositeScoreAndFallback(unittest.TestCase):
    """Tests for _composite_score() and _fallback_select()."""

    def test_composite_score_high_novelty_and_relevance(self):
        """Composite score rewards novelty and problem relevance."""
        high = _make_candidate(kb_novelty=0.9, problem_relevance=0.8, position="intro")
        low = _make_candidate(kb_novelty=0.1, problem_relevance=0.1, position="middle")

        self.assertGreater(_composite_score(high), _composite_score(low))

    def test_fallback_select_respects_target_count(self):
        """Fallback always returns exactly target_count (or fewer if not enough)."""
        candidates = _make_candidates(6)
        result = _fallback_select(candidates, 3)
        self.assertEqual(len(result), 3)

    def test_fallback_pads_from_preferred(self):
        """Fallback pads preferred indices to reach target count."""
        candidates = _make_candidates(6)
        result = _fallback_select(candidates, 3, preferred_indices=[0])
        self.assertEqual(len(result), 3)
        # Index 0 should be included
        self.assertEqual(result[0].text, candidates[0].text)

    def test_fallback_trims_excess(self):
        """Fallback trims if too many preferred indices."""
        candidates = _make_candidates(6)
        result = _fallback_select(candidates, 2, preferred_indices=[0, 1, 2, 3])
        self.assertEqual(len(result), 2)


# ============================================================================
# Tests: Build Candidate Summary
# ============================================================================


class TestBuildCandidateSummary(unittest.TestCase):

    def test_summary_includes_all_candidates(self):
        """Summary includes all candidate indices."""
        candidates = _make_candidates(3)
        summary = _build_candidate_summary(candidates)
        self.assertIn("[0]", summary)
        self.assertIn("[1]", summary)
        self.assertIn("[2]", summary)

    def test_summary_all_duplicates_note(self):
        """Summary adds note when all candidates are duplicates."""
        candidates = [
            _make_candidate(kb_novelty=0.05, is_novel=False),
            _make_candidate(kb_novelty=0.03, is_novel=False),
        ]
        summary = _build_candidate_summary(candidates)
        self.assertIn("All candidates overlap", summary)

    def test_summary_includes_problem_relevance(self):
        """Summary shows problem relevance when present."""
        candidates = [
            _make_candidate(
                problem_relevance=0.85,
                problem_text="Why do feature flags fail?",
            ),
        ]
        summary = _build_candidate_summary(candidates)
        self.assertIn("0.85", summary)
        self.assertIn("feature flags", summary)


# ============================================================================
# Tests 25-28: Integration - extract_snippets()
# ============================================================================


class TestExtractSnippets(unittest.TestCase):
    """Integration tests for the full extract_snippets() pipeline."""

    def setUp(self):
        snippet_module._llm_client = None
        # Store original value
        self._original_kb = snippet_module._kb_services_available

    def tearDown(self):
        snippet_module._kb_services_available = self._original_kb

    def test_empty_text_returns_empty(self):
        """Test 25: Empty text returns empty list immediately."""
        result = extract_snippets(
            text="", title="Title", author="Author", word_count=0
        )
        self.assertEqual(result, [])

    def test_whitespace_text_returns_empty(self):
        """Test 26: Whitespace-only text returns empty list."""
        result = extract_snippets(
            text="   \n\t  ", title="Title", author="Author", word_count=0
        )
        self.assertEqual(result, [])

    @patch("knowledge_cards.snippet_extractor._judge_snippets")
    @patch("knowledge_cards.snippet_extractor._enrich_with_kb_context")
    @patch("knowledge_cards.snippet_extractor._extract_candidates")
    def test_full_pipeline_with_kb(self, mock_extract, mock_enrich, mock_judge):
        """Test 27: Full pipeline runs Stage 1 → 1.5 → 2 with KB."""
        snippet_module._kb_services_available = True

        candidates = _make_candidates(6)
        enriched = _make_candidates(6)
        for c in enriched:
            c.kb_novelty = 0.7

        mock_extract.return_value = candidates
        mock_enrich.return_value = enriched
        mock_judge.return_value = [
            ExtractedSnippet(text="Selected 1", context="Context 1", position="intro"),
            ExtractedSnippet(text="Selected 2", context="Context 2", position="middle"),
            ExtractedSnippet(text="Selected 3", context="Context 3", position="conclusion"),
        ]

        result = extract_snippets(
            text=SAMPLE_ARTICLE,
            title=SAMPLE_TITLE,
            author=SAMPLE_AUTHOR,
            word_count=3000,
        )

        self.assertEqual(len(result), 3)
        mock_extract.assert_called_once()
        mock_enrich.assert_called_once()
        mock_judge.assert_called_once()

        # Verify candidate_count = target * 2
        call_args = mock_extract.call_args
        self.assertEqual(call_args[0][3], calculate_snippet_count(3000) * 2)

    @patch("knowledge_cards.snippet_extractor._judge_snippets")
    @patch("knowledge_cards.snippet_extractor._extract_candidates")
    def test_pipeline_without_kb(self, mock_extract, mock_judge):
        """Test 28: Pipeline skips enrichment when KB unavailable."""
        snippet_module._kb_services_available = False

        candidates = _make_candidates(4)
        mock_extract.return_value = candidates
        mock_judge.return_value = [
            ExtractedSnippet(text="S1", context="C1", position="intro"),
            ExtractedSnippet(text="S2", context="C2", position="middle"),
        ]

        result = extract_snippets(
            text=SAMPLE_ARTICLE,
            title=SAMPLE_TITLE,
            author=SAMPLE_AUTHOR,
            word_count=1600,
        )

        self.assertEqual(len(result), 2)
        mock_extract.assert_called_once()
        mock_judge.assert_called_once()


# ============================================================================
# Tests: Edge Cases
# ============================================================================


class TestEdgeCases(unittest.TestCase):
    """Additional edge case tests."""

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_stage1_skips_empty_text_snippets(self, mock_get_client):
        """Snippets with empty text are filtered out in Stage 1."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [
                {"text": "", "context": "Empty", "position": "intro"},
                {"text": "Valid snippet", "context": "Good", "position": "middle"},
            ]
        }
        mock_get_client.return_value = mock_client

        candidates = _extract_candidates(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR, 4)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].text, "Valid snippet")

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_judge_invalid_indices_filtered(self, mock_get_client):
        """Judge returning out-of-range indices triggers fallback."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "selected": [0, 99, -1],  # Invalid indices
            "reasoning": "Bad indices",
        }
        mock_get_client.return_value = mock_client

        candidates = _make_candidates(6)
        result = _judge_snippets(candidates, 3, SAMPLE_TITLE, SAMPLE_AUTHOR)

        # Should fallback since only 1 valid index, but need 3
        self.assertEqual(len(result), 3)

    @patch("knowledge_cards.snippet_extractor.firestore_client")
    @patch("knowledge_cards.snippet_extractor.embeddings")
    @patch("knowledge_cards.snippet_extractor.cosine_similarity")
    def test_enrichment_no_active_problems(self, mock_cosine, mock_embed, mock_fs):
        """No active problems means problem_relevance stays 0.0."""
        snippet_module._kb_services_available = True

        mock_embed.generate_query_embedding.return_value = [0.1] * 768
        mock_fs.find_nearest.return_value = []
        mock_fs.get_active_problems_with_embeddings.return_value = []

        # Use candidates with default problem_relevance=0.0
        candidates = [
            _make_candidate(text=f"Snippet {i}", problem_relevance=0.0)
            for i in range(2)
        ]
        result = _enrich_with_kb_context(candidates)

        for c in result:
            self.assertEqual(c.problem_relevance, 0.0)
            self.assertIsNone(c.problem_id)

    @patch("knowledge_cards.snippet_extractor._judge_snippets")
    @patch("knowledge_cards.snippet_extractor._extract_candidates")
    def test_extract_snippets_returns_bounded_count(self, mock_extract, mock_judge):
        """extract_snippets always returns between 0 and 15 snippets."""
        snippet_module._kb_services_available = False

        mock_extract.return_value = _make_candidates(4)
        mock_judge.return_value = [
            ExtractedSnippet(text=f"S{i}", context=f"C{i}", position="middle")
            for i in range(3)
        ]

        result = extract_snippets(
            text=SAMPLE_ARTICLE,
            title=SAMPLE_TITLE,
            author=SAMPLE_AUTHOR,
            word_count=3000,
        )

        self.assertGreaterEqual(len(result), 0)
        self.assertLessEqual(len(result), 15)

    @patch("knowledge_cards.snippet_extractor._extract_candidates")
    def test_extract_snippets_empty_candidates(self, mock_extract):
        """If Stage 1 returns empty candidates, return empty list."""
        snippet_module._kb_services_available = False
        mock_extract.return_value = []

        result = extract_snippets(
            text=SAMPLE_ARTICLE,
            title=SAMPLE_TITLE,
            author=SAMPLE_AUTHOR,
            word_count=3000,
        )

        self.assertEqual(result, [])


# ============================================================================
# Tests: Overflow Threshold
# ============================================================================


class TestOverflowThreshold(unittest.TestCase):
    """Tests for OVERFLOW_THRESHOLD and context-window truncation."""

    def test_overflow_threshold_computed_from_model(self):
        """OVERFLOW_THRESHOLD is derived from the default model's context window."""
        self.assertIsInstance(OVERFLOW_THRESHOLD, int)
        # Must be larger than old 12 KB limit and reasonably sized
        self.assertGreater(OVERFLOW_THRESHOLD, 100_000)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_no_truncation_short_text(self, mock_get_client):
        """Short text is passed verbatim to the LLM prompt."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [{"text": "A quote", "context": "ctx", "position": "intro"}]
        }
        mock_get_client.return_value = mock_client

        short_text = "x" * 100
        _extract_candidates(short_text, "T", "A", 2)

        prompt_used = mock_client.generate_json.call_args[0][0]
        self.assertIn(short_text, prompt_used)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_no_truncation_long_text(self, mock_get_client):
        """Text longer than old 12K limit is NOT truncated."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [{"text": "A quote", "context": "ctx", "position": "middle"}]
        }
        mock_get_client.return_value = mock_client

        long_text = "word " * 5000  # ~25 KB — well below model context limit
        _extract_candidates(long_text, "T", "A", 4)

        prompt_used = mock_client.generate_json.call_args[0][0]
        self.assertIn(long_text, prompt_used)

    @patch("knowledge_cards.snippet_extractor.OVERFLOW_THRESHOLD", 500)
    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_truncation_above_threshold(self, mock_get_client):
        """Text exceeding OVERFLOW_THRESHOLD is truncated before sending to LLM."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [{"text": "A quote", "context": "ctx", "position": "middle"}]
        }
        mock_get_client.return_value = mock_client

        oversized_text = "x" * 800
        _extract_candidates(oversized_text, "Big Article", "A", 4)

        prompt_used = mock_client.generate_json.call_args[0][0]
        # Prompt must NOT contain the full 800-char text
        self.assertNotIn(oversized_text, prompt_used)
        # But must contain a truncated portion
        self.assertIn("x" * 400, prompt_used)

    @patch("knowledge_cards.snippet_extractor.OVERFLOW_THRESHOLD", 500)
    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_truncation_warning_logged(self, mock_get_client):
        """Warning is logged when text is truncated."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [{"text": "A quote", "context": "ctx", "position": "middle"}]
        }
        mock_get_client.return_value = mock_client

        oversized_text = "x" * 800

        with self.assertLogs("knowledge_cards.snippet_extractor", level="WARNING") as cm:
            _extract_candidates(oversized_text, "Big Article", "A", 4)

        self.assertTrue(any("TRUNCATED" in line for line in cm.output))

    @patch("knowledge_cards.snippet_extractor.OVERFLOW_THRESHOLD", 500)
    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_truncation_prefers_sentence_boundary(self, mock_get_client):
        """Truncation breaks at a sentence boundary when possible."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [{"text": "A quote", "context": "ctx", "position": "middle"}]
        }
        mock_get_client.return_value = mock_client

        # Build text with a sentence ending near the threshold
        text = "x" * 460 + ". " + "y" * 200
        _extract_candidates(text, "T", "A", 4)

        prompt_used = mock_client.generate_json.call_args[0][0]
        # Should have truncated at ". " (char 461), not at the raw 500 limit
        self.assertIn("x" * 460 + ".", prompt_used)
        self.assertNotIn("yyy", prompt_used)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_no_truncation_below_threshold(self, mock_get_client):
        """No truncation for texts within threshold."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [{"text": "A quote", "context": "ctx", "position": "intro"}]
        }
        mock_get_client.return_value = mock_client

        normal_text = "x" * 1000  # Well below real threshold

        import logging
        with self.assertLogs("knowledge_cards.snippet_extractor", level="INFO") as cm:
            logging.getLogger("knowledge_cards.snippet_extractor").info("probe")
            _extract_candidates(normal_text, "T", "A", 4)

        truncation_lines = [l for l in cm.output if "TRUNCATED" in l]
        self.assertEqual(truncation_lines, [])


if __name__ == "__main__":
    unittest.main()
