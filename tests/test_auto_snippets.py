"""
Unit tests for Auto-Snippets Cloud Function (Story 13.4).

Tests cover:
- Config loading (tests 1-3)
- Idempotency checking (tests 4-6)
- Tag update flow (tests 7-9)
- Full pipeline orchestration (tests 10-14)
- Graceful degradation (tests 15-17)
- Job reporting (tests 18-20)
- Edge cases (tests 21-23)
"""

import os
import sys
import time

import pytest
from unittest.mock import MagicMock, Mock, patch, call

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/auto_snippets"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src/mcp_server"))

from auto_snippets.main import (
    auto_snippets,
    is_already_processed,
    load_config,
    store_job_report,
    update_tags,
)
from ingest.reader_client import ReadwiseReaderClient, ReaderDocument


# ============================================================================
# Test Helpers
# ============================================================================


def _make_raw_doc(
    doc_id="doc_123",
    title="Feature Flags Article",
    tags=None,
):
    """Create a raw document dict as returned by Reader API."""
    return {
        "id": doc_id,
        "title": title,
        "author": "Jane Developer",
        "source_url": f"https://example.com/{doc_id}",
        "tags": tags or ["kx-auto"],
        "category": "article",
        "html": f"<p>Content of {title}</p>",
        "word_count": 3000,
    }


def _mock_firestore_doc(exists=True, data=None):
    """Create a mock Firestore document snapshot."""
    mock_doc = MagicMock()
    mock_doc.exists = exists
    mock_doc.to_dict.return_value = data or {}
    return mock_doc


def _mock_reader_doc(clean_text="short article text"):
    """Create a mock ReaderDocument with a real clean_text attribute."""
    mock_doc = MagicMock(spec=ReaderDocument)
    mock_doc.clean_text = clean_text
    return mock_doc


# ============================================================================
# Test 1-3: Config Loading
# ============================================================================


