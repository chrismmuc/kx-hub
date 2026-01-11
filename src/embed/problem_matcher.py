"""
Problem Matcher: Match new chunks to active Feynman-style problems.

Epic 10 Story 10.2: Pipeline Integration

This module provides functions to:
1. Match new chunks against active problems using embedding similarity
2. Check for contradictions based on source relationships
3. Batch update problems with new evidence

Usage:
    from problem_matcher import match_chunks_to_problems

    result = match_chunks_to_problems(
        chunk_ids=["chunk_123", "chunk_456"],
        similarity_threshold=0.7
    )
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

# Similarity threshold for matching chunks to problems
DEFAULT_SIMILARITY_THRESHOLD = 0.7

# Global Firestore client (lazy initialization)
_firestore_client = None


def get_firestore_client() -> firestore.Client:
    """Get or create Firestore client instance (cached)."""
    global _firestore_client

    if _firestore_client is None:
        project = os.getenv("GCP_PROJECT")
        logger.info(f"Initializing Firestore client for project: {project}")
        _firestore_client = firestore.Client(project=project)

    return _firestore_client


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Cosine similarity score (0.0 to 1.0)
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def get_active_problems_with_embeddings() -> List[Dict[str, Any]]:
    """
    Get all active problems with their embeddings.

    Returns:
        List of active problems with problem_id, problem, embedding
    """
    try:
        db = get_firestore_client()

        query = db.collection("problems").where("status", "==", "active")

        problems = []
        for doc in query.stream():
            data = doc.to_dict()
            embedding = data.get("embedding", [])
            if embedding:  # Only include problems with embeddings
                problems.append({
                    "problem_id": doc.id,
                    "problem": data.get("problem", ""),
                    "embedding": embedding,
                    "evidence": data.get("evidence", []),
                })

        logger.info(f"Retrieved {len(problems)} active problems with embeddings")
        return problems

    except Exception as e:
        logger.error(f"Failed to get active problems: {e}")
        return []


def get_chunk_with_embedding(chunk_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a chunk with its embedding from kb_items.

    Args:
        chunk_id: Chunk document ID

    Returns:
        Chunk data with embedding, or None if not found
    """
    try:
        db = get_firestore_client()
        doc = db.collection("kb_items").document(chunk_id).get()

        if not doc.exists:
            return None

        data = doc.to_dict()
        data["chunk_id"] = doc.id
        return data

    except Exception as e:
        logger.error(f"Failed to get chunk {chunk_id}: {e}")
        return None


def get_source_relationships(source_id: str) -> List[Dict[str, Any]]:
    """
    Get relationships for a source (for contradiction detection).

    Args:
        source_id: Source document ID

    Returns:
        List of relationship dictionaries
    """
    try:
        db = get_firestore_client()

        # Query relationships where this source is involved
        relationships = []

        # Get relationships where this source is the source
        source_query = db.collection("relationships").where(
            "source_source_id", "==", source_id
        )
        for doc in source_query.stream():
            data = doc.to_dict()
            relationships.append({
                "type": data.get("type"),
                "target_source": data.get("target_source_id"),
                "context": data.get("explanation", ""),
            })

        return relationships

    except Exception as e:
        logger.warning(f"Failed to get relationships for source {source_id}: {e}")
        return []


def check_for_contradiction(
    chunk_source_id: str,
    existing_evidence: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
) -> bool:
    """
    Check if a chunk's source contradicts any existing evidence sources.

    Args:
        chunk_source_id: Source ID of the new chunk
        existing_evidence: List of existing evidence for the problem
        relationships: List of relationships for the chunk's source

    Returns:
        True if contradiction found
    """
    # Get source IDs from existing evidence
    existing_source_ids = set()
    for ev in existing_evidence:
        source_id = ev.get("source_id")
        if source_id:
            existing_source_ids.add(source_id)

    # Check if any relationship is a contradiction with existing sources
    for rel in relationships:
        if rel.get("type") == "contradicts":
            target = rel.get("target_source")
            if target in existing_source_ids:
                return True

    return False


