"""
Unit tests for document chunking module.

Tests token counting, semantic boundary detection, chunking algorithm,
overlap calculation, and frontmatter injection.
"""

import unittest
from src.common.chunker import (
    DocumentChunker,
    ChunkConfig,
    ChunkBoundary,
    chunk_document,
    calculate_tokens
)


class TestTokenCounting(unittest.TestCase):
    """Test token calculation functionality."""

    def setUp(self):
        self.chunker = DocumentChunker()

    def test_calculate_tokens_empty_string(self):
        """Test token counting for empty string."""
        result = self.chunker.calculate_tokens("")
        self.assertEqual(result, 0)

    def test_calculate_tokens_simple_text(self):
        """Test token counting for simple text."""
        text = "Hello world"
        result = self.chunker.calculate_tokens(text)
        # Should be approximately 2 tokens
        self.assertGreater(result, 0)
        self.assertLess(result, 10)

    def test_calculate_tokens_long_text(self):
        """Test token counting scales with text length."""
        short_text = "Hello world"
        long_text = " ".join(["Hello world"] * 100)

        short_tokens = self.chunker.calculate_tokens(short_text)
        long_tokens = self.chunker.calculate_tokens(long_text)

        # Long text should have significantly more tokens
        self.assertGreater(long_tokens, short_tokens * 50)


class TestSemanticBoundaries(unittest.TestCase):
    """Test semantic boundary detection."""

    def setUp(self):
        self.chunker = DocumentChunker()

    def test_detect_highlight_boundaries(self):
        """Test detection of highlight (blockquote) boundaries."""
        text = """Some intro text.

> Highlight 1
> - Location: Page 10

> Highlight 2
> - Location: Page 20
"""
        boundaries = self.chunker.detect_semantic_boundaries(text)

        # Should find highlight boundaries (regex matches each line starting with >)
        highlight_boundaries = [b for b in boundaries if b.boundary_type == 'highlight']
        self.assertGreater(len(highlight_boundaries), 0)

        # Check priorities
        for boundary in highlight_boundaries:
            self.assertEqual(boundary.priority, 1)

    def test_detect_paragraph_boundaries(self):
        """Test detection of paragraph boundaries."""
        text = """Paragraph 1.

Paragraph 2.

Paragraph 3."""

        boundaries = self.chunker.detect_semantic_boundaries(text)

        # Should find paragraph boundaries
        para_boundaries = [b for b in boundaries if b.boundary_type == 'paragraph']
        self.assertGreater(len(para_boundaries), 0)

        # Check priorities
        for boundary in para_boundaries:
            self.assertEqual(boundary.priority, 2)

    def test_detect_sentence_boundaries(self):
        """Test detection of sentence boundaries."""
        text = "This is sentence one. This is sentence two. This is sentence three."

        boundaries = self.chunker.detect_semantic_boundaries(text)

        # Should find sentence boundaries
        sentence_boundaries = [b for b in boundaries if b.boundary_type == 'sentence']
        self.assertGreater(len(sentence_boundaries), 0)

        # Check priorities
        for boundary in sentence_boundaries:
            self.assertEqual(boundary.priority, 3)

    def test_boundary_priority_ordering(self):
        """Test that boundaries are correctly prioritized."""
        text = """> Highlight text.

New paragraph. Another sentence."""

        boundaries = self.chunker.detect_semantic_boundaries(text)

        # Verify priorities are ordered correctly
        if len(boundaries) > 1:
            for i in range(len(boundaries) - 1):
                if boundaries[i].position == boundaries[i+1].position:
                    # Same position: priority should be in order
                    self.assertLessEqual(boundaries[i].priority, boundaries[i+1].priority)


