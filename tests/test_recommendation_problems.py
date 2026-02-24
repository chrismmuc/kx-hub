"""
Tests for recommendation_problems.py

Epic 11: Problem-Driven Recommendations
Story 11.1: Problem-Based Query Generation
"""

import pytest
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, "src/mcp_server")

from recommendation_problems import (
    translate_to_english,
    get_active_problems,
    sort_problems_by_mode,
    get_evidence_keywords,
    generate_problem_queries,
    format_query_for_tavily,
    filter_problems_by_topic,
    DEEPEN_TEMPLATES,
    EXPLORE_TEMPLATES,
    BALANCED_TEMPLATES,
    _translation_cache,
)


class TestTranslateToEnglish:
    """Tests for translate_to_english function."""

    def test_uses_cache(self):
        """Test that cached translations are reused."""
        # Pre-populate cache
        _translation_cache["Test German"] = "Cached English"

        result = translate_to_english("Test German", use_cache=True)

        assert result == "Cached English"

    def test_bypasses_cache_when_disabled(self):
        """Test that cache can be bypassed."""
        _translation_cache["Test German"] = "Cached English"

        with patch("recommendation_problems.get_client") as mock_client:
            mock_response = MagicMock()
            mock_response.text = "Fresh English"
            mock_client.return_value.generate.return_value = mock_response

            result = translate_to_english("Test German", use_cache=False)

            assert result == "Fresh English"
            mock_client.return_value.generate.assert_called_once()

    def test_returns_original_on_error(self):
        """Test graceful fallback on translation error."""
        with patch("recommendation_problems.get_client") as mock_client:
            mock_client.return_value.generate.side_effect = Exception("API Error")

            result = translate_to_english("German Text", use_cache=False)

            assert result == "German Text"


class TestSortProblemsByMode:
    """Tests for sort_problems_by_mode function."""

    @pytest.fixture
    def sample_problems(self):
        return [
            {"problem_id": "p1", "evidence_count": 5},
            {"problem_id": "p2", "evidence_count": 0},
            {"problem_id": "p3", "evidence_count": 10},
            {"problem_id": "p4", "evidence_count": 2},
        ]

    def test_deepen_mode_high_evidence_first(self, sample_problems):
        """Deepen mode should prioritize high evidence problems."""
        result = sort_problems_by_mode(sample_problems, "deepen")

        evidence_counts = [p["evidence_count"] for p in result]
        assert evidence_counts == [10, 5, 2, 0]

    def test_explore_mode_low_evidence_first(self, sample_problems):
        """Explore mode should prioritize low evidence problems."""
        result = sort_problems_by_mode(sample_problems, "explore")

        evidence_counts = [p["evidence_count"] for p in result]
        assert evidence_counts == [0, 2, 5, 10]

    def test_balanced_mode_interleaves(self, sample_problems):
        """Balanced mode should interleave high and low evidence."""
        result = sort_problems_by_mode(sample_problems, "balanced")

        # Should alternate between high and low
        evidence_counts = [p["evidence_count"] for p in result]
        # First should be from high end, second from low end
        assert evidence_counts[0] > evidence_counts[1] or evidence_counts[0] == evidence_counts[1]


class TestGetEvidenceKeywords:
    """Tests for get_evidence_keywords function."""

    def test_extracts_from_source_titles(self):
        """Test keyword extraction from evidence source titles."""
        problem = {
            "evidence": [
                {"source_title": "The Culture Map by Erin Meyer"},
                {"source_title": "Leadership Across Boundaries"},
            ]
        }

        keywords = get_evidence_keywords(problem, max_keywords=5)

        assert len(keywords) <= 5
        assert any("Culture" in k for k in keywords)

    def test_extracts_author_names(self):
        """Test that author names are included."""
        problem = {
            "evidence": [
                {"source_title": "Some Book", "author": "Daniel Kahneman"},
            ]
        }

        keywords = get_evidence_keywords(problem, max_keywords=5)

        assert "Daniel" in keywords

    def test_limits_keywords(self):
        """Test that max_keywords is respected."""
        problem = {
            "evidence": [
                {"source_title": "Very Long Title With Many Words Here"},
                {"source_title": "Another Title With Different Words"},
                {"source_title": "Third Title Adding More Keywords"},
            ]
        }

        keywords = get_evidence_keywords(problem, max_keywords=3)

        assert len(keywords) <= 3

    def test_handles_empty_evidence(self):
        """Test handling of problems with no evidence."""
        problem = {"evidence": []}

        keywords = get_evidence_keywords(problem)

        assert keywords == []


