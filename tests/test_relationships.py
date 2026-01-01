"""
Tests for Relationship Extraction (Epic 4, Story 4.1)
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.relationships.extractor import RelationshipExtractor
from src.relationships.prompt_manager import (
    PromptManager,
    create_relationship_prompt,
)
from src.relationships.schema import (
    RELATIONSHIP_TYPES,
    Relationship,
    RelationType,
    validate_llm_response,
)


class TestRelationshipSchema:
    """Tests for Relationship dataclass and validation."""

    def test_relationship_creation(self):
        """Test creating a valid Relationship."""
        rel = Relationship(
            source_chunk_id="chunk1",
            target_chunk_id="chunk2",
            type="extends",
            confidence=0.85,
            explanation="Chunk 2 builds on chunk 1",
            source_context="source-a--source-b",
        )

        assert rel.source_chunk_id == "chunk1"
        assert rel.target_chunk_id == "chunk2"
        assert rel.type == "extends"
        assert rel.confidence == 0.85
        assert rel.source_context == "source-a--source-b"
        assert isinstance(rel.created_at, datetime)

    def test_relationship_invalid_type(self):
        """Test that invalid relationship types raise ValueError."""
        with pytest.raises(ValueError, match="Invalid relationship type"):
            Relationship(
                source_chunk_id="chunk1",
                target_chunk_id="chunk2",
                type="invalid_type",
                confidence=0.8,
                explanation="Test",
                source_context="source-a--source-b",
            )

    def test_relationship_invalid_confidence(self):
        """Test that confidence outside 0-1 raises ValueError."""
        with pytest.raises(ValueError, match="Confidence must be between"):
            Relationship(
                source_chunk_id="chunk1",
                target_chunk_id="chunk2",
                type="extends",
                confidence=1.5,
                explanation="Test",
                source_context="source-a--source-b",
            )

    def test_relationship_same_source_target(self):
        """Test that same source and target raises ValueError."""
        with pytest.raises(
            ValueError, match="Source and target chunk IDs must be different"
        ):
            Relationship(
                source_chunk_id="chunk1",
                target_chunk_id="chunk1",
                type="extends",
                confidence=0.8,
                explanation="Test",
                source_context="source-a--source-b",
            )

    def test_relationship_to_dict(self):
        """Test converting Relationship to dictionary."""
        rel = Relationship(
            source_chunk_id="chunk1",
            target_chunk_id="chunk2",
            type="supports",
            confidence=0.9,
            explanation="Evidence provided",
            source_context="source-a--source-b",
        )

        d = rel.to_dict()

        assert d["source_chunk_id"] == "chunk1"
        assert d["target_chunk_id"] == "chunk2"
        assert d["type"] == "supports"
        assert d["confidence"] == 0.9
        assert d["explanation"] == "Evidence provided"
        assert d["source_context"] == "source-a--source-b"
        assert "created_at" in d

    def test_relationship_from_dict(self):
        """Test creating Relationship from dictionary."""
        d = {
            "source_chunk_id": "chunk1",
            "target_chunk_id": "chunk2",
            "type": "contradicts",
            "confidence": 0.75,
            "explanation": "Opposing view",
            "source_context": "source-a--source-b",
        }

        rel = Relationship.from_dict(d)

        assert rel.source_chunk_id == "chunk1"
        assert rel.type == "contradicts"
        assert rel.confidence == 0.75

    def test_all_relationship_types_valid(self):
        """Test that all defined types are valid."""
        for rel_type in RELATIONSHIP_TYPES:
            # Should not raise
            if rel_type != "none":
                rel = Relationship(
                    source_chunk_id="a",
                    target_chunk_id="b",
                    type=rel_type,
                    confidence=0.5,
                    explanation="Test",
                    source_context="source-a--source-b",
                )
                assert rel.type == rel_type


class TestValidateLLMResponse:
    """Tests for LLM response validation."""

    def test_valid_response(self):
        """Test validating a valid LLM response."""
        response = {
            "type": "extends",
            "confidence": 0.85,
            "explanation": "Builds upon the concept",
        }

        rel = validate_llm_response(response, "chunk1", "chunk2", "source-a--source-b")

        assert rel is not None
        assert rel.type == "extends"
        assert rel.confidence == 0.85
        assert rel.source_chunk_id == "chunk1"

    def test_none_type_returns_none(self):
        """Test that 'none' type returns None."""
        response = {
            "type": "none",
            "confidence": 0.9,
            "explanation": "No relationship",
        }

        rel = validate_llm_response(response, "chunk1", "chunk2", "source-a--source-b")

        assert rel is None

    def test_invalid_type_returns_none(self):
        """Test that invalid type returns None."""
        response = {
            "type": "invalid",
            "confidence": 0.8,
            "explanation": "Test",
        }

        rel = validate_llm_response(response, "chunk1", "chunk2", "source-a--source-b")

        assert rel is None

    def test_missing_fields_returns_none(self):
        """Test that missing fields return None."""
        response = {"type": "extends"}  # Missing confidence and explanation

        # Should not raise, just return None or partial
        rel = validate_llm_response(response, "chunk1", "chunk2", "source-a--source-b")
        # It will create with defaults (0.0 confidence, "" explanation)
        # But validation in Relationship might catch it


class TestPromptManager:
    """Tests for PromptManager."""

    def test_load_prompt(self):
        """Test loading the relationship prompt template."""
        pm = PromptManager()
        prompt = pm.load_prompt()

        assert "Chunk A" in prompt
        assert "Chunk B" in prompt
        assert "relates_to" in prompt
        assert "extends" in prompt
        assert "{source_title}" in prompt

    def test_format_prompt(self):
        """Test formatting a prompt with chunk data."""
        pm = PromptManager()

        formatted = pm.format_prompt(
            source_title="Deep Work",
            source_summary="Focus on cognitively demanding tasks.",
            target_title="Digital Minimalism",
            target_summary="Reduce digital distractions.",
        )

        assert "Deep Work" in formatted
        assert "Focus on cognitively demanding tasks" in formatted
        assert "Digital Minimalism" in formatted
        assert "Reduce digital distractions" in formatted
        # Placeholders should be replaced
        assert "{source_title}" not in formatted

    def test_format_prompt_with_none_values(self):
        """Test formatting with None values."""
        pm = PromptManager()

        formatted = pm.format_prompt(
            source_title=None,
            source_summary=None,
            target_title="Test",
            target_summary="Test summary",
        )

        assert "Unknown" in formatted  # Default for None title
        assert "Test" in formatted

    def test_create_relationship_prompt_convenience(self):
        """Test convenience function."""
        prompt = create_relationship_prompt(
            source_title="A",
            source_summary="Summary A",
            target_title="B",
            target_summary="Summary B",
        )

        assert "Summary A" in prompt
        assert "Summary B" in prompt

    def test_prompt_caching(self):
        """Test that prompts are cached."""
        pm = PromptManager()

        prompt1 = pm.load_prompt()
        prompt2 = pm.load_prompt()

        assert prompt1 is prompt2  # Same object from cache

    def test_get_prompt_stats(self):
        """Test getting prompt statistics."""
        pm = PromptManager()

        stats = pm.get_prompt_stats("Hello world, this is a test.")

        assert stats["char_count"] == 28
        assert stats["word_count"] == 6
        assert stats["estimated_tokens"] == 7  # 28 // 4


class TestRelationshipExtractor:
    """Tests for RelationshipExtractor."""

    def test_compute_similarity(self):
        """Test cosine similarity computation."""
        extractor = RelationshipExtractor()

        # Identical vectors = similarity 1.0
        vec = [1.0, 0.0, 0.0]
        similarity = extractor.compute_similarity(vec, vec)
        assert similarity == pytest.approx(1.0)

        # Orthogonal vectors = similarity 0.0
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        similarity = extractor.compute_similarity(vec_a, vec_b)
        assert similarity == pytest.approx(0.0)

        # Opposite vectors = similarity -1.0
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [-1.0, 0.0, 0.0]
        similarity = extractor.compute_similarity(vec_a, vec_b)
        assert similarity == pytest.approx(-1.0)

    def test_compute_similarity_zero_vector(self):
        """Test similarity with zero vector."""
        extractor = RelationshipExtractor()

        vec = [1.0, 2.0, 3.0]
        zero = [0.0, 0.0, 0.0]

        similarity = extractor.compute_similarity(vec, zero)
        assert similarity == 0.0

    def test_get_candidate_pairs_above_threshold(self):
        """Test filtering candidate pairs by similarity threshold."""
        extractor = RelationshipExtractor(similarity_threshold=0.8)

        # Create chunks with embeddings
        chunks = [
            {"id": "a", "embedding": [1.0, 0.0, 0.0]},
            {"id": "b", "embedding": [0.95, 0.31, 0.0]},  # ~0.95 similarity to a
            {"id": "c", "embedding": [0.0, 1.0, 0.0]},  # 0.0 similarity to a
        ]

        candidates = extractor.get_candidate_pairs(chunks)

        # Only a-b pair should be above 0.8 threshold
        assert len(candidates) == 1
        chunk_a, chunk_b, similarity = candidates[0]
        assert {chunk_a["id"], chunk_b["id"]} == {"a", "b"}
        assert similarity > 0.8

    def test_get_candidate_pairs_not_enough_chunks(self):
        """Test with less than 2 chunks."""
        extractor = RelationshipExtractor()

        chunks = [{"id": "a", "embedding": [1.0, 0.0]}]
        candidates = extractor.get_candidate_pairs(chunks)

        assert candidates == []

    def test_get_candidate_pairs_missing_embeddings(self):
        """Test chunks without embeddings are skipped."""
        extractor = RelationshipExtractor(similarity_threshold=0.0)

        chunks = [
            {"id": "a", "embedding": [1.0, 0.0]},
            {"id": "b", "embedding": None},  # Missing embedding
            {"id": "c"},  # No embedding key
        ]

        candidates = extractor.get_candidate_pairs(chunks)

        # Only 1 chunk has embedding, so no pairs
        assert candidates == []

    def test_get_chunk_summary_from_knowledge_card(self):
        """Test extracting summary from knowledge card."""
        extractor = RelationshipExtractor()

        chunk = {
            "content": "Long content here...",
            "knowledge_card": {"summary": "This is the KC summary"},
        }

        summary = extractor._get_chunk_summary(chunk)
        assert summary == "This is the KC summary"

    def test_get_chunk_summary_fallback_to_content(self):
        """Test fallback to content when no knowledge card."""
        extractor = RelationshipExtractor()

        chunk = {"content": "Short content"}

        summary = extractor._get_chunk_summary(chunk)
        assert summary == "Short content"

    def test_get_chunk_summary_truncates_long_content(self):
        """Test that long content is truncated."""
        extractor = RelationshipExtractor()

        long_content = "x" * 600
        chunk = {"content": long_content}

        summary = extractor._get_chunk_summary(chunk)
        assert len(summary) == 503  # 500 + "..."
        assert summary.endswith("...")

    @patch.object(RelationshipExtractor, "llm_client")
    def test_extract_relationship_success(self, mock_llm):
        """Test successful relationship extraction."""
        extractor = RelationshipExtractor(confidence_threshold=0.7)

        # Mock LLM response
        mock_llm.generate_json.return_value = {
            "type": "extends",
            "confidence": 0.85,
            "explanation": "B builds on A",
        }

        chunk_a = {"id": "chunk1", "title": "A", "content": "Content A"}
        chunk_b = {"id": "chunk2", "title": "B", "content": "Content B"}

        rel = extractor.extract_relationship(chunk_a, chunk_b, "source-a--source-b")

        assert rel is not None
        assert rel.type == "extends"
        assert rel.confidence == 0.85
        assert rel.source_chunk_id == "chunk1"
        assert rel.target_chunk_id == "chunk2"

    @patch.object(RelationshipExtractor, "llm_client")
    def test_extract_relationship_below_confidence(self, mock_llm):
        """Test relationship filtered by confidence threshold."""
        extractor = RelationshipExtractor(confidence_threshold=0.7)

        mock_llm.generate_json.return_value = {
            "type": "relates_to",
            "confidence": 0.5,  # Below threshold
            "explanation": "Weak connection",
        }

        chunk_a = {"id": "chunk1", "title": "A", "content": "Content A"}
        chunk_b = {"id": "chunk2", "title": "B", "content": "Content B"}

        rel = extractor.extract_relationship(chunk_a, chunk_b, "source-a--source-b")

        assert rel is None

    @patch.object(RelationshipExtractor, "llm_client")
    def test_extract_relationship_llm_error(self, mock_llm):
        """Test handling LLM errors gracefully."""
        extractor = RelationshipExtractor()

        mock_llm.generate_json.side_effect = Exception("API Error")

        chunk_a = {"id": "chunk1", "title": "A", "content": "Content A"}
        chunk_b = {"id": "chunk2", "title": "B", "content": "Content B"}

        rel = extractor.extract_relationship(chunk_a, chunk_b, "source-a--source-b")

        assert rel is None  # Should handle error gracefully

    @patch.object(RelationshipExtractor, "llm_client")
    def test_process_chunks(self, mock_llm):
        """Test processing chunks with source context."""
        extractor = RelationshipExtractor(
            similarity_threshold=0.5, confidence_threshold=0.7
        )

        # Mock LLM to return relationship
        mock_llm.generate_json.return_value = {
            "type": "supports",
            "confidence": 0.9,
            "explanation": "Evidence provided",
        }

        # Chunks with high similarity
        chunks = [
            {"id": "a", "title": "A", "content": "X", "embedding": [1.0, 0.0]},
            {"id": "b", "title": "B", "content": "Y", "embedding": [0.9, 0.44]},
        ]

        result = extractor.process_chunks(chunks, "source-a--source-b")

        assert result["candidates"] == 1
        assert result["extracted"] == 1
        assert len(result["relationships"]) == 1
        assert result["relationships"][0].type == "supports"
        assert result["relationships"][0].source_context == "source-a--source-b"


class TestMainModule:
    """Tests for main.py functions."""

    @patch("src.relationships.main.get_firestore_client")
    def test_save_relationships_dry_run(self, mock_get_client):
        """Test dry run doesn't write to Firestore."""
        from src.relationships.main import save_relationships

        relationships = [
            Relationship(
                source_chunk_id="a",
                target_chunk_id="b",
                type="extends",
                confidence=0.8,
                explanation="Test",
                source_context="source-a--source-b",
            )
        ]

        result = save_relationships(relationships, dry_run=True)

        assert result["saved"] == 1
        assert result["failed"] == 0
        mock_get_client.assert_not_called()

    @patch("src.relationships.main.get_firestore_client")
    def test_save_relationships_empty_list(self, mock_get_client):
        """Test saving empty list."""
        from src.relationships.main import save_relationships

        result = save_relationships([], dry_run=False)

        assert result["saved"] == 0
        assert result["failed"] == 0