class TestConfig:
    """Tests for config loading."""

    def test_load_config_defaults(self):
        """Test 1: Missing Firestore doc returns defaults."""
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_firestore_doc(exists=False)
        )

        config = load_config(mock_db)

        assert config["enabled"] is True
        assert config["tag"] == "kx-auto"
        assert config["processed_tag"] == "kx-processed"
        assert config["write_to_readwise"] is True
        assert config["max_documents_per_run"] == 20

    def test_load_config_from_firestore(self):
        """Test 2: Firestore config overrides defaults."""
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_firestore_doc(
                exists=True,
                data={
                    "tag": "custom-tag",
                    "max_documents_per_run": 5,
                },
            )
        )

        config = load_config(mock_db)

        assert config["tag"] == "custom-tag"
        assert config["max_documents_per_run"] == 5
        # Defaults still present for unset keys
        assert config["enabled"] is True
        assert config["processed_tag"] == "kx-processed"

    @patch("auto_snippets.main.get_firestore_client")
    @patch("auto_snippets.main.load_config")
    def test_disabled_returns_early(self, mock_load_config, mock_get_db):
        """Test 3: Disabled config returns without processing."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {"enabled": False}

        # Should not raise
        auto_snippets(event={}, context=None)

        # No further calls (no get_secret, no fetch)
        mock_db.collection.assert_not_called()


# ============================================================================
# Test 4-6: Idempotency Checking
# ============================================================================


class TestIdempotency:
    """Tests for idempotency checking."""

    def test_already_processed_returns_true(self):
        """Test 4: Document with existing kb_item returns True."""
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_firestore_doc(exists=True)
        )

        assert is_already_processed(mock_db, "doc_abc") is True

    def test_not_processed_returns_false(self):
        """Test 5: Document without kb_item returns False."""
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_firestore_doc(exists=False)
        )

        assert is_already_processed(mock_db, "doc_xyz") is False

    def test_correct_chunk_id_checked(self):
        """Test 6: Checks the correct kb_items document ID."""
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = (
            _mock_firestore_doc(exists=False)
        )

        is_already_processed(mock_db, "my_doc_id")

        mock_db.collection.assert_called_with("kb_items")
        mock_db.collection.return_value.document.assert_called_with(
            "auto_snippet_my_doc_id_0"
        )


# ============================================================================
# Test 7-9: Tag Update Flow
# ============================================================================


class TestTagUpdate:
    """Tests for tag update flow."""

    def test_success_calls_reader(self):
        """Test 7: Successful tag update calls update_document_tags."""
        mock_reader = MagicMock(spec=ReadwiseReaderClient)
        mock_reader.update_document_tags.return_value = {"id": "doc_123"}

        result = update_tags(
            reader=mock_reader,
            document_id="doc_123",
            current_tags=["kx-auto", "tech"],
            remove_tag="kx-auto",
            add_tag="kx-processed",
        )

        assert result is True
        mock_reader.update_document_tags.assert_called_once_with(
            document_id="doc_123",
            current_tags=["kx-auto", "tech"],
            remove_tags=["kx-auto"],
            add_tags=["kx-processed"],
        )

    def test_failure_returns_false(self):
        """Test 8: Failed tag update returns False."""
        mock_reader = MagicMock(spec=ReadwiseReaderClient)
        mock_reader.update_document_tags.side_effect = Exception("API error")

        result = update_tags(
            reader=mock_reader,
            document_id="doc_123",
            current_tags=["kx-auto"],
            remove_tag="kx-auto",
            add_tag="kx-processed",
        )

        assert result is False

    def test_correct_params(self):
        """Test 9: Tag update passes correct parameters."""
        mock_reader = MagicMock(spec=ReadwiseReaderClient)
        mock_reader.update_document_tags.return_value = {}

        update_tags(
            reader=mock_reader,
            document_id="doc_456",
            current_tags=["alpha", "beta", "kx-auto"],
            remove_tag="kx-auto",
            add_tag="kx-processed",
        )

        call_kwargs = mock_reader.update_document_tags.call_args[1]
        assert call_kwargs["remove_tags"] == ["kx-auto"]
        assert call_kwargs["add_tags"] == ["kx-processed"]
        assert call_kwargs["current_tags"] == ["alpha", "beta", "kx-auto"]


# ============================================================================
# Test 10-14: Full Pipeline Orchestration
# ============================================================================


class TestFullPipeline:
    """Tests for end-to-end auto_snippets function."""

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_happy_path_processes_and_tags(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Test 10: Happy path processes documents and updates tags."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "test-api-key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [
            _make_raw_doc("doc_1", "Article 1"),
            _make_raw_doc("doc_2", "Article 2"),
        ]
        mock_reader.extract_document_content.return_value = _mock_reader_doc()

        mock_idempotent.return_value = False
        mock_process.return_value = {
            "snippets_extracted": 3,
            "chunks_embedded": 3,
            "highlights_created": 3,
            "problem_matches": 1,
        }
        mock_update_tags.return_value = True
        mock_report.return_value = "report_123"

        auto_snippets(event={}, context=None)

        assert mock_process.call_count == 2
        assert mock_update_tags.call_count == 2
        mock_report.assert_called_once()
        report_kwargs = mock_report.call_args[1]
        assert report_kwargs["status"] == "success"
        assert len(report_kwargs["processed"]) == 2
        assert len(report_kwargs["failed"]) == 0

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_partial_failure_mixed_results(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Test 11: Mixed results — some succeed, some fail."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [
            _make_raw_doc("doc_1"),
            _make_raw_doc("doc_2"),
            _make_raw_doc("doc_3"),
        ]
        mock_reader.extract_document_content.side_effect = [
            _mock_reader_doc(),
            Exception("Parse error"),
            _mock_reader_doc(),
        ]

        mock_idempotent.return_value = False
        mock_process.side_effect = [
            {"snippets_extracted": 2, "chunks_embedded": 2, "highlights_created": 0, "problem_matches": 0},
            {"snippets_extracted": 1, "chunks_embedded": 1, "highlights_created": 0, "problem_matches": 0},
        ]
        mock_update_tags.return_value = True
        mock_report.return_value = "report_456"

        auto_snippets(event={}, context=None)

        report_kwargs = mock_report.call_args[1]
        assert len(report_kwargs["processed"]) == 2
        assert len(report_kwargs["failed"]) == 1
        assert "doc_2" in report_kwargs["failed"]

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_all_skipped_idempotent(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_report,
    ):
        """Test 12: All documents already processed — all skipped."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [
            _make_raw_doc("doc_1"),
            _make_raw_doc("doc_2"),
        ]

        mock_idempotent.return_value = True  # All already processed
        mock_report.return_value = "report_789"

        auto_snippets(event={}, context=None)

        mock_process.assert_not_called()
        report_kwargs = mock_report.call_args[1]
        assert len(report_kwargs["skipped"]) == 2
        assert len(report_kwargs["processed"]) == 0

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_process_failure_retains_tags(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Test 13: Process failure retains tags for retry."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [_make_raw_doc("doc_1")]
        mock_reader.extract_document_content.return_value = _mock_reader_doc()

        mock_idempotent.return_value = False
        mock_process.side_effect = Exception("Pipeline error")
        mock_report.return_value = "report_err"

        auto_snippets(event={}, context=None)

        # Tags NOT updated on failure
        mock_update_tags.assert_not_called()
        report_kwargs = mock_report.call_args[1]
        assert len(report_kwargs["failed"]) == 1

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_max_documents_limit(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Test 14: max_documents_per_run limits processing."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 2,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        # 5 documents available, but max is 2
        mock_reader.fetch_tagged_documents.return_value = [
            _make_raw_doc(f"doc_{i}") for i in range(5)
        ]
        mock_reader.extract_document_content.return_value = _mock_reader_doc()

        mock_idempotent.return_value = False
        mock_process.return_value = {
            "snippets_extracted": 1,
            "chunks_embedded": 1,
            "highlights_created": 0,
            "problem_matches": 0,
        }
        mock_update_tags.return_value = True
        mock_report.return_value = "report_max"

        auto_snippets(event={}, context=None)

        # Only 2 documents processed
        assert mock_process.call_count == 2


# ============================================================================
# Test 15-17: Graceful Degradation
# ============================================================================


class TestGracefulDegradation:
    """Tests for error handling and graceful degradation."""

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_reader_api_down(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_report,
    ):
        """Test 15: Reader API failure stores error report and re-raises."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.side_effect = Exception("Reader API down")
        mock_report.return_value = "report_fail"

        with pytest.raises(Exception, match="Reader API down"):
            auto_snippets(event={}, context=None)

        mock_report.assert_called_once()
        report_kwargs = mock_report.call_args[1]
        assert report_kwargs["status"] == "failed"
        assert "Reader API down" in report_kwargs["error"]

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_process_document_exception_continues(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Test 16: One document failure doesn't stop processing others."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [
            _make_raw_doc("doc_1"),
            _make_raw_doc("doc_2"),
            _make_raw_doc("doc_3"),
        ]
        mock_reader.extract_document_content.return_value = _mock_reader_doc()

        mock_idempotent.return_value = False
        mock_process.side_effect = [
            {"snippets_extracted": 2, "chunks_embedded": 2, "highlights_created": 0, "problem_matches": 0},
            Exception("LLM timeout"),
            {"snippets_extracted": 1, "chunks_embedded": 1, "highlights_created": 0, "problem_matches": 0},
        ]
        mock_update_tags.return_value = True
        mock_report.return_value = "report_partial"

        auto_snippets(event={}, context=None)

        # 2 succeeded, 1 failed
        report_kwargs = mock_report.call_args[1]
        assert len(report_kwargs["processed"]) == 2
        assert len(report_kwargs["failed"]) == 1

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_tag_update_failure_nonblocking(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Test 17: Tag update failure doesn't prevent success report."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [_make_raw_doc("doc_1")]
        mock_reader.extract_document_content.return_value = _mock_reader_doc()

        mock_idempotent.return_value = False
        mock_process.return_value = {
            "snippets_extracted": 3,
            "chunks_embedded": 3,
            "highlights_created": 0,
            "problem_matches": 0,
        }
        # Tag update fails, but shouldn't crash
        mock_update_tags.return_value = False
        mock_report.return_value = "report_tag_fail"

        auto_snippets(event={}, context=None)

        # Document still counted as processed (snippets were extracted)
        report_kwargs = mock_report.call_args[1]
        assert report_kwargs["status"] == "success"
        assert len(report_kwargs["processed"]) == 1


# ============================================================================
# Test 18-20: Job Reporting
# ============================================================================


class TestJobReporting:
    """Tests for job report storage."""

    def test_success_report_structure(self):
        """Test 18: Success report has correct structure."""
        mock_db = MagicMock()
        mock_doc_ref = (None, MagicMock())
        mock_doc_ref[1].id = "job_abc"
        mock_db.collection.return_value.add.return_value = mock_doc_ref

        job_id = store_job_report(
            db=mock_db,
            config={"tag": "kx-auto"},
            status="success",
            metrics={"documents_processed": 3},
            processed=["doc_1", "doc_2", "doc_3"],
            skipped=[],
            failed=[],
            execution_time=45.2,
        )

        assert job_id == "job_abc"
        mock_db.collection.assert_called_with("batch_jobs")

        # Verify report structure
        report = mock_db.collection.return_value.add.call_args[0][0]
        assert report["job_type"] == "auto_snippets"
        assert report["status"] == "success"
        assert report["config"] == {"tag": "kx-auto"}
        assert report["metrics"] == {"documents_processed": 3}
        assert report["processed"] == ["doc_1", "doc_2", "doc_3"]
        assert report["skipped"] == []
        assert report["failed"] == []
        assert report["error"] is None
        assert report["execution_time_seconds"] == 45.2
        assert "timestamp" in report

    def test_failure_report_stored(self):
        """Test 19: Failure report includes error details."""
        mock_db = MagicMock()
        mock_doc_ref = (None, MagicMock())
        mock_doc_ref[1].id = "job_fail"
        mock_db.collection.return_value.add.return_value = mock_doc_ref

        job_id = store_job_report(
            db=mock_db,
            config={},
            status="failed",
            metrics={},
            processed=[],
            skipped=[],
            failed=[],
            error="Reader API timeout",
            execution_time=5.0,
        )

        report = mock_db.collection.return_value.add.call_args[0][0]
        assert report["status"] == "failed"
        assert report["error"] == "Reader API timeout"
        assert report["job_type"] == "auto_snippets"

    def test_metrics_accuracy(self):
        """Test 20: Metrics reflect actual processing results."""
        mock_db = MagicMock()
        mock_doc_ref = (None, MagicMock())
        mock_doc_ref[1].id = "job_metrics"
        mock_db.collection.return_value.add.return_value = mock_doc_ref

        metrics = {
            "documents_found": 10,
            "documents_processed": 5,
            "documents_skipped": 3,
            "documents_failed": 2,
            "total_snippets": 15,
            "total_embedded": 14,
        }

        store_job_report(
            db=mock_db,
            config={},
            status="success",
            metrics=metrics,
            processed=["d1", "d2", "d3", "d4", "d5"],
            skipped=["d6", "d7", "d8"],
            failed=["d9", "d10"],
        )

        report = mock_db.collection.return_value.add.call_args[0][0]
        assert report["metrics"]["documents_found"] == 10
        assert report["metrics"]["total_snippets"] == 15
        assert len(report["processed"]) == 5
        assert len(report["skipped"]) == 3
        assert len(report["failed"]) == 2


# ============================================================================
# Test 21-23: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_empty_documents_list(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_report,
    ):
        """Test 21: No tagged documents — success with zero counts."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = []
        mock_report.return_value = "report_empty"

        auto_snippets(event={}, context=None)

        report_kwargs = mock_report.call_args[1]
        assert report_kwargs["status"] == "success"
        assert report_kwargs["metrics"]["documents_found"] == 0

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_zero_snippets_skips_tags(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Test 22: Document with zero snippets skips tag update."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [_make_raw_doc("doc_1")]
        mock_reader.extract_document_content.return_value = _mock_reader_doc()

        mock_idempotent.return_value = False
        mock_process.return_value = {
            "snippets_extracted": 0,
            "chunks_embedded": 0,
            "highlights_created": 0,
            "problem_matches": 0,
        }
        mock_report.return_value = "report_no_snippets"

        auto_snippets(event={}, context=None)

        # Tags NOT updated when no snippets extracted
        mock_update_tags.assert_not_called()
        report_kwargs = mock_report.call_args[1]
        assert len(report_kwargs["skipped"]) == 1
        assert len(report_kwargs["processed"]) == 0

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    def test_custom_tag_names_from_config(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Test 23: Custom tag names from config are used correctly."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "custom-ingest",
            "processed_tag": "custom-done",
            "write_to_readwise": False,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [
            _make_raw_doc("doc_1", tags=["custom-ingest"])
        ]
        mock_reader.extract_document_content.return_value = _mock_reader_doc()

        mock_idempotent.return_value = False
        mock_process.return_value = {
            "snippets_extracted": 2,
            "chunks_embedded": 2,
            "highlights_created": 0,
            "problem_matches": 0,
        }
        mock_update_tags.return_value = True
        mock_report.return_value = "report_custom"

        auto_snippets(event={}, context=None)

        # Verify custom tag used for fetch
        mock_reader.fetch_tagged_documents.assert_called_once_with(tag="custom-ingest", category="")

        # Verify custom tags used for update (positional args)
        update_call = mock_update_tags.call_args[0]
        assert update_call[3] == "custom-ingest"  # remove_tag
        assert update_call[4] == "custom-done"  # add_tag


# ============================================================================
# Tests: Overflow Tag Handling
# ============================================================================


class TestOverflowTag:
    """Tests for kx-overflow tag behavior."""

    def test_update_tags_with_extra_tags(self):
        """extra_tags are included in the add_tags call."""
        mock_reader = MagicMock(spec=ReadwiseReaderClient)
        mock_reader.update_document_tags.return_value = {}

        result = update_tags(
            reader=mock_reader,
            document_id="doc_big",
            current_tags=["kx-auto"],
            remove_tag="kx-auto",
            add_tag="kx-processed",
            extra_tags=["kx-overflow"],
        )

        assert result is True
        call_kwargs = mock_reader.update_document_tags.call_args[1]
        assert "kx-processed" in call_kwargs["add_tags"]
        assert "kx-overflow" in call_kwargs["add_tags"]

    def test_update_tags_no_extra_tags_unchanged(self):
        """Without extra_tags, only the regular add_tag is added."""
        mock_reader = MagicMock(spec=ReadwiseReaderClient)
        mock_reader.update_document_tags.return_value = {}

        update_tags(
            reader=mock_reader,
            document_id="doc_normal",
            current_tags=["kx-auto"],
            remove_tag="kx-auto",
            add_tag="kx-processed",
        )

        call_kwargs = mock_reader.update_document_tags.call_args[1]
        assert call_kwargs["add_tags"] == ["kx-processed"]

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    @patch("auto_snippets.main.OVERFLOW_THRESHOLD", 100)  # Low threshold for test
    def test_overflow_document_gets_kx_overflow_tag(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Document exceeding OVERFLOW_THRESHOLD gets kx-overflow tag."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [_make_raw_doc("doc_big")]

        # ReaderDocument with text exceeding threshold (>100 chars)
        mock_doc = MagicMock(spec=ReaderDocument)
        mock_doc.clean_text = "x" * 200
        mock_doc.title = "Big Article"
        mock_reader.extract_document_content.return_value = mock_doc

        mock_idempotent.return_value = False
        mock_process.return_value = {
            "snippets_extracted": 3,
            "chunks_embedded": 3,
            "highlights_created": 0,
            "problem_matches": 0,
        }
        mock_update_tags.return_value = True
        mock_report.return_value = "report_overflow"

        auto_snippets(event={}, context=None)

        mock_update_tags.assert_called_once()
        call_kwargs = mock_update_tags.call_args[1]
        assert call_kwargs.get("extra_tags") == ["kx-overflow"]

    @patch("auto_snippets.main.store_job_report")
    @patch("auto_snippets.main.update_tags")
    @patch("auto_snippets.main.process_document")
    @patch("auto_snippets.main.is_already_processed")
    @patch("auto_snippets.main.ReadwiseReaderClient")
    @patch("auto_snippets.main.get_secret")
    @patch("auto_snippets.main.load_config")
    @patch("auto_snippets.main.get_firestore_client")
    @patch("auto_snippets.main.OVERFLOW_THRESHOLD", 100)
    def test_normal_document_no_overflow_tag(
        self,
        mock_get_db,
        mock_load_config,
        mock_get_secret,
        mock_reader_cls,
        mock_idempotent,
        mock_process,
        mock_update_tags,
        mock_report,
    ):
        """Normal-sized document does NOT get kx-overflow tag."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_load_config.return_value = {
            "enabled": True,
            "tag": "kx-auto",
            "processed_tag": "kx-processed",
            "write_to_readwise": True,
            "max_documents_per_run": 20,
        }
        mock_get_secret.return_value = "key"

        mock_reader = MagicMock()
        mock_reader_cls.return_value = mock_reader
        mock_reader.fetch_tagged_documents.return_value = [_make_raw_doc("doc_small")]

        mock_doc = MagicMock(spec=ReaderDocument)
        mock_doc.clean_text = "x" * 50  # below threshold
        mock_reader.extract_document_content.return_value = mock_doc

        mock_idempotent.return_value = False
        mock_process.return_value = {
            "snippets_extracted": 2,
            "chunks_embedded": 2,
            "highlights_created": 0,
            "problem_matches": 0,
        }
        mock_update_tags.return_value = True
        mock_report.return_value = "report_normal"

        auto_snippets(event={}, context=None)

        mock_update_tags.assert_called_once()
        call_kwargs = mock_update_tags.call_args[1]
        assert call_kwargs.get("extra_tags") is None
