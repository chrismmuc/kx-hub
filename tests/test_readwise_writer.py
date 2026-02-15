"""
Unit tests for Readwise Writer & Pipeline Integration (Story 13.3).

Tests cover:
- ReadwiseHighlightWriter (tests 1-7)
- embed_snippets (tests 8-15)
- process_document orchestration (tests 16-21)
- Edge cases (tests 22-25)
"""

import hashlib
import os
import sys

import pytest
from unittest.mock import MagicMock, Mock, patch, call

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/mcp_server"))

from ingest.readwise_writer import (
    ReadwiseHighlightWriter,
    embed_snippets,
    process_document,
)
from ingest.reader_client import ReaderDocument
from knowledge_cards.snippet_extractor import ExtractedSnippet


# ============================================================================
# Test Helpers
# ============================================================================


def _make_snippet(
    text="Teams adopting feature flags without governance create debt.",
    context="Key finding about feature flag management.",
    position="middle",
):
    return ExtractedSnippet(text=text, context=context, position=position)


def _make_reader_doc(
    doc_id="doc_123",
    title="The Hidden Cost of Feature Flags",
    author="Jane Developer",
    source_url="https://example.com/feature-flags",
    clean_text="Full article text about feature flags...",
    word_count=3000,
    tags=None,
):
    raw_data = {
        "id": doc_id,
        "title": title,
        "author": author,
        "source_url": source_url,
        "tags": tags or ["kx-auto"],
        "category": "article",
    }
    return ReaderDocument(raw_data, clean_text, word_count)


def _make_snippets(count=3):
    snippets = []
    for i in range(count):
        snippets.append(
            _make_snippet(
                text=f"Snippet {i} text about feature flags and their impact.",
                context=f"Context {i}: why this matters.",
                position=["intro", "middle", "conclusion"][i % 3],
            )
        )
    return snippets


# ============================================================================
# Test 1-7: ReadwiseHighlightWriter
# ============================================================================


