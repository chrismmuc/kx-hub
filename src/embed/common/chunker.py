"""
Document chunking module for intelligent text splitting with semantic boundaries.

This module implements hierarchical chunking with overlap for optimal vector embeddings.
"""

import hashlib
import re
import yaml
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

try:
    import tiktoken
    _HAS_TIKTOKEN = True
except ImportError:
    _HAS_TIKTOKEN = False
    tiktoken = None


@dataclass
class ChunkConfig:
    """Configuration for chunking behavior."""
    target_tokens: int = 512
    max_tokens: int = 1024
    min_tokens: int = 100
    overlap_tokens: int = 75
    enable_highlight_boundary: bool = True
    enable_paragraph_boundary: bool = True
    enable_sentence_boundary: bool = True


@dataclass
class ChunkBoundary:
    """Represents a semantic boundary in text."""
    position: int
    boundary_type: str  # 'highlight', 'paragraph', 'sentence', 'token_limit'
    priority: int  # Lower = higher priority


@dataclass
class Chunk:
    """Represents a single chunk with metadata."""
    content: str
    chunk_index: int
    total_chunks: int
    token_count: int
    char_start: int
    char_end: int
    overlap_start: int  # Characters overlapping with previous chunk
    overlap_end: int  # Characters overlapping with next chunk
    frontmatter: Dict
    content_hash: str


