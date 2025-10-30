"""
Integration tests for end-to-end chunking pipeline.

Tests the complete flow: JSON → Markdown (with chunking) → Embedding → Firestore
"""

import json
import unittest
from unittest.mock import patch, MagicMock
from src.common.chunker import DocumentChunker, ChunkConfig
from src.normalize.transformer import json_to_markdown


class TestChunkingIntegration(unittest.TestCase):
    """Test end-to-end chunking pipeline with realistic fixtures."""

    def load_fixture(self, filename):
        """Load test fixture JSON."""
        with open(f'tests/fixtures/{filename}', 'r') as f:
            return json.load(f)

    def test_small_book_single_chunk(self):
        """Test that small book produces single chunk."""
        # Load fixture
        book_data = self.load_fixture('small-book.json')

        # Generate markdown
        markdown = json_to_markdown(book_data)

        # Chunk the document
        config = ChunkConfig(
            target_tokens=512,
            max_tokens=1024,
            min_tokens=100,
            overlap_tokens=75
        )
        chunker = DocumentChunker(config=config)
        chunks = chunker.split_into_chunks(markdown, parent_doc_id=book_data['user_book_id'])

        # Verify single chunk for small document
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].total_chunks, 1)

        # Verify frontmatter
        self.assertEqual(chunks[0].frontmatter['doc_id'], 'test-001')
        self.assertEqual(chunks[0].frontmatter['chunk_id'], 'test-001-chunk-000')
        self.assertEqual(chunks[0].frontmatter['title'], 'Test Book: Small')
        self.assertEqual(chunks[0].frontmatter['author'], 'Test Author')

        # Verify content includes highlights
        self.assertIn('first highlight', chunks[0].content)
        self.assertIn('second highlight', chunks[0].content)

        # Verify no overlaps for single chunk
        self.assertEqual(chunks[0].overlap_start, 0)
        self.assertEqual(chunks[0].overlap_end, 0)

    def test_large_book_multiple_chunks(self):
        """Test that large book produces multiple chunks with overlaps."""
        # Load fixture
        book_data = self.load_fixture('large-book.json')

        # Generate markdown
        markdown = json_to_markdown(book_data)

        # Chunk the document
        config = ChunkConfig(
            target_tokens=512,
            max_tokens=1024,
            min_tokens=100,
            overlap_tokens=75
        )
        chunker = DocumentChunker(config=config)
        chunks = chunker.split_into_chunks(markdown, parent_doc_id=book_data['user_book_id'])

        # Verify multiple chunks for large document
        self.assertGreater(len(chunks), 1)
        print(f"Large book split into {len(chunks)} chunks")

        # Verify chunk sequence
        for i, chunk in enumerate(chunks):
            self.assertEqual(chunk.chunk_index, i)
            self.assertEqual(chunk.total_chunks, len(chunks))

        # Verify frontmatter consistency across chunks
        for chunk in chunks:
            self.assertEqual(chunk.frontmatter['doc_id'], 'test-large')
            self.assertEqual(chunk.frontmatter['title'], 'Test Book: Large Document')
            self.assertEqual(chunk.frontmatter['author'], 'Prolific Author')
            self.assertIn('psychology', chunk.frontmatter['tags'])

        # Verify overlaps (middle chunks should have both)
        if len(chunks) > 2:
            middle_chunk = chunks[1]
            self.assertGreater(middle_chunk.overlap_start, 0, "Middle chunk should have overlap with previous")
            self.assertGreater(middle_chunk.overlap_end, 0, "Middle chunk should have overlap with next")

        # Verify first chunk has no previous overlap
        self.assertEqual(chunks[0].overlap_start, 0)

        # Verify last chunk has no next overlap
        self.assertEqual(chunks[-1].overlap_end, 0)

        # Verify token counts are reasonable
        for i, chunk in enumerate(chunks):
            # Last chunk may be smaller than min_tokens if document ends
            if i < len(chunks) - 1:
                self.assertGreater(chunk.token_count, config.min_tokens * 0.8,
                                   f"Chunk {i} has {chunk.token_count} tokens, below 80% of min")
            # All chunks should be under max (with buffer for overlaps)
            self.assertLess(chunk.token_count, config.max_tokens * 1.5,
                            f"Chunk {i} has {chunk.token_count} tokens, exceeds max * 1.5")

    def test_chunk_boundaries_preserve_highlights(self):
        """Test that chunk boundaries respect highlight boundaries."""
        book_data = self.load_fixture('large-book.json')
        markdown = json_to_markdown(book_data)

        config = ChunkConfig(
            target_tokens=300,  # Smaller chunks to force splitting
            max_tokens=600,
            min_tokens=50,
            overlap_tokens=50
        )
        chunker = DocumentChunker(config=config)
        chunks = chunker.split_into_chunks(markdown, parent_doc_id=book_data['user_book_id'])

        # Should create multiple chunks
        self.assertGreater(len(chunks), 2)

        # Verify chunks contain complete highlight text
        all_content = ''.join(chunk.content for chunk in chunks)

        # Check that key highlights are preserved
        self.assertIn('Highlight 1:', all_content)
        self.assertIn('Highlight 10:', all_content)
        self.assertIn('Highlight 20:', all_content)

    def test_chunk_markdown_roundtrip(self):
        """Test converting chunks back to markdown format."""
        book_data = self.load_fixture('small-book.json')
        markdown = json_to_markdown(book_data)

        chunker = DocumentChunker()
        chunks = chunker.split_into_chunks(markdown, parent_doc_id=book_data['user_book_id'])

        # Convert first chunk to markdown
        chunk_markdown = chunker.chunk_to_markdown(chunks[0])

        # Verify markdown structure
        self.assertTrue(chunk_markdown.startswith('---'))
        self.assertIn('chunk_id:', chunk_markdown)
        self.assertIn('doc_id:', chunk_markdown)
        self.assertIn('title:', chunk_markdown)

        # Verify content is present
        self.assertIn('first highlight', chunk_markdown)

    def test_chunks_maintain_metadata_consistency(self):
        """Test that all chunks from same document share consistent metadata."""
        book_data = self.load_fixture('large-book.json')
        markdown = json_to_markdown(book_data)

        chunker = DocumentChunker()
        chunks = chunker.split_into_chunks(markdown, parent_doc_id=book_data['user_book_id'])

        # Extract metadata from all chunks
        titles = set(chunk.frontmatter['title'] for chunk in chunks)
        authors = set(chunk.frontmatter['author'] for chunk in chunks)
        doc_ids = set(chunk.frontmatter['doc_id'] for chunk in chunks)

        # All chunks should have same parent metadata
        self.assertEqual(len(titles), 1)
        self.assertEqual(len(authors), 1)
        self.assertEqual(len(doc_ids), 1)

        # Verify chunk_ids are unique
        chunk_ids = [chunk.frontmatter['chunk_id'] for chunk in chunks]
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)), "Chunk IDs should be unique")

    def test_chunk_content_hash_uniqueness(self):
        """Test that different chunks have different content hashes."""
        book_data = self.load_fixture('large-book.json')
        markdown = json_to_markdown(book_data)

        chunker = DocumentChunker()
        chunks = chunker.split_into_chunks(markdown, parent_doc_id=book_data['user_book_id'])

        if len(chunks) > 1:
            # Extract content hashes
            hashes = [chunk.content_hash for chunk in chunks]

            # All chunks should have unique hashes (different content)
            self.assertEqual(len(hashes), len(set(hashes)), "Chunks should have unique content hashes")

    def test_empty_book_handling(self):
        """Test handling of book with no highlights."""
        book_data = {
            "user_book_id": "empty-book",
            "title": "Empty Book",
            "author": "No Author",
            "source": "kindle",
            "category": "books",
            "source_url": "https://example.com",
            "unique_url": "https://example.com",
            "book_tags": [],
            "created": "2024-06-01T13:22:09.640Z",
            "last_highlight_at": None,
            "updated": "2024-06-01T13:22:09.641Z",
            "cover_image_url": "",
            "highlights_count": 0,
            "highlights": []
        }

        markdown = json_to_markdown(book_data)
        chunker = DocumentChunker()
        chunks = chunker.split_into_chunks(markdown, parent_doc_id=book_data['user_book_id'])

        # Should create one chunk even if empty
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_index, 0)


