"""
Tests for Summary Data Pipeline (Story 9.1).
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
# Cloud Function entry point
# ---------------------------------------------------------------------------

class TestMainHandler:
    @patch("src.summary.main.load_config")
    @patch("src.summary.main.collect_summary_data")
    def test_handler_success(self, mock_collect, mock_config):
        from src.summary.main import generate_summary

        mock_config.return_value = {"enabled": True, "days": 7, "limit": 100}
        mock_collect.return_value = {
            "period": {"start": "2026-02-23", "end": "2026-03-02", "days": 7},
            "stats": {
                "total_chunks": 5,
                "total_sources": 2,
                "total_highlights": 5,
                "total_relationships": 1,
                "source_types": {"article": 2},
            },
            "sources": [],
            "relationships": [],
        }

        mock_request = MagicMock()
        mock_request.get_json.return_value = {}

        response = generate_summary(mock_request)

        assert response["status"] == "success"
        assert response["stats"]["total_chunks"] == 5

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
    def test_handler_request_overrides(self, mock_collect, mock_config):
        from src.summary.main import generate_summary

        mock_config.return_value = {"enabled": True, "days": 7, "limit": 100}
        mock_collect.return_value = {
            "period": {"start": "2026-02-16", "end": "2026-03-02", "days": 14},
            "stats": {
                "total_chunks": 0, "total_sources": 0,
                "total_highlights": 0, "total_relationships": 0,
                "source_types": {},
            },
            "sources": [],
            "relationships": [],
        }

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
