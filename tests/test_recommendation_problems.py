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
    generate_evidence_queries,
    format_query_for_tavily,
    filter_problems_by_topic,
    _build_evidence_summary,
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
        """Test that deepen mode uses appropriate templates (template fallback)."""
        with patch("recommendation_problems.get_active_problems") as mock_get:
            mock_get.return_value = mock_problems
            with patch("recommendation_problems.translate_to_english") as mock_trans, \
                 patch("recommendation_problems.generate_evidence_queries", return_value=[]):
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


class TestBuildEvidenceSummary:
    """Tests for _build_evidence_summary (Epic 14)."""

    def test_full_evidence_item(self):
        """Test formatting with title, author, and takeaway."""
        evidence = [
            {"source_title": "The Culture Map", "author": "Erin Meyer", "takeaways": ["cultural dimensions"]}
        ]
        result = _build_evidence_summary(evidence)
        assert result == "- The Culture Map (Erin Meyer) — cultural dimensions"

    def test_title_and_author_only(self):
        """Test formatting without takeaways."""
        evidence = [{"source_title": "Deep Work", "author": "Cal Newport", "takeaways": []}]
        result = _build_evidence_summary(evidence)
        assert result == "- Deep Work (Cal Newport)"

    def test_title_and_takeaway_only(self):
        """Test formatting without author."""
        evidence = [{"source_title": "Some Article", "takeaways": ["key insight"]}]
        result = _build_evidence_summary(evidence)
        assert result == "- Some Article — key insight"

    def test_title_only(self):
        """Test formatting with only title."""
        evidence = [{"source_title": "Minimal Source"}]
        result = _build_evidence_summary(evidence)
        assert result == "- Minimal Source"

    def test_missing_title_uses_unknown(self):
        """Test fallback when title is missing."""
        evidence = [{"author": "Someone"}]
        result = _build_evidence_summary(evidence)
        assert result == "- Unknown (Someone)"

    def test_caps_at_max_items(self):
        """Test that max_items is respected."""
        evidence = [{"source_title": f"Book {i}"} for i in range(10)]
        result = _build_evidence_summary(evidence, max_items=3)
        assert result.count("\n") == 2  # 3 lines = 2 newlines

    def test_empty_evidence(self):
        """Test with empty evidence list."""
        assert _build_evidence_summary([]) == ""

    def test_multiple_items(self):
        """Test formatting of multiple evidence items."""
        evidence = [
            {"source_title": "Book A", "author": "Author A", "takeaways": ["insight A"]},
            {"source_title": "Book B", "author": "Author B", "takeaways": ["insight B"]},
        ]
        result = _build_evidence_summary(evidence)
        lines = result.split("\n")
        assert len(lines) == 2
        assert "Book A" in lines[0]
        assert "Book B" in lines[1]


class TestGenerateEvidenceQueries:
    """Tests for generate_evidence_queries (Epic 14)."""

    def test_returns_parsed_queries(self):
        """Test successful LLM query generation."""
        evidence = [{"source_title": "Test Book", "author": "Author", "takeaways": ["insight"]}]

        with patch("recommendation_problems.get_client") as mock_client:
            mock_response = MagicMock()
            mock_response.text = "couples therapy repair rituals research\nparenting division labor satisfaction study"
            mock_client.return_value.generate.return_value = mock_response

            result = generate_evidence_queries("test problem", evidence, "deepen", n_queries=2)

            assert len(result) == 2
            assert "couples therapy" in result[0]
            assert "parenting division" in result[1]

    def test_caps_at_n_queries(self):
        """Test that output is capped at n_queries even if LLM returns more."""
        evidence = [{"source_title": "Book"}]

        with patch("recommendation_problems.get_client") as mock_client:
            mock_response = MagicMock()
            mock_response.text = "query one\nquery two\nquery three\nquery four"
            mock_client.return_value.generate.return_value = mock_response

            result = generate_evidence_queries("problem", evidence, "deepen", n_queries=2)

            assert len(result) == 2

    def test_strips_numbering_from_output(self):
        """Test that LLM numbering prefixes are stripped."""
        evidence = [{"source_title": "Book"}]

        with patch("recommendation_problems.get_client") as mock_client:
            mock_response = MagicMock()
            mock_response.text = "1. first query here\n2) second query here"
            mock_client.return_value.generate.return_value = mock_response

            result = generate_evidence_queries("problem", evidence, "deepen", n_queries=2)

            assert result[0] == "first query here"
            assert result[1] == "second query here"

    def test_returns_empty_on_llm_error(self):
        """Test graceful fallback on LLM error."""
        evidence = [{"source_title": "Book"}]

        with patch("recommendation_problems.get_client") as mock_client:
            mock_client.return_value.generate.side_effect = Exception("API down")

            result = generate_evidence_queries("problem", evidence, "deepen")

            assert result == []

    def test_returns_empty_on_empty_response(self):
        """Test fallback when LLM returns empty/whitespace."""
        evidence = [{"source_title": "Book"}]

        with patch("recommendation_problems.get_client") as mock_client:
            mock_response = MagicMock()
            mock_response.text = "   \n  \n  "
            mock_client.return_value.generate.return_value = mock_response

            result = generate_evidence_queries("problem", evidence, "deepen")

            assert result == []

    def test_uses_correct_generation_config(self):
        """Test that temperature and max_tokens are set correctly."""
        evidence = [{"source_title": "Book"}]

        with patch("recommendation_problems.get_client") as mock_client:
            mock_response = MagicMock()
            mock_response.text = "some query"
            mock_client.return_value.generate.return_value = mock_response

            generate_evidence_queries("problem", evidence, "deepen")

            call_args = mock_client.return_value.generate.call_args
            config = call_args.kwargs.get("config") or call_args[1].get("config")
            assert config.temperature == 0.3
            assert config.max_output_tokens == 200