class TestReadwiseHighlightWriter:
    """Tests for ReadwiseHighlightWriter class."""

    def test_init(self):
        """Test 1: Writer initializes with API key and session."""
        writer = ReadwiseHighlightWriter("test-api-key")
        assert writer.api_key == "test-api-key"
        assert writer.session.headers["Authorization"] == "Token test-api-key"
        assert writer.BATCH_SIZE == 100

    @patch.object(ReadwiseHighlightWriter, "_post_highlights")
    def test_create_highlights_success(self, mock_post):
        """Test 2: Successfully create highlights from snippets."""
        mock_post.return_value = [
            {"id": 1001},
            {"id": 1002},
            {"id": 1003},
        ]

        writer = ReadwiseHighlightWriter("test-key")
        snippets = _make_snippets(3)
        result = writer.create_highlights(
            snippets=snippets,
            title="Feature Flags Article",
            author="Jane Developer",
            source_url="https://example.com/article",
        )

        assert result["created"] == 3
        assert result["failed"] == 0
        assert result["highlight_ids"] == [1001, 1002, 1003]

        # Verify payload structure
        call_args = mock_post.call_args[0][0]
        highlights = call_args["highlights"]
        assert len(highlights) == 3
        assert highlights[0]["text"] == "Snippet 0 text about feature flags and their impact."
        assert highlights[0]["note"] == "Context 0: why this matters."
        assert highlights[0]["title"] == "Feature Flags Article"
        assert highlights[0]["author"] == "Jane Developer"
        assert highlights[0]["source_url"] == "https://example.com/article"
        assert highlights[0]["source_type"] == "article"
        assert "highlighted_at" in highlights[0]

    @patch.object(ReadwiseHighlightWriter, "_post_highlights")
    def test_create_highlights_empty(self, mock_post):
        """Test 3: Empty snippets list returns zeros."""
        writer = ReadwiseHighlightWriter("test-key")
        result = writer.create_highlights(
            snippets=[],
            title="Title",
            author="Author",
            source_url="https://example.com",
        )

        assert result == {"created": 0, "failed": 0, "highlight_ids": []}
        mock_post.assert_not_called()

    @patch.object(ReadwiseHighlightWriter, "_post_highlights")
    def test_create_highlights_batch_failure(self, mock_post):
        """Test 4: Batch failure records failed count."""
        mock_post.side_effect = Exception("API Error")

        writer = ReadwiseHighlightWriter("test-key")
        snippets = _make_snippets(3)
        result = writer.create_highlights(
            snippets=snippets,
            title="Title",
            author="Author",
            source_url="https://example.com",
        )

        assert result["created"] == 0
        assert result["failed"] == 3
        assert result["highlight_ids"] == []

    def test_post_highlights_success(self):
        """Test 5: POST request succeeds on first attempt."""
        writer = ReadwiseHighlightWriter("test-key")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1}]
        mock_response.raise_for_status = Mock()
        writer.session.post = Mock(return_value=mock_response)

        result = writer._post_highlights({"highlights": [{"text": "test"}]})
        assert result == [{"id": 1}]

        writer.session.post.assert_called_once()
        call_kwargs = writer.session.post.call_args
        assert "highlights/" in call_kwargs[0][0] or "highlights/" in call_kwargs[1].get("url", call_kwargs[0][0])

    @patch("time.sleep")
    def test_post_highlights_rate_limit_retry(self, mock_sleep):
        """Test 6: Retry on 429 with Retry-After header."""
        writer = ReadwiseHighlightWriter("test-key")

        rate_limited_response = Mock()
        rate_limited_response.status_code = 429
        rate_limited_response.headers = {"Retry-After": "5"}

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = [{"id": 2}]
        success_response.raise_for_status = Mock()

        writer.session.post = Mock(
            side_effect=[rate_limited_response, success_response]
        )

        result = writer._post_highlights({"highlights": [{"text": "test"}]})
        assert result == [{"id": 2}]
        mock_sleep.assert_called_with(5)

    @patch("time.sleep")
    def test_post_highlights_timeout_retry(self, mock_sleep):
        """Test 7: Retry on timeout with exponential backoff."""
        writer = ReadwiseHighlightWriter("test-key")

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = [{"id": 3}]
        success_response.raise_for_status = Mock()

        import requests as req

        writer.session.post = Mock(
            side_effect=[req.exceptions.Timeout("timeout"), success_response]
        )

        result = writer._post_highlights({"highlights": [{"text": "test"}]})
        assert result == [{"id": 3}]
        mock_sleep.assert_called_once_with(1)  # 2^0 = 1

    @patch.object(ReadwiseHighlightWriter, "_post_highlights")
    def test_create_highlights_no_context(self, mock_post):
        """Test: Highlights without context omit note field."""
        mock_post.return_value = [{"id": 1}]

        writer = ReadwiseHighlightWriter("test-key")
        snippet = ExtractedSnippet(text="Test text", context="", position="intro")
        result = writer.create_highlights(
            snippets=[snippet],
            title="Title",
            author="Author",
            source_url="https://example.com",
        )

        payload = mock_post.call_args[0][0]
        assert "note" not in payload["highlights"][0]


# ============================================================================
# Test 8-15: embed_snippets
# ============================================================================


