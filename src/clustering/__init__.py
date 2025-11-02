"""
Semantic clustering module for kx-hub knowledge base.

Provides clustering functionality to group knowledge chunks by topic similarity
using HDBSCAN or K-Means algorithms on existing embeddings.

Two execution modes:
1. Initial load: Bulk clustering of all existing chunks (local script)
2. Delta processing: Incremental clustering of new chunks (Cloud Function)
"""

from .clusterer import SemanticClusterer

__all__ = ['SemanticClusterer']
