"""
Relationship Extractor

Core logic for extracting semantic relationships between chunks.
Uses embedding similarity for candidate filtering and LLM for relationship classification.
Epic 4, Story 4.1
"""

import logging
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .prompt_manager import PromptManager
from .schema import Relationship, validate_llm_response

logger = logging.getLogger(__name__)


class RelationshipExtractor:
    """
    Extracts semantic relationships between chunks using LLM.

    Process:
    1. Filter chunk pairs by embedding similarity (threshold)
    2. For each candidate pair, call LLM to classify relationship
    3. Filter results by confidence threshold
    """

    def __init__(
        self,
        similarity_threshold: float = 0.75,
        confidence_threshold: float = 0.7,
        model: Optional[str] = None,
    ):
        """
        Initialize relationship extractor.

        Args:
            similarity_threshold: Minimum cosine similarity for chunk pairs (default: 0.75)
            confidence_threshold: Minimum LLM confidence to keep relationship (default: 0.7)
            model: LLM model to use (default: from LLM_MODEL env or gemini-2.5-flash)
        """
        self.similarity_threshold = similarity_threshold
        self.confidence_threshold = confidence_threshold
        self.model = model

        self._llm_client = None
        self._prompt_manager = PromptManager()

    @property
    def llm_client(self):
        """Lazy initialization of LLM client."""
        if self._llm_client is None:
            from src.llm import get_client

            self._llm_client = get_client(self.model)
            logger.info(f"Initialized LLM client: {self._llm_client}")
        return self._llm_client

    def compute_similarity(
        self,
        embedding_a: List[float],
        embedding_b: List[float],
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding_a: First embedding vector
            embedding_b: Second embedding vector

        Returns:
            Cosine similarity score (0.0 to 1.0)
        """
        a = np.array(embedding_a)
        b = np.array(embedding_b)

        # Cosine similarity
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    def get_candidate_pairs(
        self,
        chunks: List[Dict[str, Any]],
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any], float]]:
        """
        Filter chunk pairs by embedding similarity.

        Args:
            chunks: List of chunk dictionaries with 'embedding' field

        Returns:
            List of (chunk_a, chunk_b, similarity) tuples above threshold
        """
        candidates = []

        # Filter chunks that have embeddings
        chunks_with_embeddings = [c for c in chunks if c.get("embedding") is not None]

        if len(chunks_with_embeddings) < 2:
            logger.warning(
                f"Not enough chunks with embeddings: {len(chunks_with_embeddings)}"
            )
            return []

        # Generate all pairs and compute similarity
        for chunk_a, chunk_b in combinations(chunks_with_embeddings, 2):
            similarity = self.compute_similarity(
                chunk_a["embedding"], chunk_b["embedding"]
            )

            if similarity >= self.similarity_threshold:
                candidates.append((chunk_a, chunk_b, similarity))

        # Sort by similarity (highest first)
        candidates.sort(key=lambda x: x[2], reverse=True)

        logger.info(
            f"Found {len(candidates)} candidate pairs above threshold "
            f"{self.similarity_threshold} from {len(chunks_with_embeddings)} chunks"
        )

        return candidates

    def _get_chunk_summary(self, chunk: Dict[str, Any]) -> str:
        """
        Extract summary from chunk's knowledge card or content.

        Args:
            chunk: Chunk dictionary

        Returns:
            Summary text for prompt
        """
        # Prefer knowledge card summary
        kc = chunk.get("knowledge_card", {})
        if isinstance(kc, dict) and kc.get("summary"):
            return kc["summary"]

        # Fallback to raw content (truncated)
        content = chunk.get("content", "")
        if len(content) > 500:
            content = content[:500] + "..."
        return content

    def extract_relationship(
        self,
        chunk_a: Dict[str, Any],
        chunk_b: Dict[str, Any],
        cluster_id: str,
    ) -> Optional[Relationship]:
        """
        Extract relationship between two chunks using LLM.

        Args:
            chunk_a: Source chunk dictionary
            chunk_b: Target chunk dictionary
            cluster_id: ID of the containing cluster

        Returns:
            Relationship if found and above confidence threshold, None otherwise
        """
        # Get chunk IDs
        source_id = chunk_a.get("id") or chunk_a.get("chunk_id")
        target_id = chunk_b.get("id") or chunk_b.get("chunk_id")

        if not source_id or not target_id:
            logger.warning("Chunk missing ID, skipping")
            return None

        # Build prompt
        prompt = self._prompt_manager.format_prompt(
            source_title=chunk_a.get("title", "Unknown"),
            source_summary=self._get_chunk_summary(chunk_a),
            target_title=chunk_b.get("title", "Unknown"),
            target_summary=self._get_chunk_summary(chunk_b),
        )

        try:
            # Call LLM for JSON response
            response = self.llm_client.generate_json(prompt)

            # Validate and convert response
            relationship = validate_llm_response(
                response=response,
                source_chunk_id=source_id,
                target_chunk_id=target_id,
                cluster_id=cluster_id,
            )

            # Filter by confidence threshold
            if relationship and relationship.confidence >= self.confidence_threshold:
                logger.debug(
                    f"Found relationship: {source_id} --[{relationship.type}]--> {target_id} "
                    f"(confidence: {relationship.confidence:.2f})"
                )
                return relationship

            return None

        except Exception as e:
            logger.warning(f"Failed to extract relationship: {e}")
            return None

    def process_cluster(
        self,
        cluster_id: str,
        chunks: List[Dict[str, Any]],
    ) -> List[Relationship]:
        """
        Process all chunk pairs in a cluster and extract relationships.

        Args:
            cluster_id: ID of the cluster
            chunks: List of chunks in the cluster

        Returns:
            List of extracted relationships
        """
        logger.info(f"Processing cluster {cluster_id} with {len(chunks)} chunks")

        # Get candidate pairs
        candidates = self.get_candidate_pairs(chunks)

        if not candidates:
            logger.info(f"No candidate pairs found in cluster {cluster_id}")
            return []

        relationships = []

        for i, (chunk_a, chunk_b, similarity) in enumerate(candidates):
            if (i + 1) % 10 == 0 or i == 0:
                logger.info(f"  Processing pair {i + 1}/{len(candidates)}...")

            relationship = self.extract_relationship(chunk_a, chunk_b, cluster_id)
            if relationship:
                relationships.append(relationship)

        logger.info(
            f"Cluster {cluster_id}: Extracted {len(relationships)} relationships "
            f"from {len(candidates)} candidates"
        )

        return relationships

    def process_chunks(
        self,
        chunks: List[Dict[str, Any]],
        cluster_id: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Process a list of chunks and extract all relationships.

        Args:
            chunks: List of chunk dictionaries
            cluster_id: Cluster ID to assign to relationships

        Returns:
            Dictionary with:
            - relationships: List of Relationship objects
            - candidates: Number of candidate pairs
            - extracted: Number of relationships extracted
        """
        candidates = self.get_candidate_pairs(chunks)
        relationships = []

        for chunk_a, chunk_b, similarity in candidates:
            rel = self.extract_relationship(chunk_a, chunk_b, cluster_id)
            if rel:
                relationships.append(rel)

        return {
            "relationships": relationships,
            "candidates": len(candidates),
            "extracted": len(relationships),
        }
