"""
Cross-Source Relationship Extraction for Knowledge Base

Extracts semantic relationships between chunks from different sources.
Epic 4, Story 4.2/4.5

Usage:
    from relationships import RelationshipExtractor

    extractor = RelationshipExtractor()
    rel = extractor.extract_relationship(chunk_a, chunk_b, context)
"""

from .extractor import RelationshipExtractor
from .schema import RELATIONSHIP_TYPES, Relationship, RelationType

__all__ = [
    "Relationship",
    "RelationType",
    "RELATIONSHIP_TYPES",
    "RelationshipExtractor",
]
