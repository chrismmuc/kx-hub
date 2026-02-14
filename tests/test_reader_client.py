"""
Unit tests for Reader API client (Story 13.1).

Tests:
- Document fetching with pagination
- HTML to clean text conversion
- Word count calculation
- Rate limiting behavior
- Error handling and retries
- Raw document storage
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from src.ingest.reader_client import (
    ReadwiseReaderClient,
    ReaderDocument,
)


class TestReaderDocument:
    """Tests for ReaderDocument class."""

    def test_init_with_full_metadata(self):
        """Test ReaderDocument initialization with complete metadata."""
        raw_data = {
            "id": "doc_123",
            "title": "Test Article",
            "author": "John Doe",
            "source_url": "https://example.com/article",
            "url": "https://reader.example.com/doc/123",
            "tags": ["test", "kx-auto-ingest"],
            "reading_progress": 15,  # minutes
            "category": "article",
            "created_at": "2026-02-14T10:00:00Z",
            "updated_at": "2026-02-14T12:00:00Z",
            "html": "<p>Test content</p>",
            "word_count": 500,
        }
        clean_text = "Test content"
        word_count = 2

        doc = ReaderDocument(raw_data, clean_text, word_count)

        assert doc.id == "doc_123"
        assert doc.title == "Test Article"
        assert doc.author == "John Doe"
        assert doc.source_url == "https://example.com/article"
        assert doc.tags == ["test", "kx-auto-ingest"]
        assert doc.reading_time == 15
        assert doc.category == "article"
        assert doc.clean_text == "Test content"
        assert doc.word_count == 2

    def test_init_with_minimal_metadata(self):
        """Test ReaderDocument with minimal metadata."""
        raw_data = {"id": "doc_456"}
        clean_text = "Minimal content"
        word_count = 2

        doc = ReaderDocument(raw_data, clean_text, word_count)

        assert doc.id == "doc_456"
        assert doc.title == "Untitled"
        assert doc.author is None
        assert doc.tags == []
        assert doc.word_count == 2

    def test_to_dict(self):
        """Test conversion to dictionary."""
        raw_data = {
            "id": "doc_789",
            "title": "Article",
            "author": "Jane",
            "source_url": "https://example.com",
        }
        clean_text = "Content"
        word_count = 1

        doc = ReaderDocument(raw_data, clean_text, word_count)
        result = doc.to_dict()

        assert result["id"] == "doc_789"
        assert result["title"] == "Article"
        assert result["clean_text"] == "Content"
        assert result["word_count"] == 1


class TestReadwiseReaderClient:
    """Tests for ReadwiseReaderClient."""

    @pytest.fixture
    def client(self):
        """Create client instance for testing."""
        return ReadwiseReaderClient(api_key="test_api_key")

    @pytest.fixture
    def mock_storage_client(self):
        """Create mock GCS storage client."""
        return MagicMock()

    def test_init(self, client):
        """Test client initialization."""
        assert client.api_key == "test_api_key"
        assert "Authorization" in client.session.headers
        assert client.session.headers["Authorization"] == "Token test_api_key"

    def test_html_to_clean_text_basic(self, client):
        """Test basic HTML to text conversion."""
        html = "<p>Hello world</p><p>Second paragraph</p>"
        result = client.html_to_clean_text(html)
        assert "Hello world" in result
        assert "Second paragraph" in result

    def test_html_to_clean_text_removes_scripts(self, client):
        """Test removal of script tags."""
        html = """
        <div>
            <p>Visible content</p>
            <script>alert('evil')</script>
            <p>More content</p>
        </div>
        """
        result = client.html_to_clean_text(html)
        assert "Visible content" in result
        assert "More content" in result
        assert "alert" not in result
        assert "script" not in result.lower()

    def test_html_to_clean_text_removes_nav(self, client):
        """Test removal of navigation elements."""
        html = """
        <nav>Skip to main content</nav>
        <header>Site header</header>
        <article>
            <p>Main content here</p>
        </article>
        <footer>Copyright 2026</footer>
        """
        result = client.html_to_clean_text(html)
        assert "Main content here" in result
        assert "Skip to main" not in result
        assert "Site header" not in result
        assert "Copyright" not in result

    def test_html_to_clean_text_normalizes_whitespace(self, client):
        """Test whitespace normalization."""
        html = "<p>Text   with     lots\n\n\nof\t\twhitespace</p>"
        result = client.html_to_clean_text(html)
        assert result == "Text with lots of whitespace"

    def test_html_to_clean_text_empty(self, client):
        """Test with empty HTML."""
        assert client.html_to_clean_text("") == ""
        assert client.html_to_clean_text(None) == ""

    def test_calculate_word_count(self, client):
        """Test word count calculation."""
        assert client.calculate_word_count("one two three") == 3
        assert client.calculate_word_count("single") == 1
        assert client.calculate_word_count("") == 0
        assert client.calculate_word_count(None) == 0
        assert client.calculate_word_count("  multiple   spaces  ") == 2

    @patch.object(ReadwiseReaderClient, "_make_request")
    def test_fetch_tagged_documents_single_page(self, mock_request, client):
        """Test fetching documents with single page response."""
        mock_request.return_value = {
            "results": [
                {"id": "doc1", "title": "Article 1"},
                {"id": "doc2", "title": "Article 2"},
            ],
            "nextPageCursor": None,
        }

        results = client.fetch_tagged_documents(tag="test-tag")

        assert len(results) == 2
        assert results[0]["id"] == "doc1"
        assert results[1]["id"] == "doc2"
        mock_request.assert_called_once()

    @patch.object(ReadwiseReaderClient, "_make_request")
    def test_fetch_tagged_documents_pagination(self, mock_request, client):
        """Test fetching documents with pagination."""
        # Mock two pages of results
        mock_request.side_effect = [
            {
                "results": [{"id": "doc1"}, {"id": "doc2"}],
                "nextPageCursor": "cursor_abc",
            },
            {
                "results": [{"id": "doc3"}],
                "nextPageCursor": None,
            },
        ]

        results = client.fetch_tagged_documents(tag="test-tag")

        assert len(results) == 3
        assert results[0]["id"] == "doc1"
        assert results[2]["id"] == "doc3"
        assert mock_request.call_count == 2

    def test_extract_document_content(self, client):
        """Test extracting content from raw document."""
        raw_doc = {
            "id": "doc_abc",
            "title": "Test Article",
            "html": "<p>Article content here</p>",
            "word_count": 3,
        }

        result = client.extract_document_content(raw_doc)

        assert isinstance(result, ReaderDocument)
        assert result.id == "doc_abc"
        assert result.title == "Test Article"
        assert "Article content here" in result.clean_text
        assert result.word_count == 3

    def test_extract_document_content_calculates_word_count(self, client):
        """Test word count calculation when not provided by API."""
        raw_doc = {
            "id": "doc_xyz",
            "title": "Test",
            "html": "<p>one two three four</p>",
        }

        result = client.extract_document_content(raw_doc)

        assert result.word_count == 4  # Calculated from content

    def test_store_raw_document(self, client, mock_storage_client):
        """Test storing raw document in GCS."""
        client.storage_client = mock_storage_client
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        raw_data = {"id": "doc_123", "title": "Test"}
        doc = ReaderDocument(raw_data, "content", 1)

        uri = client.store_raw_document("test-bucket", doc)

        assert uri == "gs://test-bucket/reader-doc-doc_123.json"
        mock_storage_client.bucket.assert_called_once_with("test-bucket")
        mock_bucket.blob.assert_called_once_with("reader-doc-doc_123.json")
        mock_blob.upload_from_string.assert_called_once()

    def test_store_raw_document_no_storage_client(self, client):
        """Test storing without storage client raises error."""
        doc = ReaderDocument({"id": "test"}, "content", 1)

        with pytest.raises(ValueError, match="storage_client not configured"):
            client.store_raw_document("bucket", doc)

    def test_rate_limit_enforcement(self, client):
        """Test rate limiting delays requests appropriately."""
        # Simulate hitting the rate limit
        for _ in range(20):
            client._general_request_times.append(time.time())

        start = time.time()
        client._rate_limit("general")
        elapsed = time.time() - start

        # Should have waited because we hit the limit
        assert elapsed > 0

    def test_rate_limit_allows_under_limit(self, client):
        """Test rate limiting doesn't delay when under limit."""
        # Only 5 requests in the last minute
        for _ in range(5):
            client._general_request_times.append(time.time())

        start = time.time()
        client._rate_limit("general")
        elapsed = time.time() - start

        # Should not wait
        assert elapsed < 0.1

    @patch.object(ReadwiseReaderClient, "_make_request")
    @patch.object(ReadwiseReaderClient, "store_raw_document")
    @patch.object(ReadwiseReaderClient, "extract_document_content")
    def test_fetch_and_process_documents(
        self, mock_extract, mock_store, mock_request, client, mock_storage_client
    ):
        """Test end-to-end document fetching and processing."""
        client.storage_client = mock_storage_client

        # Mock API response
        mock_request.return_value = {
            "results": [
                {"id": "doc1", "title": "Article 1", "html": "<p>Content 1</p>"},
                {"id": "doc2", "title": "Article 2", "html": "<p>Content 2</p>"},
            ],
            "nextPageCursor": None,
        }

        # Mock document extraction
        mock_doc1 = Mock(spec=ReaderDocument)
        mock_doc1.id = "doc1"
        mock_doc1.title = "Article 1"
        mock_doc1.word_count = 10
        mock_doc1.clean_text = "Content 1"

        mock_doc2 = Mock(spec=ReaderDocument)
        mock_doc2.id = "doc2"
        mock_doc2.title = "Article 2"
        mock_doc2.word_count = 15
        mock_doc2.clean_text = "Content 2"

        mock_extract.side_effect = [mock_doc1, mock_doc2]

        # Mock storage
        mock_store.return_value = "gs://bucket/file.json"

        # Execute
        results = client.fetch_and_process_documents(
            tag="test-tag",
            store_raw=True,
            raw_bucket="test-bucket",
        )

        # Verify
        assert len(results) == 2
        assert mock_extract.call_count == 2
        assert mock_store.call_count == 2
        mock_store.assert_any_call("test-bucket", mock_doc1)
        mock_store.assert_any_call("test-bucket", mock_doc2)

    def test_fetch_and_process_requires_bucket_when_storing(self, client):
        """Test that raw_bucket is required when store_raw=True."""
        with pytest.raises(ValueError, match="raw_bucket required"):
            client.fetch_and_process_documents(
                tag="test-tag",
                store_raw=True,
                raw_bucket=None,
            )

    @patch.object(ReadwiseReaderClient, "_make_request")
    def test_update_document_tags_add_and_remove(self, mock_request, client):
        """Test tag update with both add and remove operations."""
        mock_request.return_value = {"id": "doc_123"}

        client.update_document_tags(
            document_id="doc_123",
            current_tags=["kx-auto-ingest", "tech", "ai"],
            remove_tags=["kx-auto-ingest"],
            add_tags=["kx-processed"],
        )

        mock_request.assert_called_once_with(
            "PATCH",
            "/update/doc_123/",
            endpoint_type="general",
            json={"tags": ["ai", "kx-processed", "tech"]},
        )

    @patch.object(ReadwiseReaderClient, "_make_request")
    def test_update_document_tags_add_only(self, mock_request, client):
        """Test tag update with only add — existing tags preserved."""
        mock_request.return_value = {"id": "doc_456"}

        client.update_document_tags(
            document_id="doc_456",
            current_tags=["existing-tag"],
            add_tags=["new-tag"],
        )

        mock_request.assert_called_once_with(
            "PATCH",
            "/update/doc_456/",
            endpoint_type="general",
            json={"tags": ["existing-tag", "new-tag"]},
        )

    @patch.object(ReadwiseReaderClient, "_make_request")
    def test_update_document_tags_empty_operations(self, mock_request, client):
        """Test tag update with no add/remove produces same tag set."""
        mock_request.return_value = {"id": "doc_789"}

        client.update_document_tags(
            document_id="doc_789",
            current_tags=["tag-a", "tag-b"],
        )

        mock_request.assert_called_once_with(
            "PATCH",
            "/update/doc_789/",
            endpoint_type="general",
            json={"tags": ["tag-a", "tag-b"]},
        )
