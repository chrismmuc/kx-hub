"""
Unit tests for the embed Cloud Function (Story 1.3+).

Tests cover:
- Frontmatter parsing (valid, missing fields, malformed)
- Vertex AI embedding generation
- Firestore document writes with vector embeddings
- API error handling (429 rate limit, 500 server error)
- Retry logic with exponential backoff
- Edge cases (empty content, large files, Unicode)
"""

import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

from google.api_core import exceptions
from google.api_core.exceptions import NotFound


class TestFrontmatterParser(unittest.TestCase):
    """Test frontmatter parsing functionality."""

    def test_parse_valid_frontmatter(self):
        """AC 6: Parse frontmatter with all required fields."""
        from src.embed.main import parse_markdown

        markdown_content = """---
id: '41094950'
title: Test Book
author: Test Author
source: kindle
url: https://readwise.io/bookreview/41094950
created_at: '2024-06-01T13:22:09.640Z'
updated_at: '2024-06-01T13:22:09.641Z'
tags: [parenting, psychology]
highlight_count: 3
user_book_id: 41094950
category: books
---

# Test Book

Test content here."""

        metadata, content = parse_markdown(markdown_content)

        self.assertEqual(metadata["id"], "41094950")
        self.assertEqual(metadata["title"], "Test Book")
        self.assertEqual(metadata["author"], "Test Author")
        self.assertEqual(metadata["url"], "https://readwise.io/bookreview/41094950")
        self.assertEqual(metadata["tags"], ["parenting", "psychology"])
        self.assertIn("# Test Book", content)

    def test_parse_missing_optional_fields(self):
        """AC 6: Gracefully handle missing optional fields (url, tags)."""
        from src.embed.main import parse_markdown

        markdown_content = """---
id: '12345'
title: Test Book
author: Test Author
source: kindle
created_at: '2024-06-01T13:22:09.640Z'
updated_at: '2024-06-01T13:22:09.641Z'
highlight_count: 1
user_book_id: 12345
category: books
---

Content here."""

        metadata, content = parse_markdown(markdown_content)

        self.assertEqual(metadata["id"], "12345")
        self.assertEqual(metadata["title"], "Test Book")
        self.assertIsNone(metadata.get("url"))
        self.assertEqual(metadata.get("tags", []), [])

    def test_parse_malformed_frontmatter(self):
        """AC 6: Handle malformed YAML frontmatter gracefully."""
        from src.embed.main import parse_markdown

        markdown_content = """---
id: '12345'
title: Test Book
invalid yaml here: [unclosed bracket
author: Test Author
---

Content here."""

        with self.assertRaises(ValueError):
            parse_markdown(markdown_content)

    def test_parse_missing_required_fields(self):
        """AC 6: Raise error if required fields are missing."""
        from src.embed.main import parse_markdown

        markdown_content = """---
title: Test Book
author: Test Author
---

Content here."""

        with self.assertRaises(ValueError):
            parse_markdown(markdown_content)

    def test_parse_empty_content(self):
        """Edge case: Empty markdown content after frontmatter."""
        from src.embed.main import parse_markdown

        markdown_content = """---
id: '12345'
title: Test Book
author: Test Author
source: kindle
created_at: '2024-06-01T13:22:09.640Z'
updated_at: '2024-06-01T13:22:09.641Z'
highlight_count: 0
user_book_id: 12345
category: books
---

"""

        metadata, content = parse_markdown(markdown_content)

        self.assertEqual(metadata["id"], "12345")
        self.assertEqual(content.strip(), "")

    def test_parse_unicode_content(self):
        """Edge case: Handle Unicode and special characters."""
        from src.embed.main import parse_markdown

        markdown_content = """---
id: '12345'
title: Test Book with 中文 and émojis 🎉
author: Test Author
source: kindle
created_at: '2024-06-01T13:22:09.640Z'
updated_at: '2024-06-01T13:22:09.641Z'
highlight_count: 1
user_book_id: 12345
category: books
---

Content with special chars: äöü ñ 中文 🎉"""

        metadata, content = parse_markdown(markdown_content)

        self.assertIn("中文", metadata["title"])
        self.assertIn("🎉", content)


