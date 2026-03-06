"""
Tests for Epic 15: Newsletter Generation Pipeline.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.newsletter.models import (
    CuratedSource,
    CurationResult,
    HotNewsItem,
    NewsletterDraft,
)
from src.newsletter.curation_agent import (
    _fallback_curation,
    _format_sources_for_agent,
    _get_source_summary,
    _parse_curation_result,
    run_curation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_source(
    source_id="src-1",
    title="Test Article",
    source_type="article",
    source_url="https://example.com/article",
    readwise_url="https://readwise.io/bookreview/123",
    knowledge_card_summary="A key insight from this article.",
):
    return {
        "source_id": source_id,
        "title": title,
        "type": source_type,
        "source_url": source_url,
        "readwise_url": readwise_url,
        "chunks": [
            {
                "chunk_id": "chunk-1",
                "knowledge_card": {
                    "summary": knowledge_card_summary,
                    "takeaways": ["Key takeaway"],
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestModels:
    def test_curated_source_model(self):
        src = CuratedSource(
            title="Test",
            url="https://example.com",
            source_type="article",
            summary="A summary",
        )
        assert src.title == "Test"
        assert src.reason == ""  # default

    def test_hot_news_item_model(self):
        item = HotNewsItem(
            title="Big AI News",
            url="https://news.example.com",
            summary="Something happened",
        )
        assert item.title == "Big AI News"

    def test_curation_result_model(self):
        result = CurationResult(
            filtered_sources=[
                CuratedSource(title="T", url="u", source_type="article", summary="s")
            ],
            hot_news=[],
        )
        assert len(result.filtered_sources) == 1
        assert result.curator_notes == ""

    def test_newsletter_draft_model(self):
        draft = NewsletterDraft(
            html="<html/>",
            plain_text="text",
            subject="Weekly Tech",
            curated_sources=[],
            hot_news=[],
            created_at="2026-03-06T10:00:00Z",
            period_start="2026-02-28",
            period_end="2026-03-06",
        )
        assert draft.dry_run is True
        assert draft.gcs_url == ""


# ---------------------------------------------------------------------------
# Curation Agent Tests
# ---------------------------------------------------------------------------

class TestCurationAgent:
    def test_fallback_curation_returns_all_sources(self):
        sources = [_make_source("src-1", "Article 1"), _make_source("src-2", "Article 2")]
        result = _fallback_curation(sources)
        assert isinstance(result, CurationResult)
        assert len(result.filtered_sources) == 2
        assert result.hot_news == []

    def test_format_sources_for_agent(self):
        sources = [_make_source()]
        json_str = _format_sources_for_agent(sources)
        data = json.loads(json_str)
        assert len(data) == 1
        assert data[0]["title"] == "Test Article"
        assert data[0]["source_type"] == "article"

    def test_get_source_summary_with_knowledge_card(self):
        src = _make_source(knowledge_card_summary="Important insight")
        summary = _get_source_summary(src)
        assert "Important insight" in summary

    def test_get_source_summary_no_chunks(self):
        src = {"source_id": "x", "chunks": []}
        assert _get_source_summary(src) == ""

    def test_parse_curation_result_valid_json(self):
        sources = [_make_source()]
        valid_json = json.dumps({
            "filtered_sources": [
                {
                    "title": "Curated Article",
                    "url": "https://example.com",
                    "source_type": "article",
                    "summary": "A curated summary",
                    "reason": "High relevance",
                }
            ],
            "hot_news": [
                {
                    "title": "AI News",
                    "url": "https://news.example.com",
                    "summary": "Something happened in AI",
                }
            ],
            "curator_notes": "Good week",
        })
        result = _parse_curation_result(valid_json, sources)
        assert isinstance(result, CurationResult)
        assert len(result.filtered_sources) == 1
        assert result.filtered_sources[0].title == "Curated Article"
        assert len(result.hot_news) == 1
        assert result.curator_notes == "Good week"

    def test_parse_curation_result_invalid_text_uses_fallback(self):
        sources = [_make_source()]
        result = _parse_curation_result("This is not JSON at all.", sources)
        assert isinstance(result, CurationResult)
        assert len(result.filtered_sources) == len(sources)  # fallback = all sources
        assert result.hot_news == []

    def test_run_curation_no_agent_id_uses_fallback(self):
        sources = [_make_source()]
        with patch.dict("os.environ", {}, clear=False):
            # Remove agent ID if set
            import os
            os.environ.pop("NEWSLETTER_AGENT_ENGINE_ID", None)
            result = run_curation(sources)
        assert isinstance(result, CurationResult)
        assert len(result.filtered_sources) == len(sources)

    def test_run_curation_agent_exception_uses_fallback(self):
        sources = [_make_source()]
        mock_vertexai = MagicMock()
        mock_agent_engines = MagicMock()
        mock_agent_engines.get.side_effect = Exception("Agent not found")
        mock_vertexai.agent_engines = mock_agent_engines

        with patch.dict("os.environ", {"NEWSLETTER_AGENT_ENGINE_ID": "projects/x/y/z"}):
            with patch.dict("sys.modules", {
                "vertexai": mock_vertexai,
                "vertexai.agent_engines": mock_agent_engines,
            }):
                result = run_curation(sources)
        # Should return fallback
        assert isinstance(result, CurationResult)


# ---------------------------------------------------------------------------
# Newsletter Generator Tests (mocked LLM)
# ---------------------------------------------------------------------------

class TestNewsletterGenerator:
    @pytest.fixture(autouse=True)
    def _init_generator_mocks(self):
        """Ensure lazy imports are initialized so patch targets exist."""
        import src.newsletter.generator as gen
        if gen._get_client is None:
            gen._get_client = lambda model: None
            gen._GenerationConfig = type("GenerationConfig", (), {})

    def test_generate_newsletter_returns_required_keys(self):
        from src.newsletter.generator import generate_newsletter

        curation_result = CurationResult(
            filtered_sources=[
                CuratedSource(
                    title="Test Article",
                    url="https://example.com",
                    source_type="article",
                    summary="An important insight",
                )
            ],
            hot_news=[
                HotNewsItem(
                    title="AI Release",
                    url="https://ai.example.com",
                    summary="New model released",
                )
            ],
        )
        period = {"start": "2026-02-28", "end": "2026-03-06"}

        mock_response = MagicMock()
        mock_response.text = "## What I've Been Reading\n\nGreat reads this week.\n\n## Key Takeaway\n\nImportant insight."
        mock_response.input_tokens = 100
        mock_response.output_tokens = 200

        mock_client = MagicMock()
        mock_client.generate.return_value = mock_response

        with patch("src.newsletter.generator._get_client", return_value=mock_client):
            with patch("src.newsletter.generator._GenerationConfig"):
                result = generate_newsletter(curation_result, period)

        assert "html" in result
        assert "plain_text" in result
        assert "subject" in result
        assert "Tech Reads" in result["subject"]
        assert len(result["html"]) > 0

    def test_generate_newsletter_html_contains_structure(self):
        from src.newsletter.generator import generate_newsletter

        curation_result = CurationResult(filtered_sources=[], hot_news=[])
        period = {"start": "2026-02-28", "end": "2026-03-06"}

        mock_response = MagicMock()
        mock_response.text = "## Reading\n\nSome content.\n\n## Takeaway\n\nLesson learned."

        mock_client = MagicMock()
        mock_client.generate.return_value = mock_response

        with patch("src.newsletter.generator._get_client", return_value=mock_client):
            with patch("src.newsletter.generator._GenerationConfig"):
                result = generate_newsletter(curation_result, period)

        assert "<!DOCTYPE html>" in result["html"]
        assert "<title>" in result["html"]
        assert "Tech Reads" in result["html"]


# ---------------------------------------------------------------------------
# Main Cloud Function Tests
# ---------------------------------------------------------------------------

class TestNewsletterMain:
    def test_main_returns_disabled_when_config_disabled(self):
        from src.newsletter.main import generate_newsletter_cf

        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        with patch("src.newsletter.main._load_config", return_value={"enabled": False}):
            result = generate_newsletter_cf(mock_request)

        assert result["status"] == "disabled"

    def test_main_returns_success_with_mocked_pipeline(self):
        from src.newsletter.main import generate_newsletter_cf

        mock_request = MagicMock()
        mock_request.get_json.return_value = {"dry_run": True}

        mock_sources = [_make_source()]
        mock_curation = CurationResult(
            filtered_sources=[
                CuratedSource(title="T", url="u", source_type="article", summary="s")
            ],
            hot_news=[],
        )
        mock_newsletter = {
            "html": "<html>Newsletter</html>",
            "plain_text": "Newsletter text",
            "subject": "Tech Reads: Mar 1\u20136, 2026",
        }

        with patch("src.newsletter.main._load_config", return_value={
            "enabled": True, "days": 7, "limit": 50, "dry_run": True, "deliver_to_reader": False
        }):
            with patch("src.newsletter.main._fetch_recent_sources", return_value=mock_sources):
                with patch("src.newsletter.main.run_curation", return_value=mock_curation):
                    with patch("src.newsletter.main.generate_newsletter", return_value=mock_newsletter):
                        with patch("src.newsletter.main._upload_to_gcs", return_value="https://gcs.example.com/newsletter.html"):
                            with patch("src.newsletter.main._save_draft", return_value="draft-123"):
                                result = generate_newsletter_cf(mock_request)

        assert result["status"] == "success"
        assert result["draft_id"] == "draft-123"
        assert result["dry_run"] is True

    def test_main_handles_no_sources(self):
        from src.newsletter.main import generate_newsletter_cf

        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        with patch("src.newsletter.main._load_config", return_value={
            "enabled": True, "days": 7, "limit": 50, "dry_run": True, "deliver_to_reader": False
        }):
            with patch("src.newsletter.main._fetch_recent_sources", return_value=[]):
                result = generate_newsletter_cf(mock_request)

        assert result["status"] == "success"
        assert "No sources" in result["message"]