class TestGenerateProblemQueriesWithLLM:
    """Tests for LLM integration in generate_problem_queries (Epic 14)."""

    @pytest.fixture
    def problems_with_evidence(self):
        return [
            {
                "problem_id": "prob_1",
                "problem": "Problem mit Evidence",
                "status": "active",
                "evidence_count": 10,
                "evidence": [
                    {"source_title": "Book A", "author": "Author A", "takeaways": ["insight"]},
                ],
            },
        ]

    @pytest.fixture
    def problems_without_evidence(self):
        return [
            {
                "problem_id": "prob_2",
                "problem": "Problem ohne Evidence",
                "status": "active",
                "evidence_count": 0,
                "evidence": [],
            },
        ]

    def test_uses_llm_for_problems_with_evidence(self, problems_with_evidence):
        """Test that LLM path is used when evidence exists."""
        with patch("recommendation_problems.get_active_problems") as mock_get, \
             patch("recommendation_problems.translate_to_english") as mock_trans, \
             patch("recommendation_problems.generate_evidence_queries") as mock_llm:
            mock_get.return_value = problems_with_evidence
            mock_trans.side_effect = lambda x, **kw: f"EN: {x}"
            mock_llm.return_value = ["llm query one", "llm query two"]

            queries = generate_problem_queries(mode="deepen", max_queries=4)

            assert len(queries) == 2
            assert all(q["query_method"] == "llm" for q in queries)
            assert queries[0]["query"] == "llm query one"

    def test_uses_templates_for_problems_without_evidence(self, problems_without_evidence):
        """Test that template path is used when no evidence exists."""
        with patch("recommendation_problems.get_active_problems") as mock_get, \
             patch("recommendation_problems.translate_to_english") as mock_trans:
            mock_get.return_value = problems_without_evidence
            mock_trans.side_effect = lambda x, **kw: f"EN: {x}"

            queries = generate_problem_queries(mode="explore", max_queries=2)

            assert len(queries) == 2
            assert all(q["query_method"] == "template" for q in queries)

    def test_falls_back_to_templates_on_llm_failure(self, problems_with_evidence):
        """Test template fallback when LLM returns empty."""
        with patch("recommendation_problems.get_active_problems") as mock_get, \
             patch("recommendation_problems.translate_to_english") as mock_trans, \
             patch("recommendation_problems.generate_evidence_queries") as mock_llm:
            mock_get.return_value = problems_with_evidence
            mock_trans.side_effect = lambda x, **kw: f"EN: {x}"
            mock_llm.return_value = []  # LLM failed

            queries = generate_problem_queries(mode="deepen", max_queries=2)

            assert len(queries) == 2
            assert all(q["query_method"] == "template" for q in queries)

    def test_mixed_problems_use_both_methods(self):
        """Test that problems with evidence use LLM, without use templates."""
        mixed = [
            {
                "problem_id": "p1", "problem": "With evidence",
                "status": "active", "evidence_count": 5,
                "evidence": [{"source_title": "Book"}],
            },
            {
                "problem_id": "p2", "problem": "No evidence",
                "status": "active", "evidence_count": 0,
                "evidence": [],
            },
        ]
        with patch("recommendation_problems.get_active_problems") as mock_get, \
             patch("recommendation_problems.translate_to_english") as mock_trans, \
             patch("recommendation_problems.generate_evidence_queries") as mock_llm:
            mock_get.return_value = mixed
            mock_trans.side_effect = lambda x, **kw: f"EN: {x}"
            mock_llm.return_value = ["llm query"]

            queries = generate_problem_queries(mode="balanced", max_queries=4)

            methods = {q["problem_id"]: q["query_method"] for q in queries}
            assert methods.get("p1") == "llm"
            assert methods.get("p2") == "template"

    def test_query_method_field_always_present(self):
        """Test that query_method field exists in all queries."""
        problems = [
            {
                "problem_id": "p1", "problem": "Test",
                "status": "active", "evidence_count": 0, "evidence": [],
            },
        ]
        with patch("recommendation_problems.get_active_problems") as mock_get, \
             patch("recommendation_problems.translate_to_english") as mock_trans:
            mock_get.return_value = problems
            mock_trans.side_effect = lambda x, **kw: x

            queries = generate_problem_queries(max_queries=2)

            for q in queries:
                assert "query_method" in q
                assert q["query_method"] in ("llm", "template")
