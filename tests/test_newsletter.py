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
from src.newsletter.generator import _build_generator_prompt


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
        assert src.author == ""  # default

    def test_curated_source_model_with_author(self):
        src = CuratedSource(
            title="Test",
            url="https://example.com",
            source_type="article",
            summary="A summary",
            author="Simon Willison",
        )
        assert src.author == "Simon Willison"

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
        import os
        os.environ.pop("NEWSLETTER_AGENT_ENGINE_ID", None)
        mock_sm = MagicMock()
        mock_sm.SecretManagerServiceClient.side_effect = Exception("no secret manager")
        with patch.dict("sys.modules", {"google.cloud.secretmanager": mock_sm}):
            with patch("src.newsletter.curation_agent._batch_resolve_missing_urls", return_value={}):
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
        assert "Christian's View" in result["subject"]
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
        assert "Christian's View" in result["html"]


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
            with patch("src.newsletter.main._fetch_recent_sources", return_value=(mock_sources, {})):
                with patch("src.newsletter.main._fetch_relationships", return_value=[]):
                    with patch("src.newsletter.main._fetch_previous_newsletter", return_value=None):
                        with patch("src.newsletter.main.run_curation", return_value=mock_curation):
                            with patch("src.newsletter.main.generate_newsletter", return_value=mock_newsletter):
                                with patch("src.newsletter.main._upload_to_gcs", return_value="https://gcs.example.com/newsletter.html"):
                                    with patch("src.newsletter.main._save_draft", return_value="draft-123"):
                                        result = generate_newsletter_cf(mock_request)

        assert result["status"] == "success"
        assert result["draft_id"] == "draft-123"
        assert result["dry_run"] is True

    def test_main_includes_image_url_on_success(self):
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
        subject = "Tech Reads: Mar 1\u20136, 2026"
        mock_newsletter = {
            "html": f"<!DOCTYPE html><h1>{subject}</h1><p>Content</p>",
            "plain_text": "Newsletter text",
            "subject": subject,
        }

        with patch("src.newsletter.main._load_config", return_value={
            "enabled": True, "days": 7, "limit": 50, "dry_run": True, "deliver_to_reader": False
        }):
            with patch("src.newsletter.main._fetch_recent_sources", return_value=(mock_sources, {})):
                with patch("src.newsletter.main._fetch_relationships", return_value=[]):
                    with patch("src.newsletter.main._fetch_previous_newsletter", return_value=None):
                        with patch("src.newsletter.main.run_curation", return_value=mock_curation):
                            with patch("src.newsletter.main.generate_newsletter", return_value=mock_newsletter):
                                with patch("src.newsletter.main.extract_themes", return_value="tech themed prompt"):
                                    with patch("src.newsletter.main.generate_cover_image", return_value=b"PNG_BYTES"):
                                        with patch("src.newsletter.main.upload_image_to_gcs", return_value="https://storage.googleapis.com/kx-hub-content/newsletter/images/cover.png"):
                                            with patch("src.newsletter.main._upload_to_gcs", return_value="https://gcs.example.com/newsletter.html"):
                                                with patch("src.newsletter.main._save_draft", return_value="draft-456") as mock_save:
                                                    result = generate_newsletter_cf(mock_request)

        assert result["status"] == "success"
        assert result["image_url"] == "https://storage.googleapis.com/kx-hub-content/newsletter/images/cover.png"
        # Verify draft was saved with image_url and html containing img tag
        saved_draft = mock_save.call_args[0][0]
        assert saved_draft.image_url == "https://storage.googleapis.com/kx-hub-content/newsletter/images/cover.png"
        assert '<img src="https://storage.googleapis.com/kx-hub-content/newsletter/images/cover.png"' in saved_draft.html
        assert f'<h1>{subject}</h1>' in saved_draft.html

    def test_main_cover_image_failure_is_nonfatal(self):
        from src.newsletter.main import generate_newsletter_cf

        mock_request = MagicMock()
        mock_request.get_json.return_value = {"dry_run": True}

        mock_sources = [_make_source()]
        mock_curation = CurationResult(
            filtered_sources=[CuratedSource(title="T", url="u", source_type="article", summary="s")],
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
            with patch("src.newsletter.main._fetch_recent_sources", return_value=(mock_sources, {})):
                with patch("src.newsletter.main._fetch_relationships", return_value=[]):
                    with patch("src.newsletter.main._fetch_previous_newsletter", return_value=None):
                        with patch("src.newsletter.main.run_curation", return_value=mock_curation):
                            with patch("src.newsletter.main.generate_newsletter", return_value=mock_newsletter):
                                with patch("src.newsletter.main.extract_themes", side_effect=Exception("Vertex AI unavailable")):
                                    with patch("src.newsletter.main._upload_to_gcs", return_value="https://gcs.example.com/newsletter.html"):
                                        with patch("src.newsletter.main._save_draft", return_value="draft-789") as mock_save:
                                            result = generate_newsletter_cf(mock_request)

        assert result["status"] == "success"
        assert result["image_url"] == ""
        saved_draft = mock_save.call_args[0][0]
        assert saved_draft.image_url == ""
        assert saved_draft.html == "<html>Newsletter</html>"

    def test_main_handles_no_sources(self):
        from src.newsletter.main import generate_newsletter_cf

        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        with patch("src.newsletter.main._load_config", return_value={
            "enabled": True, "days": 7, "limit": 50, "dry_run": True, "deliver_to_reader": False
        }):
            with patch("src.newsletter.main._fetch_recent_sources", return_value=([], {})):
                result = generate_newsletter_cf(mock_request)

        assert result["status"] == "success"
        assert "No sources" in result["message"]

    def test_main_skip_image_skips_cover_generation(self):
        """skip_image=true should bypass cover image generation entirely."""
        from src.newsletter.main import generate_newsletter_cf

        mock_request = MagicMock()
        mock_request.get_json.return_value = {"dry_run": True, "skip_image": True}

        mock_sources = [_make_source()]
        mock_curation = CurationResult(
            filtered_sources=[CuratedSource(title="T", url="u", source_type="article", summary="s")],
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
            with patch("src.newsletter.main._fetch_recent_sources", return_value=(mock_sources, {})):
                with patch("src.newsletter.main._fetch_relationships", return_value=[]):
                    with patch("src.newsletter.main._fetch_previous_newsletter", return_value=None):
                        with patch("src.newsletter.main.run_curation", return_value=mock_curation):
                            with patch("src.newsletter.main.generate_newsletter", return_value=mock_newsletter):
                                with patch("src.newsletter.main.extract_themes") as mock_themes:
                                    with patch("src.newsletter.main._upload_to_gcs", return_value=""):
                                        with patch("src.newsletter.main._save_draft", return_value="draft-skip"):
                                            result = generate_newsletter_cf(mock_request)

        assert result["status"] == "success"
        assert result["image_url"] == ""
        mock_themes.assert_not_called()

    def test_main_passes_previous_issue_to_generator(self):
        """generate_newsletter should receive previous_issue from Firestore."""
        from src.newsletter.main import generate_newsletter_cf

        mock_request = MagicMock()
        mock_request.get_json.return_value = {"dry_run": True, "skip_image": True}

        mock_sources = [_make_source()]
        mock_curation = CurationResult(
            filtered_sources=[CuratedSource(title="T", url="u", source_type="article", summary="s")],
            hot_news=[],
        )
        mock_newsletter = {
            "html": "<html>Newsletter</html>",
            "plain_text": "Newsletter text",
            "subject": "Tech Reads: Mar 1\u20136, 2026",
        }
        prev_issue = {"subject": "Tech Reads: Feb 22\u201328, 2026", "period_start": "2026-02-22", "period_end": "2026-02-28"}

        with patch("src.newsletter.main._load_config", return_value={
            "enabled": True, "days": 7, "limit": 50, "dry_run": True, "deliver_to_reader": False
        }):
            with patch("src.newsletter.main._fetch_recent_sources", return_value=(mock_sources, {})):
                with patch("src.newsletter.main._fetch_relationships", return_value=[]):
                    with patch("src.newsletter.main._fetch_previous_newsletter", return_value=prev_issue):
                        with patch("src.newsletter.main.run_curation", return_value=mock_curation):
                            with patch("src.newsletter.main.generate_newsletter", return_value=mock_newsletter) as mock_gen:
                                with patch("src.newsletter.main._upload_to_gcs", return_value=""):
                                    with patch("src.newsletter.main._save_draft", return_value="draft-prev"):
                                        result = generate_newsletter_cf(mock_request)

        assert result["status"] == "success"
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["previous_issue"] == prev_issue


# ---------------------------------------------------------------------------
# Generator Prompt Tests
# ---------------------------------------------------------------------------

class TestGeneratorPrompt:
    def _make_curation(self, sources=None, hot_news=None):
        return CurationResult(
            filtered_sources=sources or [
                CuratedSource(title="AI Article", url="https://ai.example.com", source_type="article", summary="About LLMs", author="Andrej Karpathy"),
                CuratedSource(title="Arch Guide", url="https://se.example.com", source_type="article", summary="Software patterns"),
                CuratedSource(title="Leadership", url="https://biz.example.com", source_type="article", summary="Business leadership"),
            ],
            hot_news=hot_news or [],
        )

    def test_prompt_includes_previous_issue(self):
        curation = self._make_curation()
        prev = {"subject": "Tech Reads: Feb 22\u201328, 2026", "period_start": "2026-02-22", "period_end": "2026-02-28"}
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        prompt = _build_generator_prompt(curation, period, [], previous_issue=prev)
        assert "=== PREVIOUS ISSUE ===" in prompt
        assert "Tech Reads: Feb 22" in prompt

    def test_prompt_omits_previous_issue_when_none(self):
        curation = self._make_curation()
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        prompt = _build_generator_prompt(curation, period, [], previous_issue=None)
        assert "=== PREVIOUS ISSUE ===" not in prompt

    def test_prompt_includes_hot_news_section(self):
        hot_news = [HotNewsItem(title="GPT-5 Released", url="https://openai.com", summary="New model")]
        curation = self._make_curation(hot_news=hot_news)
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        prompt = _build_generator_prompt(curation, period, [])
        assert "=== HOT NEWS" in prompt
        assert "GPT-5 Released" in prompt

    def test_prompt_skips_hot_news_when_empty(self):
        curation = self._make_curation(hot_news=[])
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        prompt = _build_generator_prompt(curation, period, [])
        assert "=== HOT NEWS" not in prompt

    def test_prompt_includes_author_attribution(self):
        curation = self._make_curation()
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        prompt = _build_generator_prompt(curation, period, [])
        assert "by Andrej Karpathy" in prompt

    def test_prompt_uses_author_lookup_fallback(self):
        sources = [CuratedSource(title="T", url="https://example.com", source_type="article", summary="s")]
        curation = CurationResult(filtered_sources=sources, hot_news=[])
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        prompt = _build_generator_prompt(curation, period, [], author_lookup={"https://example.com": "Simon Willison"})
        assert "by Simon Willison" in prompt

    def test_prompt_skips_unknown_author(self):
        sources = [CuratedSource(title="T", url="https://example.com", source_type="article", summary="s", author="Unknown")]
        curation = CurationResult(filtered_sources=sources, hot_news=[])
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        prompt = _build_generator_prompt(curation, period, [])
        assert "by Unknown" not in prompt

    def test_prompt_includes_connection_links(self):
        curation = self._make_curation()
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        rels = [{
            "from_source_id": "src-1",
            "from_title": "AI Article",
            "target_title": "Arch Guide",
            "target_source_url": "https://external.example.com/arch-guide",
            "relationship_type": "extends",
            "explanation": "Both discuss scalability",
        }]
        prompt = _build_generator_prompt(
            curation, period, rels,
            source_urls={"src-1": "https://ai.example.com"},
        )
        assert "=== CONNECTIONS ===" in prompt
        assert "https://ai.example.com" in prompt
        assert "https://external.example.com/arch-guide" in prompt
        # readwise.io URLs must be filtered out of connections
        assert "readwise.io" not in prompt

    def test_prompt_contains_grouping_instructions(self):
        curation = self._make_curation()
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        prompt = _build_generator_prompt(curation, period, [])
        assert "AI & Process" in prompt
        assert "Software Engineering" in prompt
        assert "Beyond the Code" in prompt

    def test_prompt_contains_intro_instruction(self):
        curation = self._make_curation()
        period = {"start": "2026-03-01", "end": "2026-03-07"}
        prompt = _build_generator_prompt(curation, period, [])
        assert "Hi everyone" in prompt
        assert "NO section header" in prompt


# ---------------------------------------------------------------------------
# _fetch_previous_newsletter Tests
# ---------------------------------------------------------------------------

class TestFetchPreviousNewsletter:
    def test_returns_none_on_firestore_error(self):
        from src.newsletter.main import _fetch_previous_newsletter

        with patch("src.newsletter.main._get_db", side_effect=Exception("Firestore unavailable")):
            result = _fetch_previous_newsletter()

        assert result is None

    def test_returns_dict_with_expected_keys(self):
        from src.newsletter.main import _fetch_previous_newsletter

        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "subject": "Tech Reads: Feb 22\u201328, 2026",
            "period_start": "2026-02-22",
            "period_end": "2026-02-28",
            "html": "<html/>",
        }

        mock_db = MagicMock()
        mock_db.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = iter([mock_doc])

        with patch("src.newsletter.main._get_db", return_value=mock_db):
            result = _fetch_previous_newsletter()

        assert result is not None
        assert result["subject"] == "Tech Reads: Feb 22\u201328, 2026"
        assert result["period_start"] == "2026-02-22"
        assert "html" not in result  # only subject + period fields returned

    def test_returns_none_when_no_documents(self):
        from src.newsletter.main import _fetch_previous_newsletter

        mock_db = MagicMock()
        mock_db.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = iter([])

        with patch("src.newsletter.main._get_db", return_value=mock_db):
            result = _fetch_previous_newsletter()

        assert result is None