class TestGenerateProblemQueries:
    """Tests for generate_problem_queries function."""

    @pytest.fixture
    def mock_problems(self):
        return [
            {
                "problem_id": "prob_1",
                "problem": "Test Problem High Evidence",
                "status": "active",
                "evidence_count": 10,
                "evidence": [{"source_title": "Test Source"}],
            },
            {
                "problem_id": "prob_2",
                "problem": "Test Problem Low Evidence",
                "status": "active",
                "evidence_count": 0,
                "evidence": [],
            },
        ]

    def test_generates_queries_for_all_problems(self, mock_problems):
        """Test that queries are generated for multiple problems."""
        with patch("recommendation_problems.get_active_problems") as mock_get:
            mock_get.return_value = mock_problems
            with patch("recommendation_problems.translate_to_english") as mock_trans:
                mock_trans.side_effect = lambda x, **kw: f"EN: {x}"

                queries = generate_problem_queries(mode="balanced", max_queries=4)

                assert len(queries) <= 4
                assert any(q["problem_id"] == "prob_1" for q in queries)
                assert any(q["problem_id"] == "prob_2" for q in queries)

    def test_respects_max_queries(self, mock_problems):
        """Test that max_queries limit is respected."""
        with patch("recommendation_problems.get_active_problems") as mock_get:
            mock_get.return_value = mock_problems * 5  # Many problems
            with patch("recommendation_problems.translate_to_english") as mock_trans:
                mock_trans.side_effect = lambda x, **kw: f"EN: {x}"

                queries = generate_problem_queries(max_queries=3)

                assert len(queries) == 3

    def test_deepen_mode_uses_deepen_templates(self, mock_problems):
        """Test that deepen mode uses appropriate templates."""
        with patch("recommendation_problems.get_active_problems") as mock_get:
            mock_get.return_value = mock_problems
            with patch("recommendation_problems.translate_to_english") as mock_trans:
                mock_trans.side_effect = lambda x, **kw: "translated problem"

                queries = generate_problem_queries(mode="deepen", max_queries=2)

                # Check that deepen-style keywords appear
                all_queries = " ".join(q["query"] for q in queries)
                assert any(
                    keyword in all_queries.lower()
                    for keyword in ["advanced", "deep dive", "best practices", "masterclass"]
                )

    def test_explore_mode_uses_explore_templates(self, mock_problems):
        """Test that explore mode uses appropriate templates."""
        with patch("recommendation_problems.get_active_problems") as mock_get:
            mock_get.return_value = mock_problems
            with patch("recommendation_problems.translate_to_english") as mock_trans:
                mock_trans.side_effect = lambda x, **kw: "translated problem"

                queries = generate_problem_queries(mode="explore", max_queries=2)

                # Check that explore-style keywords appear
                all_queries = " ".join(q["query"] for q in queries)
                assert any(
                    keyword in all_queries.lower()
                    for keyword in ["getting started", "perspectives", "contrarian", "mistakes"]
                )

    def test_includes_problem_metadata(self, mock_problems):
        """Test that queries include problem metadata."""
        with patch("recommendation_problems.get_active_problems") as mock_get:
            mock_get.return_value = mock_problems
            with patch("recommendation_problems.translate_to_english") as mock_trans:
                mock_trans.side_effect = lambda x, **kw: f"EN: {x}"

                queries = generate_problem_queries(max_queries=2)

                for q in queries:
                    assert "problem_id" in q
                    assert "problem_text" in q
                    assert "problem_en" in q
                    assert "mode" in q
                    assert "evidence_count" in q

    def test_handles_empty_problems(self):
        """Test handling when no problems exist."""
        with patch("recommendation_problems.get_active_problems") as mock_get:
            mock_get.return_value = []

            queries = generate_problem_queries()

            assert queries == []