class TestChunking(unittest.TestCase):
    """Test document chunking logic."""

    def setUp(self):
        self.config = ChunkConfig(
            target_tokens=100,
            max_tokens=200,
            min_tokens=20,
            overlap_tokens=20
        )
        self.chunker = DocumentChunker(config=self.config)

    def test_chunk_empty_document(self):
        """Test chunking an empty document."""
        markdown = """---
title: Empty Document
author: Test Author
---

"""
        chunks = self.chunker.split_into_chunks(markdown, parent_doc_id="test-001")

        # Should create 1 empty chunk
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, "")
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].total_chunks, 1)

    def test_chunk_small_document(self):
        """Test chunking a document smaller than target size."""
        markdown = """---
title: Small Document
author: Test Author
---

This is a small document that should not be split.
"""
        chunks = self.chunker.split_into_chunks(markdown, parent_doc_id="test-002")

        # Should create 1 chunk
        self.assertEqual(len(chunks), 1)
        self.assertIn("small document", chunks[0].content)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].total_chunks, 1)

    def test_chunk_large_document(self):
        """Test chunking a large document."""
        # Create a large document with multiple highlights
        highlights = []
        for i in range(10):
            highlights.append(f"""
> This is highlight number {i}. It contains some text about topic {i}.
> - Location: Page {i * 10}
> - Note: This is a note about highlight {i}
""")

        markdown = f"""---
title: Large Document
author: Test Author
source: kindle
category: books
tags: [test, chunking]
---

{''.join(highlights)}
"""
        chunks = self.chunker.split_into_chunks(markdown, parent_doc_id="test-003")

        # Should create multiple chunks
        self.assertGreater(len(chunks), 1)

        # Verify chunk sequence
        for i, chunk in enumerate(chunks):
            self.assertEqual(chunk.chunk_index, i)
            self.assertEqual(chunk.total_chunks, len(chunks))

    def test_chunk_frontmatter_injection(self):
        """Test that chunk frontmatter is correctly injected."""
        markdown = """---
title: Test Book
author: Test Author
source: kindle
category: books
tags: [psychology, science]
url: https://example.com/book
---

Some content here.
"""
        chunks = self.chunker.split_into_chunks(markdown, parent_doc_id="book-123")

        chunk = chunks[0]

        # Verify frontmatter fields
        self.assertEqual(chunk.frontmatter['doc_id'], 'book-123')
        self.assertEqual(chunk.frontmatter['chunk_id'], 'book-123-chunk-000')
        self.assertEqual(chunk.frontmatter['chunk_index'], 0)
        self.assertEqual(chunk.frontmatter['title'], 'Test Book')
        self.assertEqual(chunk.frontmatter['author'], 'Test Author')
        self.assertEqual(chunk.frontmatter['source'], 'kindle')
        self.assertEqual(chunk.frontmatter['category'], 'books')
        self.assertIn('psychology', chunk.frontmatter['tags'])

    def test_chunk_overlap_application(self):
        """Test that overlaps are correctly applied between chunks."""
        # Create document large enough to force chunking
        content_parts = []
        for i in range(20):
            content_parts.append(f"Paragraph {i}. " * 20)

        markdown = f"""---
title: Overlap Test
author: Test Author
---

{''.join(content_parts)}
"""
        chunks = self.chunker.split_into_chunks(markdown, parent_doc_id="overlap-test")

        if len(chunks) > 1:
            # Verify overlaps exist
            for i, chunk in enumerate(chunks):
                if i > 0:
                    # Should have overlap with previous
                    self.assertGreater(chunk.overlap_start, 0)
                else:
                    # First chunk has no previous overlap
                    self.assertEqual(chunk.overlap_start, 0)

                if i < len(chunks) - 1:
                    # Should have overlap with next
                    self.assertGreater(chunk.overlap_end, 0)
                else:
                    # Last chunk has no next overlap
                    self.assertEqual(chunk.overlap_end, 0)

    def test_chunk_content_hash(self):
        """Test that content hashes are generated for each chunk."""
        markdown = """---
title: Hash Test
author: Test Author
---

Some content for hashing.
"""
        chunks = self.chunker.split_into_chunks(markdown, parent_doc_id="hash-test")

        for chunk in chunks:
            # Should have a content hash
            self.assertIsNotNone(chunk.content_hash)
            self.assertTrue(len(chunk.content_hash) > 0)

    def test_chunk_to_markdown_conversion(self):
        """Test converting chunk back to markdown format."""
        markdown = """---
title: Conversion Test
author: Test Author
---

Content to convert.
"""
        chunks = self.chunker.split_into_chunks(markdown, parent_doc_id="convert-test")
        chunk = chunks[0]

        # Convert back to markdown
        output_markdown = self.chunker.chunk_to_markdown(chunk)

        # Should start with frontmatter
        self.assertTrue(output_markdown.startswith('---'))

        # Should contain chunk_id in frontmatter
        self.assertIn('chunk_id:', output_markdown)

        # Should contain content
        self.assertIn('Content to convert', output_markdown)


