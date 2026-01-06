"""
Tests for Epic 7: Async MCP Interface

Tests async job creation, polling, and recommendations history.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "mcp_server"))


class TestAsyncJobCreation:
    """Tests for async job creation in Firestore."""

    @patch("firestore_client.get_firestore_client")
    def test_create_async_job_success(self, mock_get_client):
        """Test successful async job creation."""
        import firestore_client

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        result = firestore_client.create_async_job(
            job_type="recommendations",
            params={"mode": "balanced", "hot_sites": "tech"},
            user_id="test-user",
        )

        assert "job_id" in result
        assert result["job_id"].startswith("rec-")
        assert result["status"] == "pending"
        assert "created_at" in result

        # Verify Firestore was called
        mock_db.collection.assert_called_with("async_jobs")

    @patch("firestore_client.get_firestore_client")
    def test_create_async_job_generates_unique_id(self, mock_get_client):
        """Test that each job gets a unique ID."""
        import firestore_client

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        job1 = firestore_client.create_async_job(job_type="recommendations", params={})
        job2 = firestore_client.create_async_job(job_type="recommendations", params={})

        assert job1["job_id"] != job2["job_id"]


class TestAsyncJobRetrieval:
    """Tests for async job retrieval."""

    @patch("firestore_client.get_firestore_client")
    def test_get_async_job_found(self, mock_get_client):
        """Test retrieving an existing job."""
        import firestore_client

        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "job_id": "rec-123",
            "job_type": "recommendations",
            "status": "running",
            "progress": 0.5,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "completed_at": None,
            "expires_at": datetime.utcnow() + timedelta(days=14),
            "params": {"mode": "balanced"},
            "result": None,
            "error": None,
        }
        mock_db.collection.return_value.document.return_value.get.return_value = (
            mock_doc
        )
        mock_get_client.return_value = mock_db

        result = firestore_client.get_async_job("rec-123")

        assert result is not None
        assert result["job_id"] == "rec-123"
        assert result["status"] == "running"
        assert result["progress"] == 0.5

    @patch("firestore_client.get_firestore_client")
    def test_get_async_job_not_found(self, mock_get_client):
        """Test retrieving a non-existent job."""
        import firestore_client

        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = (
            mock_doc
        )
        mock_get_client.return_value = mock_db

        result = firestore_client.get_async_job("nonexistent")

        assert result is None


class TestAsyncJobUpdate:
    """Tests for async job status updates."""

    @patch("firestore_client.get_firestore_client")
    def test_update_async_job_status(self, mock_get_client):
        """Test updating job status."""
        import firestore_client

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        result = firestore_client.update_async_job(
            "rec-123", status="running", progress=0.3
        )

        assert result is True
        mock_db.collection.return_value.document.return_value.update.assert_called_once()

    @patch("firestore_client.get_firestore_client")
    def test_update_async_job_completed(self, mock_get_client):
        """Test marking job as completed sets completed_at."""
        import firestore_client

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        result = firestore_client.update_async_job(
            "rec-123",
            status="completed",
            progress=1.0,
            result={"recommendations": []},
        )

        assert result is True
        call_args = (
            mock_db.collection.return_value.document.return_value.update.call_args
        )
        update_data = call_args[0][0]
        assert update_data["status"] == "completed"
        assert "completed_at" in update_data


class TestRecommendationsTool:
    """Tests for the recommendations MCP tool."""

    @patch("firestore_client.get_async_job")
    def test_recommendations_poll_completed(self, mock_get_job):
        """Test polling a completed job returns result."""
        import tools

        mock_get_job.return_value = {
            "job_id": "rec-123",
            "status": "completed",
            "progress": 1.0,
            "created_at": "2026-01-06T10:00:00Z",
            "updated_at": "2026-01-06T10:01:00Z",
            "completed_at": "2026-01-06T10:01:00Z",
            "result": {
                "recommendations": [
                    {"title": "Test Article", "url": "https://example.com"}
                ]
            },
        }

        result = tools.recommendations(job_id="rec-123")

        assert result["status"] == "completed"
        assert "result" in result
        assert len(result["result"]["recommendations"]) == 1

    @patch("firestore_client.get_async_job")
    def test_recommendations_poll_running(self, mock_get_job):
        """Test polling a running job returns progress."""
        import tools

        mock_get_job.return_value = {
            "job_id": "rec-123",
            "status": "running",
            "progress": 0.5,
            "created_at": "2026-01-06T10:00:00Z",
            "updated_at": "2026-01-06T10:00:30Z",
        }

        result = tools.recommendations(job_id="rec-123")

        assert result["status"] == "running"
        assert result["progress"] == 0.5
        assert "poll_after_seconds" in result

    @patch("firestore_client.get_async_job")
    def test_recommendations_poll_not_found(self, mock_get_job):
        """Test polling non-existent job returns error."""
        import tools

        mock_get_job.return_value = None

        result = tools.recommendations(job_id="nonexistent")

        assert "error" in result

    @patch("firestore_client.create_async_job")
    @patch("tools._executor")
    def test_recommendations_start_job(self, mock_executor, mock_create_job):
        """Test starting a new recommendations job."""
        import tools

        mock_create_job.return_value = {
            "job_id": "rec-new123",
            "status": "pending",
            "created_at": "2026-01-06T10:00:00Z",
        }

        result = tools.recommendations(
            hot_sites="tech",
            mode="surprise_me",
            limit=5,
        )

        assert result["job_id"] == "rec-new123"
        assert result["status"] == "pending"
        assert "poll_after_seconds" in result
        assert "estimated_duration_seconds" in result

        # Verify background execution was started
        mock_executor.submit.assert_called_once()


class TestRecommendationsHistory:
    """Tests for recommendations_history tool."""

    @patch("firestore_client.get_recommendations_history")
    def test_recommendations_history_returns_flat_list(self, mock_get_history):
        """Test history returns flat list of recommendations."""
        import tools

        mock_get_history.return_value = {
            "days": 14,
            "total_count": 2,
            "recommendations": [
                {
                    "title": "Article 1",
                    "url": "https://example.com/1",
                    "domain": "example.com",
                    "recommended_at": "2026-01-06T10:00:00Z",
                    "params": {"mode": "balanced", "hot_sites": "tech"},
                    "why_recommended": "Related to your reading",
                },
                {
                    "title": "Article 2",
                    "url": "https://example.com/2",
                    "domain": "example.com",
                    "recommended_at": "2026-01-05T10:00:00Z",
                    "params": {"mode": "fresh", "hot_sites": "ai"},
                    "why_recommended": "Trending topic",
                },
            ],
        }

        result = tools.recommendations_history(days=14)

        assert result["days"] == 14
        assert result["total_count"] == 2
        assert len(result["recommendations"]) == 2
        assert result["recommendations"][0]["title"] == "Article 1"

    @patch("firestore_client.get_recommendations_history")
    def test_recommendations_history_empty(self, mock_get_history):
        """Test history with no recommendations."""
        import tools

        mock_get_history.return_value = {
            "days": 14,
            "total_count": 0,
            "recommendations": [],
        }

        result = tools.recommendations_history()

        assert result["total_count"] == 0
        assert result["recommendations"] == []


class TestBackgroundJobExecution:
    """Tests for background job execution."""

    @patch("firestore_client.update_async_job")
    @patch("tools.get_reading_recommendations")
    def test_run_recommendations_job_success(self, mock_get_recs, mock_update):
        """Test successful background job execution."""
        import tools

        mock_get_recs.return_value = {
            "recommendations": [{"title": "Test"}],
            "processing_time_seconds": 60,
        }

        tools._run_recommendations_job(
            "rec-123",
            {"mode": "balanced", "limit": 10},
        )

        # Should have been called at least twice: running and completed
        assert mock_update.call_count >= 2

        # Last call should be completed
        last_call = mock_update.call_args_list[-1]
        assert last_call[1]["status"] == "completed"
        assert last_call[1]["result"] is not None

    @patch("firestore_client.update_async_job")
    @patch("tools.get_reading_recommendations")
    def test_run_recommendations_job_error(self, mock_get_recs, mock_update):
        """Test background job handles errors."""
        import tools

        mock_get_recs.return_value = {
            "error": "Tavily API failed",
            "recommendations": [],
        }

        tools._run_recommendations_job(
            "rec-123",
            {"mode": "balanced"},
        )

        # Last call should be failed
        last_call = mock_update.call_args_list[-1]
        assert last_call[1]["status"] == "failed"
        assert "error" in last_call[1]

    @patch("firestore_client.update_async_job")
    @patch("tools.get_reading_recommendations")
    def test_run_recommendations_job_exception(self, mock_get_recs, mock_update):
        """Test background job handles exceptions."""
        import tools

        mock_get_recs.side_effect = Exception("Unexpected error")

        tools._run_recommendations_job(
            "rec-123",
            {"mode": "balanced"},
        )

        # Should have marked as failed
        last_call = mock_update.call_args_list[-1]
        assert last_call[1]["status"] == "failed"