class TestEmbedSnippets:
    """Tests for embed_snippets function."""

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_single_snippet(self, mock_embed, mock_write, mock_source):
        """Test 8: Single snippet embedding with correct metadata."""
        mock_embed.return_value = [0.1] * 768
        mock_write.return_value = True

        snippets = [_make_snippet()]
        result = embed_snippets(
            snippets=snippets,
            title="Feature Flags",
            author="Jane",
            source_url="https://example.com",
            reader_doc_id="doc_123",
        )

        assert result["embedded"] == 1
        assert result["chunk_ids"] == ["auto_snippet_doc_123_0"]
        assert result["source_id"] is not None

        # Verify embedding call
        mock_embed.assert_called_once()
        embed_text = mock_embed.call_args[0][0]
        assert "Feature Flags" in embed_text
        assert "Teams adopting feature flags" in embed_text

        # Verify write_to_firestore call
        mock_write.assert_called_once()
        call_kwargs = mock_write.call_args[1]
        metadata = call_kwargs["metadata"]
        assert metadata["chunk_id"] == "auto_snippet_doc_123_0"
        assert metadata["parent_doc_id"] == "doc_123"
        assert metadata["source"] == "reader"
        assert metadata["source_type"] == "auto-snippet"
        assert "auto-snippet" in metadata["tags"]

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_multiple_snippets(self, mock_embed, mock_write, mock_source):
        """Test 9: Multiple snippets get sequential chunk IDs."""
        mock_embed.return_value = [0.1] * 768
        mock_write.return_value = True

        snippets = _make_snippets(5)
        result = embed_snippets(
            snippets=snippets,
            title="Article",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_456",
        )

        assert result["embedded"] == 5
        assert len(result["chunk_ids"]) == 5
        assert result["chunk_ids"][0] == "auto_snippet_doc_456_0"
        assert result["chunk_ids"][4] == "auto_snippet_doc_456_4"

        assert mock_embed.call_count == 5
        assert mock_write.call_count == 5

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_empty_snippets(self, mock_embed, mock_write, mock_source):
        """Test 10: Empty snippets list returns zeros."""
        result = embed_snippets(
            snippets=[],
            title="Title",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_789",
        )

        assert result == {"embedded": 0, "chunk_ids": [], "source_id": None}
        mock_embed.assert_not_called()
        mock_write.assert_not_called()

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_with_custom_tags(self, mock_embed, mock_write, mock_source):
        """Test 11: Custom tags are included alongside auto-snippet tag."""
        mock_embed.return_value = [0.1] * 768
        mock_write.return_value = True

        snippets = [_make_snippet()]
        result = embed_snippets(
            snippets=snippets,
            title="Title",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_123",
            tags=["kx-auto", "tech"],
        )

        metadata = mock_write.call_args[1]["metadata"]
        assert "kx-auto" in metadata["tags"]
        assert "tech" in metadata["tags"]
        assert "auto-snippet" in metadata["tags"]

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_content_format(self, mock_embed, mock_write, mock_source):
        """Test 12: Content is formatted as markdown blockquote."""
        mock_embed.return_value = [0.1] * 768
        mock_write.return_value = True

        snippet = _make_snippet(
            text="The insight text.",
            context="It explains something important.",
        )
        embed_snippets(
            snippets=[snippet],
            title="Title",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_123",
        )

        content = mock_write.call_args[1]["content"]
        assert content == "> The insight text.\n\n**Context:** It explains something important."

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_one_fails_others_continue(self, mock_embed, mock_write, mock_source):
        """Test 13: If one embedding fails, continue with the rest."""
        mock_embed.side_effect = [
            [0.1] * 768,
            Exception("Embedding API error"),
            [0.3] * 768,
        ]
        mock_write.return_value = True

        snippets = _make_snippets(3)
        result = embed_snippets(
            snippets=snippets,
            title="Title",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_123",
        )

        assert result["embedded"] == 2
        assert len(result["chunk_ids"]) == 2
        assert "auto_snippet_doc_123_0" in result["chunk_ids"]
        assert "auto_snippet_doc_123_2" in result["chunk_ids"]

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_firestore_write_fails(self, mock_embed, mock_write, mock_source):
        """Test 14: Firestore write failure skips that snippet."""
        mock_embed.return_value = [0.1] * 768
        mock_write.side_effect = [True, False, True]

        snippets = _make_snippets(3)
        result = embed_snippets(
            snippets=snippets,
            title="Title",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_123",
        )

        assert result["embedded"] == 2
        assert len(result["chunk_ids"]) == 2

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_content_hash(self, mock_embed, mock_write, mock_source):
        """Test 15: Content hash is computed correctly."""
        mock_embed.return_value = [0.1] * 768
        mock_write.return_value = True

        snippet = _make_snippet(text="Test text", context="Context")
        embed_snippets(
            snippets=[snippet],
            title="Title",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_123",
        )

        content = "> Test text\n\n**Context:** Context"
        expected_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
        actual_hash = mock_write.call_args[1]["content_hash"]
        assert actual_hash == expected_hash


# ============================================================================
# Test 16-21: process_document
# ============================================================================