class TestChunkConfig(unittest.TestCase):
    """Test chunk configuration handling."""

    def test_default_config(self):
        """Test that default configuration is applied."""
        config = ChunkConfig()

        self.assertEqual(config.target_tokens, 512)
        self.assertEqual(config.max_tokens, 1024)
        self.assertEqual(config.min_tokens, 100)
        self.assertEqual(config.overlap_tokens, 75)

    def test_custom_config(self):
        """Test that custom configuration is applied."""
        config = ChunkConfig(
            target_tokens=256,
            max_tokens=512,
            min_tokens=50,
            overlap_tokens=30
        )

        chunker = DocumentChunker(config=config)

        self.assertEqual(chunker.config.target_tokens, 256)
        self.assertEqual(chunker.config.max_tokens, 512)
        self.assertEqual(chunker.config.min_tokens, 50)
        self.assertEqual(chunker.config.overlap_tokens, 30)

    def test_config_boundary_toggles(self):
        """Test that boundary detection can be toggled."""
        config = ChunkConfig(
            enable_highlight_boundary=False,
            enable_paragraph_boundary=True,
            enable_sentence_boundary=False
        )

        chunker = DocumentChunker(config=config)

        text = """
> Highlight text.

Paragraph 1.

Paragraph 2. Sentence 1. Sentence 2.
"""
        boundaries = chunker.detect_semantic_boundaries(text)

        # Should only have paragraph boundaries
        highlight_count = len([b for b in boundaries if b.boundary_type == 'highlight'])
        para_count = len([b for b in boundaries if b.boundary_type == 'paragraph'])
        sentence_count = len([b for b in boundaries if b.boundary_type == 'sentence'])

        self.assertEqual(highlight_count, 0)
        self.assertGreater(para_count, 0)
        self.assertEqual(sentence_count, 0)


class TestConvenienceFunctions(unittest.TestCase):
    """Test module-level convenience functions."""

    def test_chunk_document_function(self):
        """Test chunk_document convenience function."""
        markdown = """---
title: Convenience Test
author: Test Author
---

Test content.
"""
        chunks = chunk_document(markdown, parent_doc_id="convenience-test")

        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)
        self.assertEqual(chunks[0].frontmatter['doc_id'], 'convenience-test')

    def test_chunk_document_with_custom_config(self):
        """Test chunk_document with custom configuration."""
        config = ChunkConfig(target_tokens=50)

        markdown = """---
title: Custom Config Test
author: Test Author
---

Test content.
"""
        chunks = chunk_document(markdown, parent_doc_id="config-test", config=config)

        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)

    def test_calculate_tokens_function(self):
        """Test calculate_tokens convenience function."""
        text = "Hello world"
        tokens = calculate_tokens(text)

        self.assertIsInstance(tokens, int)
        self.assertGreater(tokens, 0)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        self.chunker = DocumentChunker()

    def test_missing_frontmatter(self):
        """Test handling of document without frontmatter."""
        markdown = "Just plain text without frontmatter."

        # Should return empty frontmatter dict and full content
        frontmatter, content = self.chunker.parse_frontmatter(markdown)

        self.assertEqual(frontmatter, {})
        self.assertEqual(content, markdown)

    def test_malformed_frontmatter(self):
        """Test handling of malformed YAML frontmatter."""
        markdown = """---
title: Test
invalid yaml: [unclosed bracket
---

Content here.
"""
        # Should return empty frontmatter dict
        frontmatter, content = self.chunker.parse_frontmatter(markdown)

        self.assertEqual(frontmatter, {})

    def test_very_long_text(self):
        """Test handling of very long text."""
        # Create a very long document
        long_text = "Word " * 10000

        markdown = f"""---
title: Long Document
author: Test Author
---

{long_text}
"""
        chunks = self.chunker.split_into_chunks(markdown, parent_doc_id="long-test")

        # Should create multiple chunks
        self.assertGreater(len(chunks), 5)

        # Verify no chunk exceeds max tokens significantly
        for chunk in chunks:
            # Allow some buffer for overlap
            self.assertLess(chunk.token_count, self.chunker.config.max_tokens * 1.5)

    def test_unicode_content(self):
        """Test handling of Unicode characters."""
        markdown = """---
title: Unicode Test
author: Test Author
---

This has émojis 🎉 and spëcial çharacters.
"""
        chunks = self.chunker.split_into_chunks(markdown, parent_doc_id="unicode-test")

        self.assertEqual(len(chunks), 1)
        self.assertIn("émojis", chunks[0].content)
        self.assertIn("🎉", chunks[0].content)


if __name__ == '__main__':
    unittest.main()
