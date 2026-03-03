"""
Tests for Summary Data Pipeline (9.1), Generator (9.2), and Delivery (9.3).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.summary.data_pipeline import (
    collect_summary_data,
    detect_source_type,
    fetch_recent_chunks,
    fetch_relationships_for_sources,
    resolve_url,
)
from src.summary.cover_image import extract_themes, generate_cover_image, upload_to_gcs
from src.summary.delivery import (
    _inline_format,
    _markdown_to_html,
    _slugify,
    deliver_to_reader,
)
from src.summary.generator import (
    _build_frontmatter,
    _build_header,
    _build_prompt,
    _relationship_type_hint,
    generate_summary as generate_summary_text,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chunk(
    chunk_id="chunk-1",
    source_id="src-1",
    title="Test Article",
    author="Jane Doe",
    category="articles",
    source_url="https://example.com/article",
    readwise_url="https://readwise.io/bookreview/123",
    highlight_url="https://readwise.io/highlight/456",
    knowledge_card=None,
):
    """Build a fake chunk dict."""
    if knowledge_card is None:
        knowledge_card = {
            "summary": f"Summary for {chunk_id}",
            "takeaways": [f"Takeaway from {chunk_id}"],
        }
    return {
        "id": chunk_id,
        "source_id": source_id,
        "title": title,
        "author": author,
        "category": category,
        "source_url": source_url,
        "readwise_url": readwise_url,
        "highlight_url": highlight_url,
        "knowledge_card": knowledge_card,
        "last_highlighted_at": datetime.now(timezone.utc),
    }


def _make_relationship(src_cid, tgt_cid, rel_type="extends", explanation="Related"):
    return {
        "source_chunk_id": src_cid,
        "target_chunk_id": tgt_cid,
        "type": rel_type,
        "explanation": explanation,
    }


def _make_pipeline_data(**overrides):
    """Build a minimal pipeline data dict for generator tests."""
    defaults = {
        "period": {"start": "2026-02-23", "end": "2026-03-02", "days": 7},
        "stats": {
            "total_chunks": 3,
            "total_sources": 2,
            "total_highlights": 3,
            "total_relationships": 1,
            "source_types": {"article": 1, "podcast": 1},
        },
        "sources": [
            {
                "source_id": "src-1",
                "title": "AI Trends",
                "author": "Alice",
                "type": "article",
                "readwise_url": "https://readwise.io/bookreview/111",
                "source_url": "https://example.com/ai",
                "chunks": [
                    {
                        "chunk_id": "c1",
                        "knowledge_card": {
                            "summary": "AI is evolving fast",
                            "takeaways": ["Agents are key"],
                        },
                        "highlight_url": "",
                    }
                ],
            },
            {
                "source_id": "src-2",
                "title": "Tech Podcast",
                "author": "Bob",
                "type": "podcast",
                "readwise_url": "",
                "source_url": "https://share.snipd.com/ep/123",
                "chunks": [
                    {
                        "chunk_id": "c2",
                        "knowledge_card": {
                            "summary": "Podcast about tech trends",
                            "takeaways": ["Listen more"],
                        },
                        "highlight_url": "",
                    }
                ],
            },
        ],
        "relationships": [
            {
                "from_source_id": "src-1",
                "from_title": "AI Trends",
                "target_source_id": "src-99",
                "target_title": "Old AI Paper",
                "target_author": "Prof X",
                "target_readwise_url": "https://readwise.io/bookreview/999",
                "target_source_url": "",
                "relationship_type": "extends",
                "explanation": "Builds on earlier work",
            }
        ],
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Source type detection
# ---------------------------------------------------------------------------

class TestDetectSourceType:
    def test_article_default(self):
        assert detect_source_type({"category": "articles"}) == "article"

    def test_book(self):
        assert detect_source_type({"category": "books"}) == "book"

    def test_podcast_snipd(self):
        chunk = {"source_url": "https://share.snipd.com/episode/abc"}
        assert detect_source_type(chunk) == "podcast"

    def test_podcast_takes_precedence_over_category(self):
        chunk = {"source_url": "https://share.snipd.com/ep", "category": "books"}
        assert detect_source_type(chunk) == "podcast"

    def test_missing_fields(self):
        assert detect_source_type({}) == "article"

    def test_none_source_url(self):
        assert detect_source_type({"source_url": None, "category": "articles"}) == "article"


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------

class TestResolveUrl:
    def test_prefers_source_url(self):
        chunk = {
            "source_url": "https://example.com",
            "readwise_url": "https://readwise.io/123",
            "highlight_url": "https://readwise.io/hl/456",
        }
        assert resolve_url(chunk) == "https://example.com"

    def test_falls_back_to_readwise(self):
        chunk = {"readwise_url": "https://readwise.io/123"}
        assert resolve_url(chunk) == "https://readwise.io/123"

    def test_falls_back_to_highlight(self):
        chunk = {"highlight_url": "https://readwise.io/hl/456"}
        assert resolve_url(chunk) == "https://readwise.io/hl/456"

    def test_empty_when_none(self):
        assert resolve_url({}) == ""

    def test_skips_none_source_url(self):
        chunk = {
            "source_url": None,
            "readwise_url": "https://readwise.io/123",
        }
        assert resolve_url(chunk) == "https://readwise.io/123"


# ---------------------------------------------------------------------------
# fetch_recent_chunks (mocked Firestore)
# ---------------------------------------------------------------------------

class TestFetchRecentChunks:
    @patch("src.summary.data_pipeline._get_db")
    def test_returns_chunks_with_ids(self, mock_get_db):
        mock_doc = MagicMock()
        mock_doc.id = "chunk-1"
        mock_doc.to_dict.return_value = {"title": "Test", "source_id": "src-1"}

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = [mock_doc]

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_query
        mock_get_db.return_value = mock_db

        result = fetch_recent_chunks(days=7, limit=50)

        assert len(result) == 1
        assert result[0]["id"] == "chunk-1"
        assert result[0]["title"] == "Test"

    @patch("src.summary.data_pipeline._get_db")
    def test_empty_result(self, mock_get_db):
        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_query
        mock_get_db.return_value = mock_db

        result = fetch_recent_chunks(days=7, limit=50)
        assert result == []


# ---------------------------------------------------------------------------
# collect_summary_data (integration-style, mocked Firestore)
# ---------------------------------------------------------------------------

class TestCollectSummaryData:
    @patch("src.summary.data_pipeline.fetch_relationships_for_sources")
    @patch("src.summary.data_pipeline.fetch_recent_chunks")
    def test_basic_grouping(self, mock_fetch, mock_rels):
        """Chunks from 2 sources are grouped correctly."""
        mock_fetch.return_value = [
            _make_chunk("c1", "src-1", title="Article A", author="Alice"),
            _make_chunk("c2", "src-1", title="Article A", author="Alice"),
            _make_chunk("c3", "src-2", title="Book B", author="Bob", category="books"),
        ]
        mock_rels.return_value = []

        result = collect_summary_data(days=7, limit=100)

        assert result["stats"]["total_chunks"] == 3
        assert result["stats"]["total_sources"] == 2
        assert result["stats"]["source_types"]["article"] == 1
        assert result["stats"]["source_types"]["book"] == 1

        titles = {s["title"] for s in result["sources"]}
        assert titles == {"Article A", "Book B"}

    @patch("src.summary.data_pipeline.fetch_relationships_for_sources")
    @patch("src.summary.data_pipeline.fetch_recent_chunks")
    def test_empty_week(self, mock_fetch, mock_rels):
        """No chunks returns empty structure with correct period."""
        mock_fetch.return_value = []
        mock_rels.return_value = []

        result = collect_summary_data(days=7, limit=100)

        assert result["stats"]["total_chunks"] == 0
        assert result["stats"]["total_sources"] == 0
        assert result["sources"] == []
        assert result["relationships"] == []
        assert result["period"]["days"] == 7

    @patch("src.summary.data_pipeline.fetch_relationships_for_sources")
    @patch("src.summary.data_pipeline.fetch_recent_chunks")
    def test_knowledge_cards_included(self, mock_fetch, mock_rels):
        """Knowledge cards are formatted in output."""
        mock_fetch.return_value = [
            _make_chunk(
                "c1",
                "src-1",
                knowledge_card={"summary": "Great article", "takeaways": ["T1", "T2"]},
            ),
        ]
        mock_rels.return_value = []

        result = collect_summary_data(days=7)
        chunk = result["sources"][0]["chunks"][0]

        assert chunk["knowledge_card"]["summary"] == "Great article"
        assert chunk["knowledge_card"]["takeaways"] == ["T1", "T2"]

    @patch("src.summary.data_pipeline.fetch_relationships_for_sources")
    @patch("src.summary.data_pipeline.fetch_recent_chunks")
    def test_missing_knowledge_card(self, mock_fetch, mock_rels):
        """Chunks without knowledge cards get empty summary/takeaways."""
        mock_fetch.return_value = [
            _make_chunk("c1", "src-1", knowledge_card=None),
        ]
        # Override to remove knowledge_card
        mock_fetch.return_value[0]["knowledge_card"] = None
        mock_rels.return_value = []

        result = collect_summary_data(days=7)
        chunk = result["sources"][0]["chunks"][0]

        assert chunk["knowledge_card"]["summary"] == ""
        assert chunk["knowledge_card"]["takeaways"] == []

    @patch("src.summary.data_pipeline.fetch_relationships_for_sources")
    @patch("src.summary.data_pipeline.fetch_recent_chunks")
    def test_source_type_counts(self, mock_fetch, mock_rels):
        """Source type counts are accurate."""
        mock_fetch.return_value = [
            _make_chunk("c1", "src-1", category="articles"),
            _make_chunk("c2", "src-2", category="books"),
            _make_chunk(
                "c3", "src-3", source_url="https://share.snipd.com/ep/1"
            ),
            _make_chunk("c4", "src-4", category="articles"),
        ]
        mock_rels.return_value = []

        result = collect_summary_data(days=7)
        types = result["stats"]["source_types"]

        assert types["article"] == 2
        assert types["book"] == 1
        assert types["podcast"] == 1

    @patch("src.summary.data_pipeline.fetch_relationships_for_sources")
    @patch("src.summary.data_pipeline.fetch_recent_chunks")
    def test_relationships_included(self, mock_fetch, mock_rels):
        """Relationships are passed through to output."""
        mock_fetch.return_value = [
            _make_chunk("c1", "src-1", title="Article A"),
        ]
        mock_rels.return_value = [
            {
                "from_source_id": "src-1",
                "target_source_id": "src-99",
                "target_title": "External Source",
                "target_author": "Someone",
                "target_readwise_url": "",
                "target_source_url": "https://example.com",
                "relationship_type": "extends",
                "explanation": "Builds on ideas",
            }
        ]

        result = collect_summary_data(days=7)

        assert result["stats"]["total_relationships"] == 1
        rel = result["relationships"][0]
        assert rel["from_title"] == "Article A"
        assert rel["target_title"] == "External Source"
        assert rel["relationship_type"] == "extends"

    @patch("src.summary.data_pipeline.fetch_relationships_for_sources")
    @patch("src.summary.data_pipeline.fetch_recent_chunks")
    def test_url_resolution_in_sources(self, mock_fetch, mock_rels):
        """Source URL is resolved using priority: source_url > readwise_url."""
        mock_fetch.return_value = [
            _make_chunk("c1", "src-1", source_url=None, readwise_url="https://rw.io/1"),
        ]
        mock_rels.return_value = []

        result = collect_summary_data(days=7)
        assert result["sources"][0]["source_url"] == "https://rw.io/1"

    @patch("src.summary.data_pipeline.fetch_relationships_for_sources")
    @patch("src.summary.data_pipeline.fetch_recent_chunks")
    def test_period_matches_params(self, mock_fetch, mock_rels):
        """Period reflects the requested days."""
        mock_fetch.return_value = []
        mock_rels.return_value = []

        result = collect_summary_data(days=14)
        assert result["period"]["days"] == 14


# ---------------------------------------------------------------------------
# fetch_relationships_for_sources (mocked Firestore)
# ---------------------------------------------------------------------------

class TestFetchRelationships:
    @patch("src.summary.data_pipeline._batch_fetch_chunks")
    @patch("src.summary.data_pipeline._get_db")
    def test_cross_source_relationships(self, mock_get_db, mock_batch):
        """Relationships between different sources are included."""
        chunks_by_source = {
            "src-1": [{"id": "c1", "source_id": "src-1"}],
        }

        # Mock relationship query
        rel_doc = MagicMock()
        rel_doc.to_dict.return_value = _make_relationship("c1", "c-ext")

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.stream.side_effect = [
            [rel_doc],  # source_chunk_id IN batch
            [],         # target_chunk_id IN batch
        ]

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_query
        mock_get_db.return_value = mock_db

        # Mock target chunk
        mock_batch.return_value = {
            "c-ext": {
                "id": "c-ext",
                "source_id": "src-ext",
                "title": "External",
                "author": "Author",
                "readwise_url": "https://rw.io/ext",
                "source_url": "https://ext.com",
            }
        }

        result = fetch_relationships_for_sources(["src-1"], chunks_by_source)

        assert len(result) == 1
        assert result[0]["from_source_id"] == "src-1"
        assert result[0]["target_source_id"] == "src-ext"
        assert result[0]["relationship_type"] == "extends"

    @patch("src.summary.data_pipeline._batch_fetch_chunks")
    @patch("src.summary.data_pipeline._get_db")
    def test_same_source_relationships_skipped(self, mock_get_db, mock_batch):
        """Relationships within the same source are filtered out."""
        chunks_by_source = {
            "src-1": [
                {"id": "c1", "source_id": "src-1"},
                {"id": "c2", "source_id": "src-1"},
            ],
        }

        rel_doc = MagicMock()
        rel_doc.to_dict.return_value = _make_relationship("c1", "c2")

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.stream.side_effect = [
            [rel_doc],  # source_chunk_id IN batch
            [],         # target_chunk_id IN batch
        ]

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_query
        mock_get_db.return_value = mock_db

        # c2 belongs to same source
        mock_batch.return_value = {
            "c2": {"id": "c2", "source_id": "src-1", "title": "Same"}
        }

        result = fetch_relationships_for_sources(["src-1"], chunks_by_source)
        assert len(result) == 0

    @patch("src.summary.data_pipeline._batch_fetch_chunks")
    @patch("src.summary.data_pipeline._get_db")
    def test_empty_chunks(self, mock_get_db, mock_batch):
        """No chunks → no relationships."""
        result = fetch_relationships_for_sources([], {})
        assert result == []

    @patch("src.summary.data_pipeline._batch_fetch_chunks")
    @patch("src.summary.data_pipeline._get_db")
    def test_deduplicates_relationships(self, mock_get_db, mock_batch):
        """Same source pair + type is deduplicated."""
        chunks_by_source = {
            "src-1": [
                {"id": "c1", "source_id": "src-1"},
                {"id": "c2", "source_id": "src-1"},
            ],
        }

        # Two relationships from src-1 to src-ext, same type
        rel1 = MagicMock()
        rel1.to_dict.return_value = _make_relationship("c1", "c-ext1")
        rel2 = MagicMock()
        rel2.to_dict.return_value = _make_relationship("c2", "c-ext2")

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.stream.side_effect = [
            [rel1, rel2],  # source_chunk_id IN batch
            [],            # target_chunk_id IN batch
        ]

        mock_db = MagicMock()
        mock_db.collection.return_value = mock_query
        mock_get_db.return_value = mock_db

        # Both targets belong to src-ext
        mock_batch.return_value = {
            "c-ext1": {"id": "c-ext1", "source_id": "src-ext", "title": "Ext", "author": "A", "readwise_url": "", "source_url": ""},
            "c-ext2": {"id": "c-ext2", "source_id": "src-ext", "title": "Ext", "author": "A", "readwise_url": "", "source_url": ""},
        }

        result = fetch_relationships_for_sources(["src-1"], chunks_by_source)
        # Should be deduplicated: same from_source, target_source, type
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Generator: Frontmatter
# ---------------------------------------------------------------------------

class TestBuildFrontmatter:
    def test_contains_tags(self):
        data = _make_pipeline_data()
        fm = _build_frontmatter(data)
        assert "ai-weekly-summary" in fm
        assert fm.startswith("---")
        assert fm.endswith("---")

    def test_stats_in_frontmatter(self):
        data = _make_pipeline_data()
        fm = _build_frontmatter(data)
        assert "sources: 2" in fm
        assert "highlights: 3" in fm
        assert "connections: 1" in fm

    def test_period_in_frontmatter(self):
        data = _make_pipeline_data()
        fm = _build_frontmatter(data)
        assert "2026-02-23 to 2026-03-02" in fm


# ---------------------------------------------------------------------------
# Generator: Header
# ---------------------------------------------------------------------------

class TestBuildHeader:
    def test_h1_with_date_range(self):
        data = _make_pipeline_data()
        header = _build_header(data)
        assert header.startswith("# Knowledge Summary:")
        assert "23. Feb" in header
        assert "2. Mär 2026" in header

    def test_highlight_count(self):
        data = _make_pipeline_data()
        header = _build_header(data)
        assert "**3 neue Highlights**" in header

    def test_source_types(self):
        data = _make_pipeline_data()
        header = _build_header(data)
        assert "1 Artikel" in header
        assert "1 🎙️ Podcast" in header

    def test_connections_count(self):
        data = _make_pipeline_data()
        header = _build_header(data)
        assert "**1 Verbindungen**" in header

    def test_no_connections_when_zero(self):
        data = _make_pipeline_data()
        data["stats"]["total_relationships"] = 0
        header = _build_header(data)
        assert "Verbindungen" not in header


# ---------------------------------------------------------------------------
# Generator: Prompt building
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_contains_sources(self):
        data = _make_pipeline_data()
        prompt = _build_prompt(data)
        assert "AI Trends" in prompt
        assert "Alice" in prompt

    def test_contains_podcast_icon(self):
        data = _make_pipeline_data()
        prompt = _build_prompt(data)
        assert "🎙️ Tech Podcast" in prompt

    def test_contains_relationships(self):
        data = _make_pipeline_data()
        prompt = _build_prompt(data)
        assert "vertieft oder erweitert" in prompt
        assert "extends" not in prompt
        assert "Old AI Paper" in prompt

    def test_contains_knowledge_cards(self):
        data = _make_pipeline_data()
        prompt = _build_prompt(data)
        assert "AI is evolving fast" in prompt
        assert "Agents are key" in prompt

    def test_contains_urls(self):
        data = _make_pipeline_data()
        prompt = _build_prompt(data)
        assert "https://readwise.io/bookreview/111" in prompt
        assert "https://share.snipd.com/ep/123" in prompt

    def test_instructions_at_end(self):
        data = _make_pipeline_data()
        prompt = _build_prompt(data)
        assert "ANWEISUNGEN" in prompt
        assert "OHNE Frontmatter" in prompt
        assert "direkt unter die H2" in prompt
        assert "**Quellen:**" in prompt
        assert "Bullet-Liste" in prompt


class TestRelationshipTypeHint:
    def test_maps_known_schema_labels(self):
        assert _relationship_type_hint("extends") == "vertieft oder erweitert"
        assert _relationship_type_hint("relates_to") == "steht inhaltlich in Beziehung zu"

    def test_falls_back_for_unknown_labels(self):
        assert _relationship_type_hint("unknown") == "steht inhaltlich in Beziehung zu"


# ---------------------------------------------------------------------------
# Generator: generate_summary
# ---------------------------------------------------------------------------

class TestGenerateSummary:
    @patch("src.summary.generator._GenerationConfig")
    @patch("src.summary.generator._get_client")
    def test_generates_full_markdown(self, mock_get_client, mock_gen_config):
        mock_response = MagicMock()
        mock_response.text = "## AI Trends\n\nSome narrative text.\n"
        mock_response.input_tokens = 1000
        mock_response.output_tokens = 500

        mock_client = MagicMock()
        mock_client.generate.return_value = mock_response
        mock_get_client.return_value = mock_client

        data = _make_pipeline_data()
        result = generate_summary_text(data)

        assert result["model"] == "gemini-3.1-pro-preview"
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 500

        md = result["markdown"]
        assert md.startswith("---")
        assert "ai-weekly-summary" in md
        assert "# Knowledge Summary:" in md
        assert "## AI Trends" in md

    def test_empty_sources_returns_empty(self):
        data = _make_pipeline_data(sources=[])
        result = generate_summary_text(data)

        assert result["markdown"] == ""
        assert result["input_tokens"] == 0

    @patch("src.summary.generator._GenerationConfig")
    @patch("src.summary.generator._get_client")
    def test_model_override(self, mock_get_client, mock_gen_config):
        mock_response = MagicMock()
        mock_response.text = "## Test\n"
        mock_response.input_tokens = 100
        mock_response.output_tokens = 50

        mock_client = MagicMock()
        mock_client.generate.return_value = mock_response
        mock_get_client.return_value = mock_client

        data = _make_pipeline_data()
        result = generate_summary_text(data, model="gemini-2.5-flash")

        assert result["model"] == "gemini-2.5-flash"
        mock_get_client.assert_called_once_with("gemini-2.5-flash")

    @patch("src.summary.generator._GenerationConfig")
    @patch("src.summary.generator._get_client")
    def test_system_prompt_passed(self, mock_get_client, mock_gen_config):
        mock_response = MagicMock()
        mock_response.text = "## Output\n"
        mock_response.input_tokens = 100
        mock_response.output_tokens = 50

        mock_client = MagicMock()
        mock_client.generate.return_value = mock_response
        mock_get_client.return_value = mock_client

        data = _make_pipeline_data()
        generate_summary_text(data)

        call_args = mock_client.generate.call_args
        assert call_args.kwargs["system_prompt"] is not None
        assert "Deutsch" in call_args.kwargs["system_prompt"]


# ---------------------------------------------------------------------------
# Delivery: Markdown to HTML
# ---------------------------------------------------------------------------

class TestMarkdownToHtml:
    def test_strips_frontmatter(self):
        md = "---\ntags:\n  - test\n---\n\n# Title\n\nContent"
        html = _markdown_to_html(md)
        assert "tags" not in html
        assert "<h1>Title</h1>" in html

    def test_headers(self):
        md = "## Section\n\n### Subsection"
        html = _markdown_to_html(md)
        assert "<h2>Section</h2>" in html
        assert "<h3>Subsection</h3>" in html

    def test_bold_and_links(self):
        md = "**Bold text** and [Link](https://example.com)"
        html = _markdown_to_html(md)
        assert "<strong>Bold text</strong>" in html
        assert '<a href="https://example.com">Link</a>' in html

    def test_blockquote(self):
        md = "> Some quote\n> continued"
        html = _markdown_to_html(md)
        assert "<blockquote>" in html
        assert "Some quote" in html

    def test_callout(self):
        md = "> [!tip] Takeaway\n> Important insight"
        html = _markdown_to_html(md)
        assert "<strong>Takeaway</strong>" in html
        assert "Important insight" in html

    def test_list_items(self):
        md = "- Item one\n- Item two"
        html = _markdown_to_html(md)
        assert "<li>Item one</li>" in html
        assert "<li>Item two</li>" in html

    def test_horizontal_rule(self):
        md = "Text\n\n---\n\nMore text"
        html = _markdown_to_html(md)
        assert "<hr>" in html

    def test_emoji_preserved(self):
        md = "🎙️ Podcast title"
        html = _markdown_to_html(md)
        assert "🎙️" in html


class TestInlineFormat:
    def test_bold(self):
        assert "<strong>test</strong>" in _inline_format("**test**")

    def test_link(self):
        result = _inline_format("[text](https://url.com)")
        assert '<a href="https://url.com">text</a>' in result

    def test_italic(self):
        assert "<em>test</em>" in _inline_format("*test*")


class TestSlugify:
    def test_basic(self):
        result = _slugify("Knowledge Summary: 23. Feb – 2. Mär 2026")
        assert "knowledge-summary" in result
        assert result.startswith("knowledge")

    def test_empty(self):
        assert _slugify("") == ""


# ---------------------------------------------------------------------------
# Delivery: deliver_to_reader
# ---------------------------------------------------------------------------

class TestDeliverToReader:
    @patch("src.summary.delivery.requests.post")
    def test_saves_to_reader(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "reader-123", "url": "https://read.readwise.io/123"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = deliver_to_reader(
            markdown="# Test\n\nContent",
            title="Knowledge Summary: Test",
            api_key="test-key",
        )

        assert result["status"] == "saved"
        assert result["reader_id"] == "reader-123"

        # Check API call
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["title"] == "Knowledge Summary: Test"
        assert "ai-weekly-summary" in payload["tags"]
        assert "kx-hub.internal" in payload["url"]  # fallback when no html_url
        assert "<h1>Test</h1>" in payload["html"]

    @patch("src.summary.delivery.requests.post")
    def test_stable_url_for_dedup(self, mock_post):
        """Same title produces same URL for Reader dedup."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "1"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        deliver_to_reader("# Test", "Same Title", "key")
        url1 = mock_post.call_args.kwargs["json"]["url"]

        deliver_to_reader("# Test 2", "Same Title", "key")
        url2 = mock_post.call_args.kwargs["json"]["url"]

        assert url1 == url2

    @patch("src.summary.delivery.requests.post")
    def test_extra_tags(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "1"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        deliver_to_reader("# Test", "Title", "key", tags=["extra-tag"])

        payload = mock_post.call_args.kwargs["json"]
        assert "ai-weekly-summary" in payload["tags"]
        assert "extra-tag" in payload["tags"]

    @patch("src.summary.delivery.requests.post")
    def test_html_has_content(self, mock_post):
        """HTML contains converted markdown content."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "1"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        md = "---\ntags:\n  - test\n---\n\n# Title\n\n**Bold** and [link](https://x.com)"
        deliver_to_reader(md, "Title", "key")

        html = mock_post.call_args.kwargs["json"]["html"]
        assert "<strong>Bold</strong>" in html
        assert '<a href="https://x.com">link</a>' in html


# ---------------------------------------------------------------------------
# Cover Image
# ---------------------------------------------------------------------------

class TestExtractThemes:
    def test_generates_prompt_via_gemini(self):
        mock_response = MagicMock()
        mock_response.text = "Interconnected translucent spheres and flowing amber-blue ribbons"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client) as mock_ctor:
            result = extract_themes("# Summary\n\nAI, cloud, and tools")

        assert result == "Interconnected translucent spheres and flowing amber-blue ribbons"
        mock_ctor.assert_called_once_with(
            vertexai=True,
            project="kx-hub",
            location="global",
        )
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-flash-preview"
        assert "Consider the ENTIRE summary" in call_kwargs["contents"]
        assert "Output ONLY the final image prompt" in call_kwargs["contents"]
        assert "AI, cloud, and tools" in call_kwargs["contents"]

    def test_uses_full_summary_not_prefix_only(self):
        mock_response = MagicMock()
        mock_response.text = "editorial motif prompt"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        markdown = ("intro " * 450) + "FINAL_THEME_MARKER"

        with patch("google.genai.Client", return_value=mock_client):
            extract_themes(markdown)

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert "FINAL_THEME_MARKER" in call_kwargs["contents"]


class TestGenerateCoverImage:
    def test_returns_image_bytes(self):
        """Test generate_cover_image with mocked Imagen API."""
        mock_image = MagicMock()
        mock_image.image.image_bytes = b"\x89PNG fake image bytes"

        mock_response = MagicMock()
        mock_response.generated_images = [mock_image]

        mock_client = MagicMock()
        mock_client.models.generate_images.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client):
            result = generate_cover_image("AI, Cloud", {"start": "2026-02-24", "end": "2026-03-03"})

        assert result == b"\x89PNG fake image bytes"
        assert mock_client.models.generate_images.call_count == 1
        call_kwargs = mock_client.models.generate_images.call_args
        assert "imagen-4.0" in call_kwargs.kwargs["model"]
        assert call_kwargs.kwargs["config"].aspect_ratio == "16:9"

    def test_raises_when_no_image(self):
        mock_response = MagicMock()
        mock_response.generated_images = []

        mock_client = MagicMock()
        mock_client.models.generate_images.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client):
            with pytest.raises(ValueError, match="No image generated"):
                generate_cover_image("themes", {"start": "2026-02-24", "end": "2026-03-03"})


class TestUploadToGcs:
    def test_uploads_and_returns_url(self):
        mock_blob = MagicMock()
        mock_blob.public_url = "https://storage.googleapis.com/kx-hub-summary-images/test.png"

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_storage_client):
            url = upload_to_gcs(b"fake-image", "test.png")

        assert url == "https://storage.googleapis.com/kx-hub-summary-images/test.png"
        mock_blob.upload_from_string.assert_called_once_with(b"fake-image", content_type="image/png")


# ---------------------------------------------------------------------------
# Delivery: image_url support
# ---------------------------------------------------------------------------

class TestDeliverToReaderWithImage:
    @patch("src.summary.delivery.requests.post")
    def test_includes_image_url_in_payload(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "reader-123", "url": "https://read.readwise.io/123"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        deliver_to_reader(
            markdown="# Test\n\nContent",
            title="Knowledge Summary: Test",
            api_key="test-key",
            image_url="https://storage.googleapis.com/kx-hub-summary-images/test.png",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["image_url"] == "https://storage.googleapis.com/kx-hub-summary-images/test.png"

    @patch("src.summary.delivery.requests.post")
    def test_omits_image_url_when_none(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "reader-123", "url": "https://read.readwise.io/123"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        deliver_to_reader(
            markdown="# Test\n\nContent",
            title="Knowledge Summary: Test",
            api_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert "image_url" not in payload


# ---------------------------------------------------------------------------
# Cloud Function entry point
# ---------------------------------------------------------------------------

class TestMainHandler:
    @patch("src.summary.main._save_summary")
    @patch("src.summary.main.deliver_to_reader")
    @patch("src.summary.main.get_secret")
    @patch("src.summary.main.upload_html_to_gcs")
    @patch("src.summary.main.upload_to_gcs")
    @patch("src.summary.main.generate_cover_image")
    @patch("src.summary.main.extract_themes")
    @patch("src.summary.main.generate_summary_text")
    @patch("src.summary.main.load_config")
    @patch("src.summary.main.collect_summary_data")
    def test_handler_success_with_delivery(self, mock_collect, mock_config, mock_gen, mock_extract, mock_cover, mock_upload, mock_upload_html, mock_secret, mock_deliver, mock_save):
        from src.summary.main import generate_summary

        mock_config.return_value = {"enabled": True, "days": 7, "limit": 100, "deliver_to_reader": True}
        mock_collect.return_value = _make_pipeline_data()
        mock_gen.return_value = {
            "markdown": "## AI Trends\n\nSome text",
            "model": "gemini-3.1-pro-preview",
            "input_tokens": 1000,
            "output_tokens": 500,
        }
        mock_extract.return_value = "abstract image prompt"
        mock_cover.return_value = b"fake-image"
        mock_upload.return_value = "https://storage.googleapis.com/kx-hub-summary-images/test.png"
        mock_upload_html.return_value = "https://storage.googleapis.com/kx-hub-summary-images/test_summary.html"
        mock_secret.return_value = "fake-api-key"
        mock_deliver.return_value = {"status": "saved", "reader_id": "r-1", "reader_url": "https://read.readwise.io/1"}

        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        response = generate_summary(mock_request)

        assert response["status"] == "success"
        assert response["delivery"]["status"] == "saved"
        assert response["image_url"] == "https://storage.googleapis.com/kx-hub-summary-images/test.png"
        assert response["html_url"] == "https://storage.googleapis.com/kx-hub-summary-images/test_summary.html"
        mock_deliver.assert_called_once()
        deliver_kwargs = mock_deliver.call_args.kwargs
        assert deliver_kwargs["image_url"] == "https://storage.googleapis.com/kx-hub-summary-images/test.png"
        assert deliver_kwargs["html_url"] == "https://storage.googleapis.com/kx-hub-summary-images/test_summary.html"
        mock_save.assert_called_once()
        save_kwargs = mock_save.call_args.kwargs
        assert save_kwargs["title"].startswith("Knowledge Summary:")
        assert save_kwargs["markdown"] == "## AI Trends\n\nSome text"
        assert save_kwargs["period"] == _make_pipeline_data()["period"]
        assert save_kwargs["delivery"]["status"] == "saved"

    @patch("src.summary.main._save_summary")
    @patch("src.summary.main.generate_summary_text")
    @patch("src.summary.main.load_config")
    @patch("src.summary.main.collect_summary_data")
    def test_handler_dry_run_skips_delivery_and_save(self, mock_collect, mock_config, mock_gen, mock_save):
        from src.summary.main import generate_summary

        mock_config.return_value = {"enabled": True, "days": 7, "limit": 100, "deliver_to_reader": True}
        mock_collect.return_value = _make_pipeline_data()
        mock_gen.return_value = {
            "markdown": "# Summary\n...",
            "model": "gemini-3.1-pro-preview",
            "input_tokens": 1000,
            "output_tokens": 500,
        }

        mock_request = MagicMock()
        mock_request.get_json.return_value = {"dry_run": True}

        response = generate_summary(mock_request)

        assert response["status"] == "success"
        assert response["delivery"]["status"] == "dry_run"
        mock_save.assert_not_called()

    @patch("src.summary.main.load_config")
    def test_handler_disabled(self, mock_config):
        from src.summary.main import generate_summary

        mock_config.return_value = {"enabled": False}

        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        response = generate_summary(mock_request)
        assert response["status"] == "disabled"

    @patch("src.summary.main.load_config")
    @patch("src.summary.main.collect_summary_data")
    def test_handler_no_sources(self, mock_collect, mock_config):
        from src.summary.main import generate_summary

        mock_config.return_value = {"enabled": True, "days": 7, "limit": 100}
        mock_collect.return_value = _make_pipeline_data(
            sources=[],
            stats={
                "total_chunks": 0, "total_sources": 0,
                "total_highlights": 0, "total_relationships": 0,
                "source_types": {},
            },
        )

        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        response = generate_summary(mock_request)
        assert response["status"] == "success"
        assert "No sources" in response["message"]

    @patch("src.summary.main.generate_summary_text")
    @patch("src.summary.main.load_config")
    @patch("src.summary.main.collect_summary_data")
    def test_handler_request_overrides(self, mock_collect, mock_config, mock_gen):
        from src.summary.main import generate_summary

        mock_config.return_value = {"enabled": True, "days": 7, "limit": 100}
        mock_collect.return_value = _make_pipeline_data(sources=[])

        mock_request = MagicMock()
        mock_request.get_json.return_value = {"days": 14, "limit": 50}

        generate_summary(mock_request)

        mock_collect.assert_called_once_with(days=14, limit=50)

    @patch("src.summary.main.load_config")
    @patch("src.summary.main.collect_summary_data")
    def test_handler_error(self, mock_collect, mock_config):
        from src.summary.main import generate_summary

        mock_config.return_value = {"enabled": True, "days": 7, "limit": 100}
        mock_collect.side_effect = RuntimeError("Firestore down")

        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        response = generate_summary(mock_request)
        assert response["status"] == "error"
        assert "Firestore down" in response["error"]

    @patch("src.summary.main.generate_summary_text")
    @patch("src.summary.main.load_config")
    @patch("src.summary.main.collect_summary_data")
    def test_handler_passes_model_override(self, mock_collect, mock_config, mock_gen):
        from src.summary.main import generate_summary

        mock_config.return_value = {"enabled": True, "days": 7, "limit": 100}
        mock_collect.return_value = _make_pipeline_data()
        mock_gen.return_value = {
            "markdown": "# Test", "model": "gemini-2.5-flash",
            "input_tokens": 0, "output_tokens": 0,
        }

        mock_request = MagicMock()
        mock_request.get_json.return_value = {"model": "gemini-2.5-flash", "dry_run": True}

        generate_summary(mock_request)

        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs["model"] == "gemini-2.5-flash"
