"""
Relationship Extraction Pipeline

Main entry point for extracting relationships between chunks.
Epic 4, Story 4.1

Usage:
    python -m src.relationship_extraction.main
    python -m src.relationship_extraction.main --cluster cluster_123
    python -m src.relationship_extraction.main --dry-run --limit 5

Environment Variables:
    GCP_PROJECT: Google Cloud project ID (default: kx-hub)
    FIRESTORE_COLLECTION: Chunks collection (default: kb_items)
    SIMILARITY_THRESHOLD: Min similarity for pairs (default: 0.75)
    CONFIDENCE_THRESHOLD: Min confidence for relationships (default: 0.7)
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from .extractor import RelationshipExtractor
from .schema import Relationship

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
GCP_PROJECT = os.environ.get("GCP_PROJECT", "kx-hub")
FIRESTORE_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "kb_items")
RELATIONSHIPS_COLLECTION = "relationships"
CLUSTERS_COLLECTION = "clusters"

# Thresholds
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.75"))
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))

# Batch size for Firestore writes
BATCH_SIZE = 100

# Global Firestore client
_firestore_client = None


def get_firestore_client():
    """Get or create Firestore client instance."""
    global _firestore_client

    if _firestore_client is None:
        from google.cloud import firestore

        _firestore_client = firestore.Client(project=GCP_PROJECT)
        logger.info(f"Initialized Firestore client for project: {GCP_PROJECT}")

    return _firestore_client


def load_chunks_grouped_by_cluster() -> Dict[str, List[Dict[str, Any]]]:
    """
    Load all chunks from Firestore and group by cluster_id.

    Returns:
        Dictionary mapping cluster_id -> list of chunks
    """
    db = get_firestore_client()
    collection_ref = db.collection(FIRESTORE_COLLECTION)

    # Group chunks by cluster
    clusters: Dict[str, List[Dict[str, Any]]] = {}

    for doc in collection_ref.stream():
        chunk_data = doc.to_dict()
        chunk_data["id"] = doc.id

        # cluster_id is stored as a list in chunks
        cluster_ids = chunk_data.get("cluster_id", [])
        if isinstance(cluster_ids, str):
            cluster_ids = [cluster_ids]

        for cluster_id in cluster_ids:
            if cluster_id not in clusters:
                clusters[cluster_id] = []
            clusters[cluster_id].append(chunk_data)

    logger.info(
        f"Loaded chunks into {len(clusters)} clusters "
        f"(total chunks with cluster: {sum(len(c) for c in clusters.values())})"
    )
    return clusters


def load_chunks_for_cluster(cluster_id: str) -> List[Dict[str, Any]]:
    """
    Load chunks for a specific cluster from Firestore.

    Args:
        cluster_id: Cluster ID to filter by

    Returns:
        List of chunk dictionaries with embeddings
    """
    db = get_firestore_client()
    collection_ref = db.collection(FIRESTORE_COLLECTION)

    chunks = []

    # Query chunks where cluster_id array contains the cluster
    query = collection_ref.where("cluster_id", "array_contains", cluster_id)

    for doc in query.stream():
        chunk_data = doc.to_dict()
        chunk_data["id"] = doc.id
        chunks.append(chunk_data)

    logger.debug(f"Loaded {len(chunks)} chunks for cluster {cluster_id}")
    return chunks


def save_relationships(
    relationships: List[Relationship],
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Save relationships to Firestore.

    Args:
        relationships: List of Relationship objects
        dry_run: If True, don't write to Firestore

    Returns:
        Dictionary with saved and failed counts
    """
    if not relationships:
        return {"saved": 0, "failed": 0}

    if dry_run:
        logger.info(f"DRY RUN: Would save {len(relationships)} relationships")
        return {"saved": len(relationships), "failed": 0}

    db = get_firestore_client()
    collection_ref = db.collection(RELATIONSHIPS_COLLECTION)

    saved = 0
    failed = 0

    # Batch writes for efficiency
    for i in range(0, len(relationships), BATCH_SIZE):
        batch = db.batch()
        batch_relationships = relationships[i : i + BATCH_SIZE]

        for rel in batch_relationships:
            try:
                # Create new document with auto-generated ID
                doc_ref = collection_ref.document()
                batch.set(doc_ref, rel.to_dict())
                saved += 1
            except Exception as e:
                logger.error(f"Failed to prepare relationship: {e}")
                failed += 1

        try:
            batch.commit()
            logger.info(
                f"Batch {i // BATCH_SIZE + 1}: Saved {len(batch_relationships)} relationships"
            )
        except Exception as e:
            logger.error(f"Batch write failed: {e}")
            failed += len(batch_relationships)
            saved -= len(batch_relationships)

    return {"saved": saved, "failed": failed}