class DocumentChunker:
    """Handles document chunking with semantic awareness and overlap."""

    def __init__(self, config: Optional[ChunkConfig] = None):
        """
        Initialize the chunker.

        Args:
            config: Chunking configuration. If None, uses defaults.
        """
        self.config = config or ChunkConfig()

        # Initialize tiktoken encoder (use cl100k_base as proxy for Gemini)
        if _HAS_TIKTOKEN:
            self.encoder = tiktoken.get_encoding("cl100k_base")
        else:
            self.encoder = None

    def calculate_tokens(self, text: str) -> int:
        """
        Calculate token count for text.

        Args:
            text: Input text

        Returns:
            Token count (approximate if tiktoken not available)
        """
        if not text:
            return 0

        if self.encoder:
            return len(self.encoder.encode(text))
        else:
            # Fallback: approximate using 0.25 char/token ratio
            return int(len(text) * 0.25)

    def parse_frontmatter(self, markdown: str) -> Tuple[Dict, str]:
        """
        Parse YAML frontmatter from markdown.

        Args:
            markdown: Full markdown content with frontmatter

        Returns:
            Tuple of (frontmatter_dict, content_without_frontmatter)
        """
        if not markdown.startswith('---'):
            return {}, markdown

        # Find the closing ---
        parts = markdown.split('---', 2)
        if len(parts) < 3:
            return {}, markdown

        frontmatter_str = parts[1].strip()
        content = parts[2].strip()

        try:
            frontmatter = yaml.safe_load(frontmatter_str)
            return frontmatter or {}, content
        except yaml.YAMLError:
            return {}, markdown

    def detect_semantic_boundaries(self, text: str) -> List[ChunkBoundary]:
        """
        Detect semantic boundaries in text using hierarchical priority.

        Priority order:
        1. Highlight boundaries (blockquote starts)
        2. Paragraph boundaries (double newline)
        3. Sentence boundaries (period + uppercase)

        Args:
            text: Content to analyze

        Returns:
            List of ChunkBoundary objects sorted by position
        """
        boundaries = []

        # Priority 1: Highlight boundaries (blockquote pattern)
        if self.config.enable_highlight_boundary:
            for match in re.finditer(r'^> ', text, re.MULTILINE):
                boundaries.append(ChunkBoundary(
                    position=match.start(),
                    boundary_type='highlight',
                    priority=1
                ))

        # Priority 2: Paragraph boundaries
        if self.config.enable_paragraph_boundary:
            for match in re.finditer(r'\n\n+', text):
                boundaries.append(ChunkBoundary(
                    position=match.end(),
                    boundary_type='paragraph',
                    priority=2
                ))

        # Priority 3: Sentence boundaries
        if self.config.enable_sentence_boundary:
            # Match ". " followed by uppercase letter (sentence end)
            for match in re.finditer(r'\.\s+(?=[A-Z])', text):
                boundaries.append(ChunkBoundary(
                    position=match.end(),
                    boundary_type='sentence',
                    priority=3
                ))

        # Sort by position, then by priority
        boundaries.sort(key=lambda b: (b.position, b.priority))

        return boundaries

    def find_split_point(
        self,
        text: str,
        target_position: int,
        boundaries: List[ChunkBoundary]
    ) -> Tuple[int, str]:
        """
        Find the best split point near target position using semantic boundaries.

        Args:
            text: Text to split
            target_position: Desired character position
            boundaries: List of semantic boundaries

        Returns:
            Tuple of (split_position, boundary_type)
        """
        if not boundaries:
            # Fallback: split at target position
            return min(target_position, len(text)), 'token_limit'

        # Find boundaries before and after target
        before = [b for b in boundaries if b.position <= target_position]
        after = [b for b in boundaries if b.position > target_position]

        # Prefer boundary before target (within reason)
        if before:
            best_before = before[-1]
            distance_before = target_position - best_before.position

            # If very close, use the boundary before
            if distance_before < self.config.overlap_tokens * 4:
                return best_before.position, best_before.boundary_type

        # Otherwise use boundary after target
        if after:
            best_after = after[0]
            distance_after = best_after.position - target_position

            # If reasonably close, use boundary after
            if distance_after < self.config.max_tokens * 0.3:
                return best_after.position, best_after.boundary_type

        # Fallback: use closest boundary
        if before:
            return before[-1].position, before[-1].boundary_type

        if after:
            return after[0].position, after[0].boundary_type

        # Ultimate fallback: split at target
        return min(target_position, len(text)), 'token_limit'

    def split_into_chunks(
        self,
        markdown: str,
        parent_doc_id: str
    ) -> List[Chunk]:
        """
        Split document into chunks with semantic awareness and overlap.

        Args:
            markdown: Full markdown document with frontmatter
            parent_doc_id: ID of parent document

        Returns:
            List of Chunk objects
        """
        # Parse frontmatter
        frontmatter, content = self.parse_frontmatter(markdown)

        if not content.strip():
            # Empty content - create single minimal chunk
            return self._create_single_chunk(
                content="",
                parent_doc_id=parent_doc_id,
                frontmatter=frontmatter,
                chunk_index=0
            )

        # Calculate total tokens
        total_tokens = self.calculate_tokens(content)

        # If content is small enough, return single chunk
        if total_tokens <= self.config.target_tokens:
            return self._create_single_chunk(
                content=content,
                parent_doc_id=parent_doc_id,
                frontmatter=frontmatter,
                chunk_index=0
            )

        # Detect all semantic boundaries
        boundaries = self.detect_semantic_boundaries(content)

        # Split into chunks
        chunks = []
        char_position = 0
        chunk_index = 0

        while char_position < len(content):
            # Calculate target end position based on token count
            remaining_content = content[char_position:]
            target_tokens = self.config.target_tokens

            # Estimate character position for target tokens
            # Use inverse of token calculation (tokens * 4 chars/token)
            estimated_chars = target_tokens * 4
            target_char_end = min(
                char_position + estimated_chars,
                len(content)
            )

            # Find best split point using semantic boundaries
            split_pos, boundary_type = self.find_split_point(
                text=content,
                target_position=target_char_end,
                boundaries=[b for b in boundaries if b.position > char_position]
            )

            # Extract chunk content
            chunk_content = content[char_position:split_pos]

            # Calculate token count for this chunk
            chunk_tokens = self.calculate_tokens(chunk_content)

            # Store chunk (overlap will be added in next pass)
            chunks.append({
                'content': chunk_content,
                'char_start': char_position,
                'char_end': split_pos,
                'token_count': chunk_tokens,
                'boundary_type': boundary_type,
                'chunk_index': chunk_index
            })

            # Move position forward
            char_position = split_pos
            chunk_index += 1

            # Safety check: prevent infinite loops
            if char_position == split_pos and split_pos < len(content):
                # Force progress if stuck
                char_position += 1

        # Apply overlaps between chunks
        chunks_with_overlap = self._apply_overlaps(chunks, content)

        # Create final Chunk objects with frontmatter
        total_chunks = len(chunks_with_overlap)
        final_chunks = []

        for i, chunk_data in enumerate(chunks_with_overlap):
            chunk_frontmatter = self._create_chunk_frontmatter(
                parent_frontmatter=frontmatter,
                parent_doc_id=parent_doc_id,
                chunk_index=i,
                total_chunks=total_chunks
            )

            chunk_obj = Chunk(
                content=chunk_data['content'],
                chunk_index=i,
                total_chunks=total_chunks,
                token_count=chunk_data['token_count'],
                char_start=chunk_data['char_start'],
                char_end=chunk_data['char_end'],
                overlap_start=chunk_data['overlap_start'],
                overlap_end=chunk_data['overlap_end'],
                frontmatter=chunk_frontmatter,
                content_hash=self._calculate_content_hash(chunk_data['content'])
            )

            final_chunks.append(chunk_obj)

        return final_chunks

    def _create_single_chunk(
        self,
        content: str,
        parent_doc_id: str,
        frontmatter: Dict,
        chunk_index: int
    ) -> List[Chunk]:
        """Create a single chunk (used when document is small)."""
        chunk_frontmatter = self._create_chunk_frontmatter(
            parent_frontmatter=frontmatter,
            parent_doc_id=parent_doc_id,
            chunk_index=chunk_index,
            total_chunks=1
        )

        chunk = Chunk(
            content=content,
            chunk_index=chunk_index,
            total_chunks=1,
            token_count=self.calculate_tokens(content),
            char_start=0,
            char_end=len(content),
            overlap_start=0,
            overlap_end=0,
            frontmatter=chunk_frontmatter,
            content_hash=self._calculate_content_hash(content)
        )

        return [chunk]

    def _apply_overlaps(
        self,
        chunks: List[Dict],
        full_content: str
    ) -> List[Dict]:
        """
        Apply sliding window overlap between chunks.

        Args:
            chunks: List of chunk dictionaries
            full_content: Original full content

        Returns:
            Updated chunks with overlap applied
        """
        if len(chunks) <= 1:
            # No overlap needed for single chunk
            for chunk in chunks:
                chunk['overlap_start'] = 0
                chunk['overlap_end'] = 0
            return chunks

        # Calculate overlap character count (approximate)
        overlap_chars = self.config.overlap_tokens * 4

        updated_chunks = []

        for i, chunk in enumerate(chunks):
            overlap_start = 0
            overlap_end = 0
            new_content = chunk['content']
            new_char_start = chunk['char_start']
            new_char_end = chunk['char_end']

            # Add overlap from previous chunk
            if i > 0:
                prev_chunk = chunks[i - 1]
                prev_end = prev_chunk['char_end']

                # Take last N chars from previous chunk
                overlap_start_pos = max(0, prev_end - overlap_chars)
                overlap_text = full_content[overlap_start_pos:prev_end]

                if overlap_text:
                    new_content = overlap_text + new_content
                    new_char_start = overlap_start_pos
                    overlap_start = len(overlap_text)

            # Add overlap to next chunk
            if i < len(chunks) - 1:
                next_chunk = chunks[i + 1]
                next_start = next_chunk['char_start']

                # Take first N chars from next chunk
                overlap_end_pos = min(len(full_content), next_start + overlap_chars)
                overlap_text = full_content[new_char_end:overlap_end_pos]

                if overlap_text:
                    new_content = new_content + overlap_text
                    new_char_end = overlap_end_pos
                    overlap_end = len(overlap_text)

            # Recalculate token count with overlap
            new_token_count = self.calculate_tokens(new_content)

            updated_chunks.append({
                'content': new_content,
                'char_start': new_char_start,
                'char_end': new_char_end,
                'token_count': new_token_count,
                'overlap_start': overlap_start,
                'overlap_end': overlap_end,
                'chunk_index': chunk['chunk_index'],
                'boundary_type': chunk['boundary_type']
            })

        return updated_chunks

    def _create_chunk_frontmatter(
        self,
        parent_frontmatter: Dict,
        parent_doc_id: str,
        chunk_index: int,
        total_chunks: int
    ) -> Dict:
        """
        Create chunk-specific frontmatter from parent metadata.

        Args:
            parent_frontmatter: Original document frontmatter
            parent_doc_id: Parent document ID
            chunk_index: Zero-based chunk index
            total_chunks: Total number of chunks

        Returns:
            Chunk frontmatter dictionary
        """
        chunk_id = f"{parent_doc_id}-chunk-{chunk_index:03d}"

        # Preserve essential parent metadata
        chunk_fm = {
            'doc_id': parent_doc_id,
            'chunk_id': chunk_id,
            'chunk_index': chunk_index,
            'total_chunks': total_chunks,
        }

        # Copy key fields from parent
        for key in ['title', 'author', 'source', 'category', 'tags', 'url']:
            if key in parent_frontmatter:
                chunk_fm[key] = parent_frontmatter[key]

        return chunk_fm

    def _calculate_content_hash(self, content: str) -> str:
        """Calculate SHA256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def chunk_to_markdown(self, chunk: Chunk) -> str:
        """
        Convert Chunk object back to markdown with frontmatter.

        Args:
            chunk: Chunk object

        Returns:
            Full markdown string with frontmatter
        """
        # Serialize frontmatter
        frontmatter_str = yaml.dump(
            chunk.frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False
        )

        # Construct markdown
        markdown = f"---\n{frontmatter_str}---\n\n{chunk.content}"

        return markdown


# Convenience functions for direct use

def chunk_document(
    markdown: str,
    parent_doc_id: str,
    config: Optional[ChunkConfig] = None
) -> List[Chunk]:
    """
    Chunk a document with default configuration.

    Args:
        markdown: Full markdown document
        parent_doc_id: Parent document identifier
        config: Optional chunking configuration

    Returns:
        List of Chunk objects
    """
    chunker = DocumentChunker(config=config)
    return chunker.split_into_chunks(markdown, parent_doc_id)


def calculate_tokens(text: str) -> int:
    """
    Calculate token count for text.

    Args:
        text: Input text

    Returns:
        Token count
    """
    chunker = DocumentChunker()
    return chunker.calculate_tokens(text)