def add_evidence_to_problem(
    problem_id: str,
    evidence: Dict[str, Any],
) -> bool:
    """
    Add evidence to a problem document.

    Args:
        problem_id: Problem document ID
        evidence: Evidence dictionary

    Returns:
        True if successful
    """
    try:
        db = get_firestore_client()

        doc_ref = db.collection("problems").document(problem_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.error(f"Problem {problem_id} not found")
            return False

        data = doc.to_dict()
        existing_evidence = data.get("evidence", [])

        # Check for duplicate
        chunk_id = evidence.get("chunk_id")
        for ev in existing_evidence:
            if ev.get("chunk_id") == chunk_id:
                logger.debug(f"Evidence for chunk {chunk_id} already exists")
                return True

        # Add new evidence
        existing_evidence.append(evidence)

        # Update counts
        evidence_count = len(existing_evidence)
        contradiction_count = sum(
            1 for ev in existing_evidence if ev.get("is_contradiction", False)
        )

        doc_ref.update({
            "evidence": existing_evidence,
            "evidence_count": evidence_count,
            "contradiction_count": contradiction_count,
            "updated_at": datetime.utcnow(),
        })

        logger.info(
            f"Added evidence to problem {problem_id}: chunk={chunk_id}, "
            f"is_contradiction={evidence.get('is_contradiction', False)}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to add evidence to problem {problem_id}: {e}")
        return False


def match_chunks_to_problems(
    chunk_ids: List[str],
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> Dict[str, Any]:
    """
    Match new chunks to active problems using embedding similarity.

    Called after embed function completes to connect new content
    to user's Feynman-style problems.

    Args:
        chunk_ids: List of newly embedded chunk IDs
        similarity_threshold: Minimum similarity score (default 0.7)

    Returns:
        Dictionary with:
        - chunks_processed: Number of chunks processed
        - matches_found: Number of matches found
        - contradictions_found: Number of contradictions detected
        - problems_updated: Set of problem IDs that received new evidence
    """
    if not chunk_ids:
        return {
            "chunks_processed": 0,
            "matches_found": 0,
            "contradictions_found": 0,
            "problems_updated": [],
        }

    logger.info(
        f"Matching {len(chunk_ids)} chunks to problems "
        f"(threshold={similarity_threshold})"
    )

    # Get active problems with embeddings
    problems = get_active_problems_with_embeddings()

    if not problems:
        logger.info("No active problems found, skipping matching")
        return {
            "chunks_processed": len(chunk_ids),
            "matches_found": 0,
            "contradictions_found": 0,
            "problems_updated": [],
        }

    matches_found = 0
    contradictions_found = 0
    problems_updated = set()

    for chunk_id in chunk_ids:
        chunk = get_chunk_with_embedding(chunk_id)
        if not chunk:
            logger.warning(f"Chunk {chunk_id} not found, skipping")
            continue

        chunk_embedding = chunk.get("embedding")
        if not chunk_embedding:
            logger.warning(f"Chunk {chunk_id} has no embedding, skipping")
            continue

        # Convert Firestore Vector to list if needed
        if hasattr(chunk_embedding, 'to_map_value'):
            chunk_embedding = list(chunk_embedding)

        chunk_source_id = chunk.get("source_id")
        chunk_source_title = chunk.get("title", "Unknown")

        # Get first 200 chars of content as quote
        content = chunk.get("content", "")
        quote = content[:200] + "..." if len(content) > 200 else content

        # Get source relationships for contradiction detection
        relationships = []
        if chunk_source_id:
            relationships = get_source_relationships(chunk_source_id)

        for problem in problems:
            problem_embedding = problem.get("embedding", [])

            # Calculate similarity
            similarity = cosine_similarity(chunk_embedding, problem_embedding)

            if similarity >= similarity_threshold:
                # Check for contradiction
                is_contradiction = check_for_contradiction(
                    chunk_source_id,
                    problem.get("evidence", []),
                    relationships,
                )

                # Build evidence object
                evidence = {
                    "chunk_id": chunk_id,
                    "source_id": chunk_source_id,
                    "source_title": chunk_source_title,
                    "quote": quote,
                    "similarity": round(similarity, 4),
                    "added_at": datetime.utcnow(),
                    "is_contradiction": is_contradiction,
                }

                # Add relationship info if this is a contradiction
                if is_contradiction and relationships:
                    for rel in relationships:
                        if rel.get("type") == "contradicts":
                            evidence["relationship"] = rel
                            break

                # Add evidence to problem
                if add_evidence_to_problem(problem["problem_id"], evidence):
                    matches_found += 1
                    problems_updated.add(problem["problem_id"])
                    if is_contradiction:
                        contradictions_found += 1

                    logger.info(
                        f"Matched chunk {chunk_id} to problem {problem['problem_id']} "
                        f"(similarity={similarity:.3f}, contradiction={is_contradiction})"
                    )

    result = {
        "chunks_processed": len(chunk_ids),
        "matches_found": matches_found,
        "contradictions_found": contradictions_found,
        "problems_updated": list(problems_updated),
    }

    logger.info(
        f"Problem matching complete: {result['matches_found']} matches, "
        f"{result['contradictions_found']} contradictions, "
        f"{len(result['problems_updated'])} problems updated"
    )

    return result