class TestVertexAIEmbeddings(unittest.TestCase):
    """Test Vertex AI embeddings generation with rate limiting and retries."""

    @patch("src.embed.main.get_vertex_ai_client")
    def test_generate_embedding_success(self, mock_get_client):
        """AC 1: Generate embedding using Vertex AI API."""
        from src.embed.main import generate_embedding

        # Mock the Vertex AI embedding model
        mock_model = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1] * 768  # 768-dimensional vector
        mock_model.get_embeddings.return_value = [mock_embedding]
        mock_get_client.return_value = mock_model

        text = "Test content for embedding"
        embedding_vector = generate_embedding(text)

        self.assertEqual(len(embedding_vector), 768)
        self.assertEqual(embedding_vector[0], 0.1)
        mock_model.get_embeddings.assert_called_once_with(
            [text], output_dimensionality=768
        )

    @patch("src.embed.main.get_vertex_ai_client")
    @patch("time.sleep", return_value=None)
    def test_generate_embedding_rate_limit_retry(self, mock_sleep, mock_get_client):
        """AC 1: Retry with exponential backoff on 429 rate limit."""
        from google.api_core.exceptions import ResourceExhausted

        from src.embed.main import generate_embedding

        mock_model = MagicMock()
        # First call raises 429, second succeeds
        mock_embedding = MagicMock()
        mock_embedding.values = [0.2] * 768
        mock_model.get_embeddings.side_effect = [
            ResourceExhausted("Rate limit exceeded"),
            [mock_embedding],
        ]
        mock_get_client.return_value = mock_model

        text = "Test content"
        embedding_vector = generate_embedding(text)

        self.assertEqual(len(embedding_vector), 768)
        self.assertEqual(mock_model.get_embeddings.call_count, 2)
        mock_sleep.assert_called_once()  # Verify backoff was applied

    @patch("src.embed.main.get_vertex_ai_client")
    @patch("time.sleep", return_value=None)
    def test_generate_embedding_server_error_retry(self, mock_sleep, mock_get_client):
        """AC 1: Retry on 500 server error, log and raise after max retries."""
        from google.api_core.exceptions import InternalServerError

        from src.embed.main import generate_embedding

        mock_model = MagicMock()
        # All calls fail with 500 error
        mock_model.get_embeddings.side_effect = InternalServerError("Server error")
        mock_get_client.return_value = mock_model

        text = "Test content"

        with self.assertRaises(InternalServerError):
            generate_embedding(text)

        # Should retry 3 times (initial + 2 retries)
        self.assertEqual(mock_model.get_embeddings.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)  # 2 backoff sleeps


# Removed: TestVectorSearchWriter - embeddings now stored directly in Firestore