class TestPipelineIntegration(unittest.TestCase):
    """Test integration between pipeline stages."""

    def load_fixture(self, filename):
        """Load test fixture JSON."""
        with open(f'tests/fixtures/{filename}', 'r') as f:
            return json.load(f)

    @patch('src.embed.main.get_vertex_ai_client')
    @patch('src.embed.main.get_firestore_client')
    def test_chunk_embedding_flow(self, mock_firestore, mock_vertex):
        """Test that chunks can be embedded and stored."""
        from src.embed.main import parse_markdown, write_to_firestore

        # Setup mocks
        mock_model = MagicMock()
        mock_model.get_embeddings.return_value = [MagicMock(values=[0.1] * 768)]
        mock_vertex.return_value = mock_model

        mock_db = MagicMock()
        mock_firestore.return_value = mock_db

        # Create a chunk markdown
        book_data = self.load_fixture('small-book.json')
        markdown = json_to_markdown(book_data)

        from src.common.chunker import DocumentChunker
        chunker = DocumentChunker()
        chunks = chunker.split_into_chunks(markdown, parent_doc_id=book_data['user_book_id'])

        # Convert chunk to markdown
        chunk_markdown = chunker.chunk_to_markdown(chunks[0])

        # Parse the chunk markdown (as embed stage would)
        metadata, content = parse_markdown(chunk_markdown)

        # Verify chunk metadata is recognized
        self.assertIn('chunk_id', metadata)
        self.assertEqual(metadata['id'], metadata['chunk_id'])
        self.assertIn('parent_doc_id', metadata)

        # Write to Firestore (as embed stage would)
        result = write_to_firestore(
            metadata=metadata,
            content=content,
            content_hash="test-hash",
            run_id="test-run",
            embedding_status="complete",
            embedding_vector=[0.1] * 768
        )

        self.assertTrue(result)

        # Verify Firestore was called with chunk schema
        call_args = mock_db.collection().document().set.call_args
        doc_data = call_args[0][0]

        # Verify chunk fields are present
        self.assertIn('chunk_id', doc_data)
        self.assertIn('parent_doc_id', doc_data)
        self.assertIn('chunk_index', doc_data)
        self.assertIn('content', doc_data)
        self.assertIn('embedding', doc_data)


if __name__ == '__main__':
    unittest.main()
