"""Unit tests for batch recommendations function."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/batch_recommendations'))

from main import (
    filter_by_recency_and_count,
    build_tags,
)


class TestFilterByRecency:
    """Test recency filtering logic."""

    def test_filter_by_recency_removes_old_articles(self):
        """Test that articles older than recency_days are filtered out."""
        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=10)).isoformat()
        recent_date = (now - timedelta(days=3)).isoformat()

        recommendations = [
            {
                "url": "https://old.com",
                "published_date": old_date,
                "final_score": 0.9,
                "title": "Old Article",
            },
            {
                "url": "https://recent.com",
                "published_date": recent_date,
                "final_score": 0.8,
                "title": "Recent Article",
            },
        ]

        filtered = filter_by_recency_and_count(
            recommendations,
            max_results=10,
            recency_days=7,
        )

        assert len(filtered) == 1
        assert filtered[0]["url"] == "https://recent.com"

    def test_filter_max_results_limit(self):
        """Test that max_results limit is respected."""
        now = datetime.now(timezone.utc)
        recommendations = [
            {
                "url": f"https://example{i}.com",
                "published_date": now.isoformat(),
                "final_score": 0.9 - i * 0.1,
                "title": f"Article {i}",
            }
            for i in range(10)
        ]

        filtered = filter_by_recency_and_count(
            recommendations,
            max_results=3,
            recency_days=30,
        )

        assert len(filtered) == 3
        # Should be top-scored items
        assert filtered[0]["final_score"] == 0.9

    def test_filter_returns_highest_scored_within_limit(self):
        """Test that highest-scored items are returned first."""
        now = datetime.now(timezone.utc)
        recommendations = [
            {"url": "https://low.com", "published_date": now.isoformat(), "final_score": 0.5, "title": "Low"},
            {"url": "https://high.com", "published_date": now.isoformat(), "final_score": 0.9, "title": "High"},
            {"url": "https://mid.com", "published_date": now.isoformat(), "final_score": 0.7, "title": "Mid"},
        ]

        filtered = filter_by_recency_and_count(
            recommendations,
            max_results=2,
            recency_days=30,
        )

        assert len(filtered) == 2
        assert filtered[0]["final_score"] == 0.9
        assert filtered[1]["final_score"] == 0.7

    def test_filter_handles_missing_published_date(self):
        """Test that articles without published_date are skipped gracefully."""
        now = datetime.now(timezone.utc)
        recommendations = [
            {"url": "https://nodatecom", "final_score": 0.9, "title": "No Date"},
            {"url": "https://withdate.com", "published_date": now.isoformat(), "final_score": 0.8, "title": "With Date"},
        ]

        filtered = filter_by_recency_and_count(
            recommendations,
            max_results=10,
            recency_days=30,
        )

        # Only the one with date should remain
        assert len(filtered) == 1
        assert filtered[0]["url"] == "https://withdate.com"

    def test_filter_handles_date_parsing_errors(self):
        """Test that invalid date formats are skipped gracefully."""
        now = datetime.now(timezone.utc)
        recommendations = [
            {"url": "https://baddate.com", "published_date": "invalid-date", "final_score": 0.9, "title": "Bad Date"},
            {"url": "https://gooddate.com", "published_date": now.isoformat(), "final_score": 0.8, "title": "Good Date"},
        ]

        filtered = filter_by_recency_and_count(
            recommendations,
            max_results=10,
            recency_days=30,
        )

        # Only the valid date should remain
        assert len(filtered) == 1
        assert filtered[0]["url"] == "https://gooddate.com"

    def test_filter_handles_date_only_format(self):
        """Test that YYYY-MM-DD format is parsed correctly."""
        now = datetime.now(timezone.utc)
        recent_date = (now - timedelta(days=2)).strftime("%Y-%m-%d")

        recommendations = [
            {
                "url": "https://example.com",
                "published_date": recent_date,
                "final_score": 0.9,
                "title": "Article",
            }
        ]

        filtered = filter_by_recency_and_count(
            recommendations,
            max_results=10,
            recency_days=7,
        )

        assert len(filtered) == 1


class TestBuildTags:
    """Test tag building logic."""

    def test_build_tags_includes_auto_tags(self):
        """Test that auto_tags from config are included."""
        rec = {
            "domain": "techcrunch.com",
            "tags": ["AI", "ML"],
        }
        config = {"auto_tags": ["ai-recommended", "batch"]}

        tags = build_tags(rec, config)

        assert "ai-recommended" in tags
        assert "batch" in tags

    def test_build_tags_includes_domain(self):
        """Test that domain is included in tags."""
        rec = {
            "domain": "techcrunch.com",
            "tags": ["AI"],
        }
        config = {"auto_tags": ["ai-recommended"]}

        tags = build_tags(rec, config)

        assert "techcrunch.com" in tags

    def test_build_tags_limits_topic_tags_to_two(self):
        """Test that only first 2 topic tags are included."""
        rec = {
            "domain": "techcrunch.com",
            "tags": ["AI", "ML", "LLMs", "DeepLearning"],
        }
        config = {"auto_tags": ["ai-recommended"]}

        tags = build_tags(rec, config)

        # Should have auto_tag, domain, and max 2 from tags
        assert "ai-recommended" in tags
        assert "techcrunch.com" in tags
        assert "AI" in tags or "ML" in tags  # Depends on implementation
        # Should not have more than 4 total tags
        assert len(tags) <= 4

    def test_build_tags_deduplicates(self):
        """Test that duplicate tags are removed."""
        rec = {
            "domain": "ai.com",
            "tags": ["AI", "AI"],
        }
        config = {"auto_tags": ["ai-recommended"]}

        tags = build_tags(rec, config)

        # Count occurrences of "AI"
        ai_count = tags.count("AI")
        assert ai_count == 1  # Should appear only once

    def test_build_tags_handles_missing_domain(self):
        """Test that missing domain doesn't break tag building."""
        rec = {
            "tags": ["AI"],
        }
        config = {"auto_tags": ["ai-recommended"]}

        tags = build_tags(rec, config)

        assert "ai-recommended" in tags
        assert "AI" in tags

    def test_build_tags_handles_missing_tags(self):
        """Test that missing tags list doesn't break tag building."""
        rec = {
            "domain": "example.com",
        }
        config = {"auto_tags": ["ai-recommended"]}

        tags = build_tags(rec, config)

        assert "ai-recommended" in tags
        assert "example.com" in tags


