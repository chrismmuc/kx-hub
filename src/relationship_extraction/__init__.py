"""
Relationship Extraction for Knowledge Base

Extracts semantic relationships between chunks within clusters.
Epic 4, Story 4.1: Chunk-to-Chunk Relationship Extraction

Usage:
    from relationship_extraction import RelationshipExtractor

    extractor = RelationshipExtractor()
    relationships = extractor.process_cluster(cluster_id, chunks)
"""

from .extractor import RelationshipExtractor
from .schema import RELATIONSHIP_TYPES, Relationship, RelationType

__all__ = [
    "Relationship",
    "RelationType",
    "RELATIONSHIP_TYPES",
    "RelationshipExtractor",
]