class TestFirestoreWriter(unittest.TestCase):
    """Test Firestore document writes."""

    @patch("src.embed.main.get_firestore_client")
    def test_write_document_success(self, mock_get_client):
        """AC 3: Write metadata to Firestore kb_items collection."""
        from src.embed.main import write_to_firestore

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        metadata = {
            "id": "41094950",
            "title": "Test Book",
            "author": "Test Author",
            "url": "https://readwise.io/bookreview/41094950",
            "tags": ["parenting"],
            "created_at": "2024-06-01T13:22:09.640Z",
            "updated_at": "2024-06-01T13:22:09.641Z",
        }

        result = write_to_firestore(
            metadata,
            content="Test content",
            content_hash="sha256:abc",
            run_id="run-1",
            embedding_status="complete",
        )

        self.assertTrue(result)

        # Verify Firestore document structure
        mock_db.collection.assert_called_once_with("kb_items")
        mock_db.collection().document.assert_called_once_with("41094950")
        mock_db.collection().document().set.assert_called_once()

        # Verify document data
        call_args = mock_db.collection().document().set.call_args
        doc_data = call_args[0][0]
        self.assertEqual(doc_data["title"], "Test Book")
        self.assertEqual(doc_data["authors"], ["Test Author"])
        self.assertEqual(doc_data["tags"], ["parenting"])
        self.assertIn("created_at", doc_data)
        self.assertIn("updated_at", doc_data)
        self.assertEqual(doc_data["content_hash"], "sha256:abc")
        self.assertEqual(doc_data["embedding_status"], "complete")
        self.assertEqual(doc_data["last_run_id"], "run-1")
        self.assertIn("last_embedded_at", doc_data)

    @patch("src.embed.main.get_firestore_client")
    def test_write_document_missing_optional_fields(self, mock_get_client):
        """AC 3: Handle missing optional fields (url, tags)."""
        from src.embed.main import write_to_firestore

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        metadata = {
            "id": "12345",
            "title": "Test Book",
            "author": "Test Author",
            "created_at": "2024-06-01T13:22:09.640Z",
            "updated_at": "2024-06-01T13:22:09.641Z",
        }

        result = write_to_firestore(
            metadata,
            content="Test content",
            content_hash="sha256:def",
            run_id="run-1",
            embedding_status="complete",
        )

        self.assertTrue(result)

        # Verify optional fields are handled
        call_args = mock_db.collection().document().set.call_args
        doc_data = call_args[0][0]
        self.assertIsNone(doc_data["url"])
        self.assertEqual(doc_data["tags"], [])
        self.assertEqual(doc_data["content_hash"], "sha256:def")

    @patch("src.embed.main.get_firestore_client")
    @patch("src.embed.main.logger")
    def test_write_document_failure_logged(self, mock_logger, mock_get_client):
        """AC 8: Log error on Firestore write failure, continue processing."""
        from src.embed.main import write_to_firestore

        mock_db = MagicMock()
        mock_db.collection().document().set.side_effect = Exception("Firestore error")
        mock_get_client.return_value = mock_db

        metadata = {
            "id": "41094950",
            "title": "Test Book",
            "author": "Test Author",
            "created_at": "2024-06-01T13:22:09.640Z",
            "updated_at": "2024-06-01T13:22:09.641Z",
        }

        result = write_to_firestore(
            metadata,
            content="Test content",
            content_hash="sha256:ghi",
            run_id="run-1",
            embedding_status="complete",
        )

        self.assertFalse(result)
        mock_logger.error.assert_called_once()
        self.assertIn("Firestore error", str(mock_logger.error.call_args))

    @patch("src.embed.main._HAS_MATCHING_ENGINE_LIB", True)
    @patch("src.embed.main.Vector")
    @patch("src.embed.main.get_firestore_client")
    def test_write_document_with_embedding_vector(self, mock_get_client, mock_vector):
        """AC 2: Write embedding vector to Firestore using Vector type."""
        from src.embed.main import write_to_firestore

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_vector_instance = MagicMock()
        mock_vector.return_value = mock_vector_instance

        metadata = {
            "id": "41094950",
            "title": "Test Book",
            "author": "Test Author",
            "created_at": "2024-06-01T13:22:09.640Z",
            "updated_at": "2024-06-01T13:22:09.641Z",
        }

        embedding_vector = [0.1] * 768

        result = write_to_firestore(
            metadata,
            content="Test content",
            content_hash="sha256:abc",
            run_id="run-1",
            embedding_status="complete",
            embedding_vector=embedding_vector,
        )

        self.assertTrue(result)

        # Verify Vector was created with the embedding
        mock_vector.assert_called_once_with(embedding_vector)

        # Verify document data includes embedding
        call_args = mock_db.collection().document().set.call_args
        doc_data = call_args[0][0]
        self.assertEqual(doc_data["embedding"], mock_vector_instance)
        self.assertEqual(doc_data["title"], "Test Book")