def process_single_cluster(
    cluster_id: str,
    extractor: RelationshipExtractor,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Process a single cluster and extract relationships.

    Args:
        cluster_id: Cluster ID to process
        extractor: RelationshipExtractor instance
        dry_run: If True, don't save to Firestore

    Returns:
        Processing statistics
    """
    # Load chunks for this cluster
    chunks = load_chunks_for_cluster(cluster_id)

    if len(chunks) < 2:
        logger.info(f"Cluster {cluster_id} has < 2 chunks, skipping")
        return {"chunks": len(chunks), "relationships": 0}

    # Extract relationships
    relationships = extractor.process_cluster(cluster_id, chunks)

    # Save
    save_result = save_relationships(relationships, dry_run)

    return {
        "cluster_id": cluster_id,
        "chunks": len(chunks),
        "candidates": len(extractor.get_candidate_pairs(chunks)),
        "relationships": len(relationships),
        "saved": save_result["saved"],
        "failed": save_result["failed"],
    }


def process_all_clusters(
    dry_run: bool = False,
    limit: Optional[int] = None,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> Dict[str, Any]:
    """
    Process all clusters and extract relationships.

    Args:
        dry_run: If True, don't write to Firestore
        limit: Optional limit on number of clusters to process
        similarity_threshold: Minimum embedding similarity for pairs
        confidence_threshold: Minimum LLM confidence for relationships

    Returns:
        Pipeline results dictionary
    """
    start_time = datetime.now()

    logger.info("=" * 80)
    logger.info("Relationship Extraction Pipeline - Starting")
    logger.info(f"Similarity threshold: {similarity_threshold}")
    logger.info(f"Confidence threshold: {confidence_threshold}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 80)

    # Initialize extractor
    extractor = RelationshipExtractor(
        similarity_threshold=similarity_threshold,
        confidence_threshold=confidence_threshold,
    )

    # Load all chunks grouped by cluster
    cluster_chunks = load_chunks_grouped_by_cluster()

    # Sort clusters by size (largest first) for better progress visibility
    cluster_ids = sorted(
        cluster_chunks.keys(), key=lambda c: len(cluster_chunks[c]), reverse=True
    )

    if limit:
        cluster_ids = cluster_ids[:limit]
        logger.info(f"Limited to {limit} clusters")

    # Process each cluster
    total_chunks = 0
    total_candidates = 0
    total_relationships = 0
    total_saved = 0
    total_failed = 0
    clusters_with_relationships = 0

    for i, cluster_id in enumerate(cluster_ids):
        chunks = cluster_chunks[cluster_id]

        logger.info(
            f"\n[{i + 1}/{len(cluster_ids)}] Processing cluster: {cluster_id} ({len(chunks)} chunks)"
        )

        if len(chunks) < 2:
            logger.info(f"  Skipping: < 2 chunks")
            continue

        total_chunks += len(chunks)

        # Get candidates
        candidates = extractor.get_candidate_pairs(chunks)
        total_candidates += len(candidates)

        if not candidates:
            logger.info(f"  No candidate pairs above similarity threshold")
            continue

        # Extract relationships
        relationships = extractor.process_cluster(cluster_id, chunks)
        total_relationships += len(relationships)

        if relationships:
            clusters_with_relationships += 1

        # Save
        save_result = save_relationships(relationships, dry_run)
        total_saved += save_result["saved"]
        total_failed += save_result["failed"]

        logger.info(
            f"  Candidates: {len(candidates)}, Relationships: {len(relationships)}"
        )

    duration = (datetime.now() - start_time).total_seconds()

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Relationship Extraction Pipeline - Complete")
    logger.info(f"Clusters processed: {len(cluster_ids)}")
    logger.info(f"Clusters with relationships: {clusters_with_relationships}")
    logger.info(f"Total chunks: {total_chunks}")
    logger.info(f"Total candidates: {total_candidates}")
    logger.info(f"Total relationships: {total_relationships}")
    logger.info(f"Saved: {total_saved}")
    logger.info(f"Failed: {total_failed}")
    logger.info(f"Duration: {duration:.1f}s")
    logger.info("=" * 80)

    return {
        "clusters_processed": len(cluster_ids),
        "clusters_with_relationships": clusters_with_relationships,
        "total_chunks": total_chunks,
        "total_candidates": total_candidates,
        "total_relationships": total_relationships,
        "saved": total_saved,
        "failed": total_failed,
        "duration": duration,
    }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract semantic relationships between chunks"
    )
    parser.add_argument("--cluster", type=str, help="Process a single cluster by ID")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract relationships but don't save to Firestore",
    )
    parser.add_argument("--limit", type=int, help="Limit number of clusters to process")
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=SIMILARITY_THRESHOLD,
        help=f"Minimum embedding similarity (default: {SIMILARITY_THRESHOLD})",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=CONFIDENCE_THRESHOLD,
        help=f"Minimum LLM confidence (default: {CONFIDENCE_THRESHOLD})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        if args.cluster:
            # Process single cluster
            extractor = RelationshipExtractor(
                similarity_threshold=args.similarity_threshold,
                confidence_threshold=args.confidence_threshold,
            )
            result = process_single_cluster(
                args.cluster,
                extractor,
                dry_run=args.dry_run,
            )
            logger.info(f"Result: {result}")
        else:
            # Process all clusters
            result = process_all_clusters(
                dry_run=args.dry_run,
                limit=args.limit,
                similarity_threshold=args.similarity_threshold,
                confidence_threshold=args.confidence_threshold,
            )

        # Exit with error if failures
        if result.get("failed", 0) > 0:
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
