"""
Unit tests for Snippet Extraction (Story 13.2).

Tests cover:
- Data classes and error types
- LLM extraction with retry logic
- Overflow threshold and truncation
- Integration: extract_snippets pipeline
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/mcp_server"))

from knowledge_cards.snippet_extractor import (
    ExtractedSnippet,
    SnippetExtractionError,
    _extract_snippets_llm,
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


# ============================================================================
# Tests: Data Classes
# ============================================================================


class TestDataClasses(unittest.TestCase):
    """Tests for ExtractedSnippet data class."""

    def test_extracted_snippet_creation(self):
        """ExtractedSnippet has required fields."""
        snippet = ExtractedSnippet(
            text="A direct quote",
            context="Why this matters",
            position="intro",
        )
        self.assertEqual(snippet.text, "A direct quote")
        self.assertEqual(snippet.context, "Why this matters")
        self.assertEqual(snippet.position, "intro")


class TestSnippetExtractionError(unittest.TestCase):
    """Test custom exception."""

    def test_error_is_exception(self):
        """SnippetExtractionError is a proper exception."""
        with self.assertRaises(SnippetExtractionError):
            raise SnippetExtractionError("Test error")

        err = SnippetExtractionError("message")
        self.assertEqual(str(err), "message")


# ============================================================================
# Tests: LLM Extraction
# ============================================================================


class TestExtractSnippetsLLM(unittest.TestCase):
    """Tests for _extract_snippets_llm()."""

    def setUp(self):
        snippet_module._llm_client = None

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_successful_extraction(self, mock_get_client):
        """Successful snippet extraction from LLM."""
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

        snippets = _extract_snippets_llm(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR)

        self.assertEqual(len(snippets), 2)
        self.assertIsInstance(snippets[0], ExtractedSnippet)
        self.assertEqual(snippets[0].position, "intro")
        self.assertEqual(snippets[1].position, "middle")

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_json_parse_error_retry(self, mock_get_client):
        """Retry on JSON parse error, succeed on second attempt."""
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

        snippets = _extract_snippets_llm(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR)

        self.assertEqual(len(snippets), 1)
        self.assertEqual(mock_client.generate_json.call_count, 2)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_persistent_failure_raises_error(self, mock_get_client):
        """Persistent failures raise SnippetExtractionError."""
        mock_client = MagicMock()
        mock_client.generate_json.side_effect = ValueError("Invalid JSON")
        mock_get_client.return_value = mock_client

        with self.assertRaises(SnippetExtractionError):
            _extract_snippets_llm(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_empty_snippets_retry_then_error(self, mock_get_client):
        """Empty snippets array triggers retry, then error."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {"snippets": []}
        mock_get_client.return_value = mock_client

        with self.assertRaises(SnippetExtractionError):
            _extract_snippets_llm(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR)

        self.assertEqual(mock_client.generate_json.call_count, 2)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_skips_empty_text_snippets(self, mock_get_client):
        """Snippets with empty text are filtered out."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [
                {"text": "", "context": "Empty", "position": "intro"},
                {"text": "Valid snippet", "context": "Good", "position": "middle"},
            ]
        }
        mock_get_client.return_value = mock_client

        snippets = _extract_snippets_llm(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR)
        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0].text, "Valid snippet")

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_variable_snippet_count(self, mock_get_client):
        """LLM can return variable number of snippets (no fixed cap)."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [
                {"text": f"Snippet {i}", "context": f"Context {i}", "position": "middle"}
                for i in range(20)
            ]
        }
        mock_get_client.return_value = mock_client

        snippets = _extract_snippets_llm(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR)
        self.assertEqual(len(snippets), 20)

    @patch("knowledge_cards.snippet_extractor._get_llm_client")
    def test_prompt_includes_coverage_instruction(self, mock_get_client):
        """Prompt instructs LLM to cover the ENTIRE article."""
        mock_client = MagicMock()
        mock_client.generate_json.return_value = {
            "snippets": [{"text": "A quote", "context": "ctx", "position": "intro"}]
        }
        mock_get_client.return_value = mock_client

        _extract_snippets_llm(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR)

        prompt_used = mock_client.generate_json.call_args[0][0]
        self.assertIn("ENTIRE article", prompt_used)
        self.assertIn("proportionally", prompt_used)


# ============================================================================
# Tests: Integration - extract_snippets()
# ============================================================================


class TestExtractSnippets(unittest.TestCase):
    """Integration tests for the full extract_snippets() pipeline."""

    def setUp(self):
        snippet_module._llm_client = None

    def test_empty_text_returns_empty(self):
        """Empty text returns empty list immediately."""
        result = extract_snippets(
            text="", title="Title", author="Author", word_count=0
        )
        self.assertEqual(result, [])

    def test_whitespace_text_returns_empty(self):
        """Whitespace-only text returns empty list."""
        result = extract_snippets(
            text="   \n\t  ", title="Title", author="Author", word_count=0
        )
        self.assertEqual(result, [])

    @patch("knowledge_cards.snippet_extractor._extract_snippets_llm")
    def test_pipeline_calls_llm_directly(self, mock_extract):
        """Pipeline calls _extract_snippets_llm and returns result."""
        mock_extract.return_value = [
            ExtractedSnippet(text="S1", context="C1", position="intro"),
            ExtractedSnippet(text="S2", context="C2", position="middle"),
            ExtractedSnippet(text="S3", context="C3", position="conclusion"),
        ]

        result = extract_snippets(
            text=SAMPLE_ARTICLE,
            title=SAMPLE_TITLE,
            author=SAMPLE_AUTHOR,
            word_count=3000,
        )

        self.assertEqual(len(result), 3)
        mock_extract.assert_called_once_with(SAMPLE_ARTICLE, SAMPLE_TITLE, SAMPLE_AUTHOR)

    @patch("knowledge_cards.snippet_extractor._extract_snippets_llm")
    def test_empty_extraction_returns_empty(self, mock_extract):
        """If LLM returns empty list, return empty list."""
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
        _extract_snippets_llm(short_text, "T", "A")

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
        _extract_snippets_llm(long_text, "T", "A")

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
        _extract_snippets_llm(oversized_text, "Big Article", "A")

        prompt_used = mock_client.generate_json.call_args[0][0]
        self.assertNotIn(oversized_text, prompt_used)
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
            _extract_snippets_llm(oversized_text, "Big Article", "A")

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

        text = "x" * 460 + ". " + "y" * 200
        _extract_snippets_llm(text, "T", "A")

        prompt_used = mock_client.generate_json.call_args[0][0]
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

        normal_text = "x" * 1000

        import logging
        with self.assertLogs("knowledge_cards.snippet_extractor", level="INFO") as cm:
            logging.getLogger("knowledge_cards.snippet_extractor").info("probe")
            _extract_snippets_llm(normal_text, "T", "A")

        truncation_lines = [l for l in cm.output if "TRUNCATED" in l]
        self.assertEqual(truncation_lines, [])


if __name__ == "__main__":
    unittest.main()