class TestFormatQueryForTavily:
    """Tests for format_query_for_tavily function."""

    def test_removes_quotes(self):
        """Test that quotes are removed."""
        query_dict = {"query": 'Test "quoted" query'}

        result = format_query_for_tavily(query_dict)

        assert '"' not in result
        assert result == "Test quoted query"

    def test_strips_whitespace(self):
        """Test that whitespace is stripped."""
        query_dict = {"query": "  Test query  "}

        result = format_query_for_tavily(query_dict)

        assert result == "Test query"

    def test_handles_missing_query(self):
        """Test handling of missing query field."""
        query_dict = {}

        result = format_query_for_tavily(query_dict)

        assert result == ""


class TestQueryTemplates:
    """Tests for query template definitions."""

    def test_deepen_templates_have_placeholder(self):
        """Test that deepen templates have {problem} placeholder."""
        for template in DEEPEN_TEMPLATES:
            assert "{problem}" in template

    def test_explore_templates_have_placeholder(self):
        """Test that explore templates have {problem} placeholder."""
        for template in EXPLORE_TEMPLATES:
            assert "{problem}" in template

    def test_balanced_templates_have_placeholder(self):
        """Test that balanced templates have {problem} placeholder."""
        for template in BALANCED_TEMPLATES:
            assert "{problem}" in template

    def test_templates_are_distinct(self):
        """Test that template sets are distinct."""
        assert set(DEEPEN_TEMPLATES) != set(EXPLORE_TEMPLATES)
        assert set(DEEPEN_TEMPLATES) != set(BALANCED_TEMPLATES)


class TestFilterProblemsByTopic:
    """Tests for filter_problems_by_topic (PR: improve-recommendation-filters)."""

    PROBLEMS = [
        {"problem_id": "p1", "problem": "How do LLM agents handle tool calling?", "tags": [], "category": ""},
        {"problem_id": "p2", "problem": "Wie baue ich starke Entwickler-Teams?", "tags": ["engineering"], "category": ""},
        {"problem_id": "p3", "problem": "Wie esse ich gesünder?", "tags": ["health"], "category": "lifestyle"},
        {"problem_id": "p4", "problem": "What makes platform engineering scale?", "tags": ["software"], "category": ""},
    ]

    def test_empty_filter_returns_all(self):
        """Empty topic_filter must return all problems unchanged (opt-in, not opt-out)."""
        result = filter_problems_by_topic(self.PROBLEMS, [])
        assert result == self.PROBLEMS

    def test_matches_problem_text(self):
        """Keyword match in problem text."""
        result = filter_problems_by_topic(self.PROBLEMS, ["LLM"])
        assert len(result) == 1
        assert result[0]["problem_id"] == "p1"

    def test_matches_tags(self):
        """Keyword match in tags list."""
        result = filter_problems_by_topic(self.PROBLEMS, ["software"])
        assert any(p["problem_id"] == "p4" for p in result)

    def test_case_insensitive(self):
        """Matching must be case-insensitive."""
        result_lower = filter_problems_by_topic(self.PROBLEMS, ["llm"])
        result_upper = filter_problems_by_topic(self.PROBLEMS, ["LLM"])
        assert [p["problem_id"] for p in result_lower] == [p["problem_id"] for p in result_upper]

    def test_non_tech_problem_excluded(self):
        """Health/lifestyle problem should not match tech keywords."""
        result = filter_problems_by_topic(self.PROBLEMS, ["software", "engineering", "LLM", "agent"])
        ids = [p["problem_id"] for p in result]
        assert "p3" not in ids  # "gesünder / health / lifestyle" — no match

    def test_german_problem_matches_german_keyword(self):
        """German problems must be matchable with German keywords."""
        result = filter_problems_by_topic(self.PROBLEMS, ["Entwickler"])
        assert len(result) == 1
        assert result[0]["problem_id"] == "p2"

    def test_multiple_keywords_union(self):
        """Multiple keywords use OR logic — any match includes the problem."""
        result = filter_problems_by_topic(self.PROBLEMS, ["LLM", "platform"])
        ids = [p["problem_id"] for p in result]
        assert "p1" in ids
        assert "p4" in ids
        assert "p3" not in ids