class TestProcessDocument:
    """Tests for process_document orchestration."""

    @patch("ingest.readwise_writer.match_chunks_to_problems")
    @patch("ingest.readwise_writer.embed_snippets")
    @patch("ingest.readwise_writer.ReadwiseHighlightWriter")
    @patch("ingest.readwise_writer.extract_snippets")
    def test_full_pipeline(self, mock_extract, mock_writer_cls, mock_embed, mock_match):
        """Test 16: Full pipeline executes all steps."""
        snippets = _make_snippets(3)
        mock_extract.return_value = snippets

        mock_writer = MagicMock()
        mock_writer.create_highlights.return_value = {
            "created": 3,
            "failed": 0,
            "highlight_ids": [1, 2, 3],
        }
        mock_writer_cls.return_value = mock_writer

        mock_embed.return_value = {
            "embedded": 3,
            "chunk_ids": ["c1", "c2", "c3"],
            "source_id": "feature-flags",
        }

        mock_match.return_value = {"matches_found": 2}

        doc = _make_reader_doc()
        result = process_document(doc, api_key="test-key")

        assert result["snippets_extracted"] == 3
        assert result["highlights_created"] == 3
        assert result["chunks_embedded"] == 3
        assert result["problem_matches"] == 2

        mock_extract.assert_called_once()
        mock_writer.create_highlights.assert_called_once()
        mock_embed.assert_called_once()
        mock_match.assert_called_once_with(["c1", "c2", "c3"])

    @patch("ingest.readwise_writer.embed_snippets")
    @patch("ingest.readwise_writer.extract_snippets")
    def test_skip_readwise_write(self, mock_extract, mock_embed):
        """Test 17: write_to_readwise=False skips Readwise step."""
        mock_extract.return_value = _make_snippets(2)
        mock_embed.return_value = {
            "embedded": 2,
            "chunk_ids": ["c1", "c2"],
            "source_id": "s1",
        }

        doc = _make_reader_doc()
        with patch("ingest.readwise_writer.match_chunks_to_problems") as mock_match:
            mock_match.return_value = {"matches_found": 0}
            result = process_document(doc, api_key="key", write_to_readwise=False)

        assert result["snippets_extracted"] == 2
        assert result["highlights_created"] == 0
        assert result["chunks_embedded"] == 2

    @patch("ingest.readwise_writer.embed_snippets")
    @patch("ingest.readwise_writer.ReadwiseHighlightWriter")
    @patch("ingest.readwise_writer.extract_snippets")
    def test_readwise_failure_still_embeds(self, mock_extract, mock_writer_cls, mock_embed):
        """Test 18: Readwise failure doesn't block embedding."""
        mock_extract.return_value = _make_snippets(2)

        mock_writer = MagicMock()
        mock_writer.create_highlights.side_effect = Exception("Readwise down")
        mock_writer_cls.return_value = mock_writer

        mock_embed.return_value = {
            "embedded": 2,
            "chunk_ids": ["c1", "c2"],
            "source_id": "s1",
        }

        doc = _make_reader_doc()
        with patch("ingest.readwise_writer.match_chunks_to_problems") as mock_match:
            mock_match.return_value = {"matches_found": 0}
            result = process_document(doc, api_key="key")

        assert result["highlights_created"] == 0
        assert result["chunks_embedded"] == 2
        mock_embed.assert_called_once()

    @patch("ingest.readwise_writer.extract_snippets")
    def test_extraction_failure(self, mock_extract):
        """Test 19: Extraction failure returns early with zeros."""
        mock_extract.side_effect = Exception("LLM unavailable")

        doc = _make_reader_doc()
        result = process_document(doc, api_key="key")

        assert result["snippets_extracted"] == 0
        assert result["highlights_created"] == 0
        assert result["chunks_embedded"] == 0
        assert result["problem_matches"] == 0

    @patch("ingest.readwise_writer.extract_snippets")
    def test_no_snippets_extracted(self, mock_extract):
        """Test 20: No snippets returns early."""
        mock_extract.return_value = []

        doc = _make_reader_doc()
        result = process_document(doc, api_key="key")

        assert result["snippets_extracted"] == 0
        assert result["highlights_created"] == 0

    @patch("ingest.readwise_writer.match_chunks_to_problems")
    @patch("ingest.readwise_writer.embed_snippets")
    @patch("ingest.readwise_writer.extract_snippets")
    def test_embedding_failure_skips_problem_match(
        self, mock_extract, mock_embed, mock_match
    ):
        """Test 21: Embedding failure means no chunk_ids for problem matching."""
        mock_extract.return_value = _make_snippets(2)
        mock_embed.side_effect = Exception("Embedding service down")

        doc = _make_reader_doc()
        result = process_document(doc, api_key="key", write_to_readwise=False)

        assert result["snippets_extracted"] == 2
        assert result["chunks_embedded"] == 0
        mock_match.assert_not_called()


