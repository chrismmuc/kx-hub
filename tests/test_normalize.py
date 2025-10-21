"""Unit tests for the normalize Cloud Function."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Module will be imported after we create it
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestMarkdownTransformer(unittest.TestCase):
    """Test the JSON to Markdown transformation logic."""

    def setUp(self):
        """Load test fixtures."""
        fixtures_dir = Path(__file__).parent / "fixtures"

        # Load sample JSON
        with open(fixtures_dir / "sample-book.json") as f:
            self.sample_book = json.load(f)

        # Load expected output
        with open(fixtures_dir / "expected-output.md") as f:
            self.expected_markdown = f.read()

    def test_generate_frontmatter(self):
        """Test YAML frontmatter generation from book JSON."""
        from normalize.transformer import generate_frontmatter

        frontmatter = generate_frontmatter(self.sample_book)

        # Check required fields (YAML uses single quotes)
        self.assertIn("id:", frontmatter)
        self.assertIn("id: '41094950'", frontmatter)
        self.assertIn("title:", frontmatter)
        self.assertIn("title: Geschwister Als Team", frontmatter)
        self.assertIn("author:", frontmatter)
        self.assertIn("author: Nicola Schmidt", frontmatter)
        self.assertIn("source:", frontmatter)
        self.assertIn("source: kindle", frontmatter)
        self.assertIn("highlight_count:", frontmatter)
        self.assertIn("highlight_count: 11", frontmatter)

        # Check YAML delimiters
        self.assertTrue(frontmatter.startswith("---\n"))
        self.assertTrue(frontmatter.endswith("---\n"))

    def test_generate_frontmatter_with_missing_fields(self):
        """Test frontmatter generation handles missing optional fields gracefully."""
        from normalize.transformer import generate_frontmatter

        minimal_book = {
            "user_book_id": 12345,
            "title": "Test Book",
            "author": "Test Author",
            "source": "kindle",
            "highlights": []
        }

        frontmatter = generate_frontmatter(minimal_book)

        # Required fields present (YAML uses single quotes)
        self.assertIn("id: '12345'", frontmatter)
        self.assertIn("title: Test Book", frontmatter)
        self.assertIn("highlight_count: 0", frontmatter)

        # Optional fields handled gracefully
        self.assertIn("url:", frontmatter)  # Should be present even if null
        self.assertIn("tags: []", frontmatter)

    def test_transform_highlights_to_markdown(self):
        """Test converting highlights array to Markdown blockquotes."""
        from normalize.transformer import transform_highlights

        markdown = transform_highlights(self.sample_book["highlights"])

        # Check structure
        self.assertIn("## Highlights", markdown)
        self.assertIn(">", markdown)  # Blockquotes present

        # Check first highlight content
        first_highlight_text = "Entspannte Eltern"
        self.assertIn(first_highlight_text, markdown)

        # Check metadata formatting
        self.assertIn("Location:", markdown)
        self.assertIn("Highlighted:", markdown)

    def test_transform_highlights_with_notes(self):
        """Test highlights with user notes are properly formatted."""
        from normalize.transformer import transform_highlights

        highlights_with_notes = [
            {
                "id": 1,
                "text": "Important passage",
                "note": "My analysis here",
                "location": 42,
                "location_type": "page",
                "highlighted_at": "2024-01-15T10:30:00Z"
            }
        ]

        markdown = transform_highlights(highlights_with_notes)

        self.assertIn("Important passage", markdown)
        self.assertIn("Note: My analysis here", markdown)
        self.assertIn("Page: 42", markdown)

    def test_transform_highlights_empty_array(self):
        """Test handling of books with no highlights."""
        from normalize.transformer import transform_highlights

        markdown = transform_highlights([])

        self.assertIn("## Highlights", markdown)
        self.assertIn("No highlights", markdown)

    def test_full_json_to_markdown_transformation(self):
        """Test complete transformation from JSON to Markdown."""
        from normalize.transformer import json_to_markdown

        markdown = json_to_markdown(self.sample_book)

        # Check frontmatter is present
        self.assertTrue(markdown.startswith("---\n"))
        self.assertIn("user_book_id: 41094950", markdown)

        # Check title header
        self.assertIn("# Geschwister Als Team", markdown)

        # Check author and source
        self.assertIn("**Author:** Nicola Schmidt", markdown)
        self.assertIn("**Source:** Kindle", markdown)

        # Check highlights section
        self.assertIn("## Highlights", markdown)
        self.assertIn("Entspannte Eltern", markdown)

    def test_markdown_escaping_special_characters(self):
        """Test that special Markdown characters are properly handled."""
        from normalize.transformer import json_to_markdown

        book_with_special_chars = {
            "user_book_id": 999,
            "title": "Test: Book with *special* chars & [brackets]",
            "author": "Author #1",
            "source": "kindle",
            "highlights": [
                {
                    "id": 1,
                    "text": "Code example: `print('hello')` and **bold** text",
                    "location": 10,
                    "location_type": "location",
                    "highlighted_at": "2024-01-01T00:00:00Z"
                }
            ]
        }

        markdown = json_to_markdown(book_with_special_chars)

        # Special chars in frontmatter should be quoted (YAML uses single quotes)
        self.assertIn("title: 'Test: Book with *special* chars & [brackets]'", markdown)

        # Special chars in markdown body should be preserved (not escaped)
        self.assertIn("Code example: `print('hello')`", markdown)

    def test_unicode_and_emoji_handling(self):
        """Test proper handling of Unicode characters and emojis."""
        from normalize.transformer import json_to_markdown

        book_with_unicode = {
            "user_book_id": 888,
            "title": "Über die Zukunft 🚀",
            "author": "François Müller",
            "source": "kindle",
            "highlights": [
                {
                    "id": 1,
                    "text": "Das ist großartig! 🎉 Ça va bien.",
                    "location": 5,
                    "location_type": "location",
                    "highlighted_at": "2024-01-01T00:00:00Z"
                }
            ]
        }

        markdown = json_to_markdown(book_with_unicode)

        # Unicode should be preserved
        self.assertIn("Über die Zukunft", markdown)
        self.assertIn("François Müller", markdown)
        self.assertIn("großartig", markdown)
        self.assertIn("Ça va bien", markdown)

    def test_large_highlight_array(self):
        """Test performance with large number of highlights (100+)."""
        from normalize.transformer import transform_highlights

        # Generate 150 highlights
        large_highlights = [
            {
                "id": i,
                "text": f"Highlight number {i}",
                "location": i * 10,
                "location_type": "location",
                "highlighted_at": "2024-01-01T00:00:00Z"
            }
            for i in range(150)
        ]

        markdown = transform_highlights(large_highlights)

        # Should handle all highlights
        self.assertIn("Highlight number 0", markdown)
        self.assertIn("Highlight number 149", markdown)

        # Count blockquotes - each highlight has one blockquote line starting with "> "
        # Count lines that start a highlight (not metadata lines)
        lines = markdown.split("\n")
        highlight_starts = [line for line in lines if line.startswith("> Highlight number")]
        self.assertEqual(len(highlight_starts), 150)


class TestNormalizeCloudFunction(unittest.TestCase):
    """Test the manifest-aware normalize handler."""

    def setUp(self):
        import normalize.main
        self.module = normalize.main

    def test_requires_run_id(self):
        from normalize.main import normalize_handler

        class MockRequest:
            def get_json(self, silent=False):
                return {}

        body, status = normalize_handler(MockRequest())
        self.assertEqual(status, 400)
        self.assertIn('run_id is required', body)

    @patch('normalize.main._load_manifest', side_effect=FileNotFoundError('missing'))
    def test_manifest_missing_returns_404(self, mock_manifest):
        from normalize.main import normalize_handler

        class MockRequest:
            def get_json(self, silent=False):
                return {'run_id': 'run-404'}

        body, status = normalize_handler(MockRequest())
        self.assertEqual(status, 404)
        self.assertIn('missing', body)

    @patch('normalize.main.PIPELINE_BUCKET', 'test-pipeline')
    @patch('normalize.main.PROJECT_ID', 'test-project')
    @patch('normalize.main._get_firestore_client')
    @patch('normalize.main._get_storage_client')
    @patch('normalize.main._load_manifest')
    def test_processes_manifest_items(self, mock_manifest, mock_storage, mock_firestore):
        from normalize.main import normalize_handler

        mock_manifest.return_value = {
            'run_id': 'run-1',
            'items': [
                {
                    'id': '123',
                    'raw_uri': 'gs://test-raw/readwise-book-123.json',
                    'raw_checksum': 'sha256:raw1',
                    'updated_at': '2024-10-20T00:00:00Z'
                }
            ]
        }

        # Storage mocks
        raw_blob = MagicMock()
        raw_blob.download_as_text.return_value = json.dumps({
            "user_book_id": 123,
            "title": "Test Book",
            "author": "Author",
            "source": "kindle",
            "highlights": []
        })
        raw_bucket = MagicMock()
        raw_bucket.blob.return_value = raw_blob

        markdown_blob = MagicMock()
        markdown_bucket = MagicMock()
        markdown_bucket.blob.return_value = markdown_blob

        storage_client = MagicMock()
        storage_client.bucket.side_effect = lambda name: raw_bucket if name == 'test-raw' else markdown_bucket
        mock_storage.return_value = storage_client

        # Firestore mocks
        doc_ref = MagicMock()
        snapshot = MagicMock()
        snapshot.exists = False
        snapshot.to_dict.return_value = {}
        doc_ref.get.return_value = snapshot

        collection = MagicMock()
        collection.document.return_value = doc_ref
        firestore_client = MagicMock()
        firestore_client.collection.return_value = collection
        mock_firestore.return_value = firestore_client

        class MockRequest:
            def get_json(self, silent=False):
                return {'run_id': 'run-1'}

        body, status = normalize_handler(MockRequest())
        self.assertEqual(status, 200)
        stats = json.loads(body)
        self.assertEqual(stats['processed'], 1)

        # Markdown written with correct content type
        markdown_blob.upload_from_string.assert_called_once()
        self.assertEqual(markdown_blob.upload_from_string.call_args.kwargs['content_type'], 'text/markdown; charset=utf-8')

        # Firestore updated to complete
        success_update = doc_ref.set.call_args_list[-1].args[0]
        self.assertEqual(success_update['embedding_status'], 'pending')
        self.assertEqual(success_update['normalize_status'], 'complete')

    @patch('normalize.main.PROJECT_ID', 'test-project')
    @patch('normalize.main._get_firestore_client')
    @patch('normalize.main._get_storage_client')
    @patch('normalize.main._load_manifest')
    def test_skips_when_checksum_matches(self, mock_manifest, mock_storage, mock_firestore):
        from normalize.main import normalize_handler

        mock_manifest.return_value = {
            'run_id': 'run-2',
            'items': [
                {
                    'id': '123',
                    'raw_uri': 'gs://test-raw/readwise-book-123.json',
                    'raw_checksum': 'sha256:raw1',
                    'updated_at': '2024-10-20T00:00:00Z'
                }
            ]
        }

        storage_client = MagicMock()
        mock_storage.return_value = storage_client

        snapshot = MagicMock()
        snapshot.exists = True
        snapshot.to_dict.return_value = {
            'normalize_status': 'complete',
            'raw_checksum': 'sha256:raw1'
        }

        doc_ref = MagicMock()
        doc_ref.get.return_value = snapshot
        collection = MagicMock()
        collection.document.return_value = doc_ref
        firestore_client = MagicMock()
        firestore_client.collection.return_value = collection
        mock_firestore.return_value = firestore_client

        class MockRequest:
            def get_json(self, silent=False):
                return {'run_id': 'run-2'}

        body, status = normalize_handler(MockRequest())
        self.assertEqual(status, 200)
        stats = json.loads(body)
        self.assertEqual(stats['skipped'], 1)
        called_buckets = [call.args[0] for call in storage_client.bucket.call_args_list]
        self.assertNotIn('test-raw', called_buckets)


if __name__ == "__main__":
    unittest.main()