class TestIntegrationScenarios:
    """Integration tests for common scenarios."""

    def test_full_filter_pipeline(self):
        """Test complete filtering pipeline with mixed data."""
        now = datetime.now(timezone.utc)

        recommendations = [
            # Old article - should be filtered
            {
                "url": "https://old.com",
                "published_date": (now - timedelta(days=15)).isoformat(),
                "final_score": 0.95,
                "title": "Old Article",
                "domain": "old.com",
                "tags": ["tech"],
            },
            # Recent but lower score
            {
                "url": "https://recent-low.com",
                "published_date": (now - timedelta(days=2)).isoformat(),
                "final_score": 0.7,
                "title": "Recent Low Score",
                "domain": "recent.com",
                "tags": ["tech"],
            },
            # Recent and high score
            {
                "url": "https://recent-high.com",
                "published_date": (now - timedelta(days=1)).isoformat(),
                "final_score": 0.9,
                "title": "Recent High Score",
                "domain": "recent.com",
                "tags": ["tech"],
            },
        ]

        filtered = filter_by_recency_and_count(
            recommendations,
            max_results=2,
            recency_days=7,
        )

        # Should filter out the old article and keep 2 recent ones
        assert len(filtered) == 2
        assert filtered[0]["url"] == "https://recent-high.com"  # Higher score first
        assert filtered[1]["url"] == "https://recent-low.com"

    def test_empty_recommendations(self):
        """Test handling of empty recommendations list."""
        filtered = filter_by_recency_and_count([], max_results=3, recency_days=7)
        assert filtered == []

    def test_all_articles_too_old(self):
        """Test when all articles are outside recency window."""
        now = datetime.now(timezone.utc)
        recommendations = [
            {
                "url": "https://old.com",
                "published_date": (now - timedelta(days=100)).isoformat(),
                "final_score": 0.9,
                "title": "Old",
            }
        ]

        filtered = filter_by_recency_and_count(
            recommendations,
            max_results=10,
            recency_days=7,
        )

        assert len(filtered) == 0
