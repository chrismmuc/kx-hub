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
    """Test the Cloud Function handler."""

    def setUp(self):
        """Import the normalize module."""
        # Import here to ensure module is available for patching
        import normalize.main
        self.main_module = normalize.main

    @patch('normalize.main.PROJECT_ID', 'test-project')
    @patch('normalize.main._get_storage_client')
    def test_handler_reads_all_json_files(self, mock_get_storage):
        """Test that handler processes all JSON files from bucket."""
        from normalize.main import normalize_handler

        # Mock storage client
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        # Mock blobs
        mock_blob_1 = MagicMock()
        mock_blob_1.name = "readwise-book-123.json"
        mock_blob_1.download_as_text.return_value = json.dumps({
            "user_book_id": 123,
            "title": "Test Book 1",
            "author": "Author 1",
            "source": "kindle",
            "highlights": []
        })

        mock_blob_2 = MagicMock()
        mock_blob_2.name = "readwise-book-456.json"
        mock_blob_2.download_as_text.return_value = json.dumps({
            "user_book_id": 456,
            "title": "Test Book 2",
            "author": "Author 2",
            "source": "kindle",
            "highlights": []
        })

        mock_bucket.list_blobs.return_value = [mock_blob_1, mock_blob_2]
        mock_get_storage.return_value = mock_client

        # Execute handler
        request = MagicMock()
        response = normalize_handler(request)

        # Verify both files processed
        self.assertEqual(response[1], 200)
        response_data = json.loads(response[0])
        self.assertEqual(response_data["files_processed"], 2)

    @patch('normalize.main.PROJECT_ID', 'test-project')
    @patch('normalize.main._get_storage_client')
    def test_handler_writes_markdown_to_output_bucket(self, mock_get_storage):
        """Test that handler writes transformed Markdown to output bucket."""
        from normalize.main import normalize_handler

        # Mock storage client
        mock_client = MagicMock()
        mock_raw_bucket = MagicMock()
        mock_output_bucket = MagicMock()

        def get_bucket(name):
            if "raw-json" in name:
                return mock_raw_bucket
            elif "markdown-normalized" in name:
                return mock_output_bucket

        mock_client.bucket.side_effect = get_bucket

        # Mock input blob
        mock_blob = MagicMock()
        mock_blob.name = "readwise-book-999.json"
        mock_blob.download_as_text.return_value = json.dumps({
            "user_book_id": 999,
            "title": "Test Book",
            "author": "Test Author",
            "source": "kindle",
            "highlights": []
        })
        mock_raw_bucket.list_blobs.return_value = [mock_blob]

        mock_get_storage.return_value = mock_client

        # Execute handler
        request = MagicMock()
        normalize_handler(request)

        # Verify markdown file written
        mock_output_bucket.blob.assert_called_once_with("notes/999.md")

    @patch('normalize.main.PROJECT_ID', 'test-project')
    @patch('normalize.main._get_storage_client')
    def test_handler_handles_malformed_json(self, mock_get_storage):
        """Test error handling for malformed JSON files."""
        from normalize.main import normalize_handler

        # Mock storage client
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        # Mock blob with invalid JSON
        mock_blob = MagicMock()
        mock_blob.name = "readwise-book-bad.json"
        mock_blob.download_as_text.return_value = "{ invalid json"

        mock_bucket.list_blobs.return_value = [mock_blob]
        mock_get_storage.return_value = mock_client

        # Execute handler - should not crash
        request = MagicMock()
        response = normalize_handler(request)

        # Verify graceful handling
        self.assertEqual(response[1], 200)
        response_data = json.loads(response[0])
        self.assertEqual(response_data["files_processed"], 0)
        self.assertEqual(response_data["errors"], 1)

    @patch('normalize.main.PROJECT_ID', 'test-project')
    @patch('normalize.main._get_storage_client')
    def test_handler_sets_content_type_metadata(self, mock_get_storage):
        """Test that markdown files have correct content-type metadata."""
        from normalize.main import normalize_handler

        # Mock storage
        mock_client = MagicMock()
        mock_raw_bucket = MagicMock()
        mock_output_bucket = MagicMock()
        mock_output_blob = MagicMock()

        def get_bucket(name):
            if "raw-json" in name:
                return mock_raw_bucket
            elif "markdown-normalized" in name:
                return mock_output_bucket

        mock_client.bucket.side_effect = get_bucket
        mock_output_bucket.blob.return_value = mock_output_blob

        # Mock input
        mock_blob = MagicMock()
        mock_blob.name = "readwise-book-111.json"
        mock_blob.download_as_text.return_value = json.dumps({
            "user_book_id": 111,
            "title": "Test",
            "author": "Author",
            "source": "kindle",
            "highlights": []
        })
        mock_raw_bucket.list_blobs.return_value = [mock_blob]

        mock_get_storage.return_value = mock_client

        # Execute
        request = MagicMock()
        normalize_handler(request)

        # Verify content-type set
        mock_output_blob.upload_from_string.assert_called_once()
        call_args = mock_output_blob.upload_from_string.call_args
        self.assertEqual(call_args[1]["content_type"], "text/markdown; charset=utf-8")


if __name__ == "__main__":
    unittest.main()
