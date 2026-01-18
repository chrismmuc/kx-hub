"""Tests for date_extractor module."""

import unittest
from unittest.mock import patch, MagicMock

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "mcp_server"))

from date_extractor import (
    extract_date_from_html,
    _extract_date_from_jsonld,
    fetch_and_extract_date,
    extract_dates_batch,
)


class TestExtractDateFromJsonLD(unittest.TestCase):
    """Tests for JSON-LD date extraction."""

    def test_extract_from_direct_property(self):
        """Should extract datePublished from direct property."""
        data = {"datePublished": "2025-01-15T10:30:00Z"}
        result = _extract_date_from_jsonld(data)
        self.assertEqual(result, "2025-01-15T10:30:00Z")

    def test_extract_from_graph(self):
        """Should extract date from @graph array."""
        data = {
            "@graph": [
                {"@type": "WebPage"},
                {"@type": "Article", "datePublished": "2025-01-10"},
            ]
        }
        result = _extract_date_from_jsonld(data)
        self.assertEqual(result, "2025-01-10")

    def test_extract_from_list(self):
        """Should handle list of JSON-LD objects."""
        data = [
            {"@type": "Organization"},
            {"@type": "Article", "datePublished": "2024-12-25"},
        ]
        result = _extract_date_from_jsonld(data)
        self.assertEqual(result, "2024-12-25")

    def test_priority_datePublished_over_dateCreated(self):
        """Should prefer datePublished over dateCreated."""
        data = {
            "datePublished": "2025-01-15",
            "dateCreated": "2025-01-01",
        }
        result = _extract_date_from_jsonld(data)
        self.assertEqual(result, "2025-01-15")

    def test_returns_none_for_empty(self):
        """Should return None for empty data."""
        self.assertIsNone(_extract_date_from_jsonld({}))
        self.assertIsNone(_extract_date_from_jsonld([]))
        self.assertIsNone(_extract_date_from_jsonld(None))


class TestExtractDateFromHTML(unittest.TestCase):
    """Tests for HTML date extraction."""

    def test_extract_from_jsonld_script(self):
        """Should extract date from JSON-LD script tag."""
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {"@type": "Article", "datePublished": "2025-01-15T08:00:00Z"}
            </script>
        </head>
        <body><p>Test</p></body>
        </html>
        """
        result = extract_date_from_html(html)
        self.assertEqual(result, "2025-01-15T08:00:00Z")

    def test_extract_from_meta_article_published_time(self):
        """Should extract date from article:published_time meta tag."""
        html = """
        <html>
        <head>
            <meta property="article:published_time" content="2025-01-14T12:00:00Z">
        </head>
        <body><p>Test</p></body>
        </html>
        """
        result = extract_date_from_html(html)
        self.assertEqual(result, "2025-01-14T12:00:00Z")

    def test_extract_from_time_element(self):
        """Should extract date from time element with datetime attribute."""
        html = """
        <html>
        <body>
            <article>
                <time datetime="2025-01-13">January 13, 2025</time>
                <p>Article content</p>
            </article>
        </body>
        </html>
        """
        result = extract_date_from_html(html)
        self.assertEqual(result, "2025-01-13")

    def test_jsonld_priority_over_meta(self):
        """JSON-LD should take priority over meta tags."""
        html = """
        <html>
        <head>
            <meta property="article:published_time" content="2025-01-01">
            <script type="application/ld+json">
            {"datePublished": "2025-01-15"}
            </script>
        </head>
        </html>
        """
        result = extract_date_from_html(html)
        self.assertEqual(result, "2025-01-15")

    def test_returns_none_for_no_date(self):
        """Should return None when no date found."""
        html = "<html><body><p>No date here</p></body></html>"
        result = extract_date_from_html(html)
        self.assertIsNone(result)

    def test_handles_malformed_jsonld(self):
        """Should handle malformed JSON-LD gracefully."""
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {invalid json}
            </script>
            <meta property="article:published_time" content="2025-01-14">
        </head>
        </html>
        """
        result = extract_date_from_html(html)
        self.assertEqual(result, "2025-01-14")


class TestFetchAndExtractDate(unittest.TestCase):
    """Tests for URL fetching and date extraction."""

    @patch("date_extractor.requests.get")
    def test_successful_extraction(self, mock_get):
        """Should fetch URL and extract date."""
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <head>
            <script type="application/ld+json">
            {"datePublished": "2025-01-15"}
            </script>
        </head>
        </html>
        """
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_and_extract_date("https://example.com/article")
        self.assertEqual(result, "2025-01-15")

    @patch("date_extractor.requests.get")
    def test_timeout_returns_none(self, mock_get):
        """Should return None on timeout."""
        import requests

        mock_get.side_effect = requests.exceptions.Timeout()

        result = fetch_and_extract_date("https://example.com/slow")
        self.assertIsNone(result)

    @patch("date_extractor.requests.get")
    def test_http_error_returns_none(self, mock_get):
        """Should return None on HTTP error."""
        import requests

        mock_get.side_effect = requests.exceptions.HTTPError("404")

        result = fetch_and_extract_date("https://example.com/notfound")
        self.assertIsNone(result)


class TestExtractDatesBatch(unittest.TestCase):
    """Tests for batch date extraction."""

    @patch("date_extractor.fetch_and_extract_date")
    def test_batch_extraction(self, mock_fetch):
        """Should extract dates from multiple URLs in parallel."""
        mock_fetch.side_effect = [
            "2025-01-15",
            None,  # Failed extraction
            "2025-01-10",
        ]

        urls = [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]
        result = extract_dates_batch(urls)

        self.assertEqual(len(result), 2)
        self.assertEqual(result["https://example.com/a"], "2025-01-15")
        self.assertEqual(result["https://example.com/c"], "2025-01-10")
        self.assertNotIn("https://example.com/b", result)

    def test_empty_urls_returns_empty_dict(self):
        """Should return empty dict for empty URL list."""
        result = extract_dates_batch([])
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