# ============================================================================
# Test 22-25: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @patch("ingest.readwise_writer.match_chunks_to_problems")
    @patch("ingest.readwise_writer.embed_snippets")
    @patch("ingest.readwise_writer.ReadwiseHighlightWriter")
    @patch("ingest.readwise_writer.extract_snippets")
    def test_no_source_url_skips_readwise(
        self, mock_extract, mock_writer_cls, mock_embed, mock_match
    ):
        """Test 22: No source_url skips Readwise write even if enabled."""
        mock_extract.return_value = _make_snippets(1)
        mock_embed.return_value = {
            "embedded": 1,
            "chunk_ids": ["c1"],
            "source_id": "s1",
        }
        mock_match.return_value = {"matches_found": 0}

        doc = _make_reader_doc(source_url=None)
        result = process_document(doc, api_key="key", write_to_readwise=True)

        assert result["highlights_created"] == 0
        mock_writer_cls.assert_not_called()
        assert result["chunks_embedded"] == 1

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_auto_snippet_tag_not_duplicated(self, mock_embed, mock_write, mock_source):
        """Test 23: auto-snippet tag is not duplicated when already present."""
        mock_embed.return_value = [0.1] * 768
        mock_write.return_value = True

        embed_snippets(
            snippets=[_make_snippet()],
            title="Title",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_123",
            tags=["auto-snippet", "other"],
        )

        metadata = mock_write.call_args[1]["metadata"]
        tag_count = metadata["tags"].count("auto-snippet")
        assert tag_count == 1

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_run_id_format(self, mock_embed, mock_write, mock_source):
        """Test 24: Run ID follows expected format."""
        mock_embed.return_value = [0.1] * 768
        mock_write.return_value = True

        embed_snippets(
            snippets=[_make_snippet()],
            title="Title",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_abc",
        )

        run_id = mock_write.call_args[1]["run_id"]
        assert run_id == "auto_ingest_doc_abc"

    @patch("ingest.readwise_writer.match_chunks_to_problems")
    @patch("ingest.readwise_writer.embed_snippets")
    @patch("ingest.readwise_writer.extract_snippets")
    def test_problem_match_failure_nonblocking(
        self, mock_extract, mock_embed, mock_match
    ):
        """Test 25: Problem matching failure doesn't affect result."""
        mock_extract.return_value = _make_snippets(2)
        mock_embed.return_value = {
            "embedded": 2,
            "chunk_ids": ["c1", "c2"],
            "source_id": "s1",
        }
        mock_match.side_effect = Exception("Firestore down")

        doc = _make_reader_doc()
        result = process_document(doc, api_key="key", write_to_readwise=False)

        assert result["snippets_extracted"] == 2
        assert result["chunks_embedded"] == 2
        assert result["problem_matches"] == 0

    @patch("ingest.readwise_writer._ensure_source_exists")
    @patch("ingest.readwise_writer.write_to_firestore")
    @patch("ingest.readwise_writer.generate_embedding")
    def test_embed_no_tags(self, mock_embed, mock_write, mock_source):
        """Test: tags=None still adds auto-snippet tag."""
        mock_embed.return_value = [0.1] * 768
        mock_write.return_value = True

        embed_snippets(
            snippets=[_make_snippet()],
            title="Title",
            author="Author",
            source_url="https://example.com",
            reader_doc_id="doc_123",
            tags=None,
        )

        metadata = mock_write.call_args[1]["metadata"]
        assert metadata["tags"] == ["auto-snippet"]

    @patch("time.sleep")
    def test_post_highlights_max_retries_exceeded(self, mock_sleep):
        """Test: Max retries raises after exhausting attempts."""
        writer = ReadwiseHighlightWriter("test-key")

        import requests as req

        writer.session.post = Mock(
            side_effect=req.exceptions.Timeout("timeout")
        )

        with pytest.raises(req.exceptions.Timeout):
            writer._post_highlights({"highlights": [{"text": "test"}]})

        assert writer.session.post.call_count == 3

    @patch("ingest.readwise_writer.match_chunks_to_problems")
    @patch("ingest.readwise_writer.embed_snippets")
    @patch("ingest.readwise_writer.extract_snippets")
    def test_process_doc_with_none_author(self, mock_extract, mock_embed, mock_match):
        """Test: None author defaults to 'Unknown'."""
        mock_extract.return_value = _make_snippets(1)
        mock_embed.return_value = {
            "embedded": 1,
            "chunk_ids": ["c1"],
            "source_id": "s1",
        }
        mock_match.return_value = {"matches_found": 0}

        doc = _make_reader_doc(author=None)
        result = process_document(doc, api_key="key", write_to_readwise=False)

        # Verify extract_snippets was called with "Unknown" author
        call_kwargs = mock_extract.call_args[1]
        assert call_kwargs["author"] == "Unknown"
        assert result["chunks_embedded"] == 1
