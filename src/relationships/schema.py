"""
Schema definitions for Relationship Extraction

Defines the Relationship dataclass and validation functions.
Epic 4, Story 4.1
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


# Fixed relationship types (no dynamic ontology)
RelationType = Literal[
    "relates_to",  # General thematic connection
    "extends",  # Builds upon, develops further
    "supports",  # Provides evidence, confirms
    "contradicts",  # Conflicts with, challenges
    "applies_to",  # Practical application of
    "none",  # No meaningful relationship (filtered out)
]

RELATIONSHIP_TYPES = {
    "relates_to": "General thematic connection between chunks",
    "extends": "Target chunk builds upon or develops source chunk further",
    "supports": "Target chunk provides evidence or confirms source chunk",
    "contradicts": "Target chunk conflicts with or challenges source chunk",
    "applies_to": "Target chunk is a practical application of source chunk",
    "none": "No meaningful relationship exists",
}


@dataclass
class Relationship:
    """
    Represents a semantic relationship between two chunks.

    Attributes:
        source_chunk_id: ID of the source chunk
        target_chunk_id: ID of the target chunk
        type: One of the fixed relationship types
        confidence: LLM confidence score (0.0-1.0)
        explanation: Brief explanation of why this relationship exists
        source_context: Context info (e.g., "source_a--source_b" for cross-source)
        created_at: Timestamp when relationship was extracted
    """

    source_chunk_id: str
    target_chunk_id: str
    type: RelationType
    confidence: float
    explanation: str
    source_context: str  # Replaces cluster_id
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self):
        """Validate fields after initialization."""
        if self.type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Invalid relationship type: {self.type}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            )
        if self.source_chunk_id == self.target_chunk_id:
            raise ValueError("Source and target chunk IDs must be different")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for Firestore storage.

        Returns:
            Dictionary with all fields serialized
        """
        return {
            "source_chunk_id": self.source_chunk_id,
            "target_chunk_id": self.target_chunk_id,
            "type": self.type,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "source_context": self.source_context,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Relationship":
        """
        Create Relationship from dictionary (e.g., from Firestore).

        Args:
            data: Dictionary with relationship fields

        Returns:
            Relationship instance
        """
        return cls(
            source_chunk_id=data["source_chunk_id"],
            target_chunk_id=data["target_chunk_id"],
            type=data["type"],
            confidence=data["confidence"],
            explanation=data["explanation"],
            source_context=data.get("source_context", data.get("cluster_id", "")),
            created_at=data.get("created_at", _utc_now()),
        )


def validate_llm_response(
    response: Dict[str, Any],
    source_chunk_id: str,
    target_chunk_id: str,
    source_context: str,
) -> Optional[Relationship]:
    """
    Validate and convert LLM response to Relationship.

    Args:
        response: Parsed JSON from LLM containing type, confidence, explanation
        source_chunk_id: ID of source chunk
        target_chunk_id: ID of target chunk
        source_context: Context info (e.g., source IDs)

    Returns:
        Relationship if valid, None if type is "none" or validation fails

    Example:
        >>> response = {"type": "extends", "confidence": 0.85, "explanation": "..."}
        >>> rel = validate_llm_response(response, "chunk1", "chunk2", "source-a--source-b")
    """
    try:
        rel_type = response.get("type", "none")

        # Filter out "none" relationships
        if rel_type == "none":
            return None

        # Validate type
        if rel_type not in RELATIONSHIP_TYPES:
            return None

        confidence = float(response.get("confidence", 0.0))
        explanation = str(response.get("explanation", ""))

        return Relationship(
            source_chunk_id=source_chunk_id,
            target_chunk_id=target_chunk_id,
            type=rel_type,
            confidence=confidence,
            explanation=explanation,
            source_context=source_context,
        )

    except (ValueError, TypeError, KeyError) as e:
        # Log would be added here in production
        return None