class TestEmbedHandler(unittest.TestCase):
    """Test the manifest-driven embed handler."""

    @patch("src.embed.main.write_to_firestore", return_value=True)
    @patch("src.embed.main.generate_embedding", return_value=[0.1] * 768)
    @patch("src.embed.main.get_pipeline_collection")
    @patch("src.embed.main.get_storage_client")
    @patch(
        "src.embed.main._load_manifest",
        return_value={"run_id": "run-123", "items": [{"id": "123"}]},
    )
    def test_embed_processes_pending_item(
        self,
        mock_manifest,
        mock_storage,
        mock_collection,
        mock_generate_embedding,
        mock_write,
    ):
        from src.embed.main import _compute_markdown_hash, embed

        markdown_content = """---
id: '123'
title: Test Book
author: Test Author
source: kindle
created_at: '2024-06-01T13:22:09.640Z'
updated_at: '2024-06-01T13:22:09.641Z'
highlight_count: 1
user_book_id: 123
category: books
---

Body text here."""

        mock_blob = MagicMock()
        mock_blob.download_as_text.return_value = markdown_content
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        def bucket_side_effect(name):
            if name == "test-markdown-bucket":
                return mock_bucket
            raise AssertionError(f"Unexpected bucket: {name}")

        mock_storage.return_value.bucket.side_effect = bucket_side_effect

        doc_ref = MagicMock()
        snapshot = MagicMock()
        snapshot.id = "123"
        snapshot.reference = doc_ref
        snapshot.to_dict.return_value = {
            "id": "123",
            "embedding_status": "pending",
            "markdown_uri": "gs://test-markdown-bucket/notes/123.md",
            "content_hash": "sha256:old",
            "embedded_content_hash": "sha256:old",
            "manifest_run_id": "run-123",
        }

        mock_query = MagicMock()
        mock_query.stream.return_value = [snapshot]
        mock_collection.return_value.where.return_value = mock_query

        class MockRequest:
            def get_json(self, silent=False):
                return {"run_id": "run-123"}

        response, status = embed(MockRequest())

        self.assertEqual(status, 200)
        self.assertEqual(response["processed"], 1)
        self.assertEqual(response["failed"], 0)
        self.assertEqual(response["firestore_updates"], 1)

        mock_generate_embedding.assert_called_once()

        # Verify write_to_firestore was called with embedding_vector
        mock_write.assert_called()
        write_call = mock_write.call_args
        self.assertIn("embedding_vector", write_call.kwargs)
        self.assertEqual(write_call.kwargs["embedding_vector"], [0.1] * 768)

        success_call = doc_ref.set.call_args_list[-1]
        success_update = success_call.args[0]
        expected_hash = _compute_markdown_hash(markdown_content)
        self.assertEqual(success_update["embedded_content_hash"], expected_hash)
        self.assertEqual(success_update["embedding_status"], "complete")

        write_args = mock_write.call_args.args
        # args[0] = metadata, args[1] = content, args[2] = content_hash
        self.assertEqual(write_args[2], expected_hash)

    def test_embed_missing_run_id(self):
        from src.embed.main import embed

        class MockRequest:
            def get_json(self, silent=False):
                return {}

        response, status = embed(MockRequest())
        self.assertEqual(status, 400)
        self.assertEqual(response["status"], "error")

    @patch("src.embed.main._load_manifest", side_effect=NotFound("missing"))
    def test_embed_missing_manifest(self, mock_manifest):
        from src.embed.main import embed

        class MockRequest:
            def get_json(self, silent=False):
                return {"run_id": "run-404"}

        response, status = embed(MockRequest())
        self.assertEqual(status, 404)
        self.assertEqual(response["status"], "error")


if __name__ == "__main__":
    unittest.main()
