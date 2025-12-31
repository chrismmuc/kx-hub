"""
Cross-Source Relationship Extraction Pipeline

Extracts relationships between chunks from DIFFERENT sources only.
Epic 4, Story 4.2

Usage:
    python -m src.relationship_extraction.main --dry-run --limit 10
    python -m src.relationship_extraction.main --parallel 10

Environment Variables:
    GCP_PROJECT: Google Cloud project ID (default: kx-hub)
    SIMILARITY_THRESHOLD: Min similarity for pairs (default: 0.80)
    CONFIDENCE_THRESHOLD: Min confidence for relationships (default: 0.7)
"""

import argparse
import asyncio
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .extractor import RelationshipExtractor
from .schema import Relationship

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
GCP_PROJECT = os.environ.get("GCP_PROJECT", "kx-hub")
CHUNKS_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "kb_items")
SOURCES_COLLECTION = "sources"
RELATIONSHIPS_COLLECTION = "relationships"

# Thresholds - higher default for cross-source (quality over quantity)
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.80"))
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.8"))

# Batch size for Firestore writes
BATCH_SIZE = 100

# Default parallelism
DEFAULT_PARALLEL = 5

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


def load_existing_pairs() -> set:
    """Load existing relationship pairs from Firestore to skip duplicates."""
    db = get_firestore_client()
    existing = set()

    for doc in db.collection(RELATIONSHIPS_COLLECTION).stream():
        data = doc.to_dict()
        pair = (data.get("source_chunk_id"), data.get("target_chunk_id"))
        existing.add(pair)

    logger.info(f"Found {len(existing)} existing relationships to skip")
    return existing


def load_chunks_by_source() -> Dict[str, List[Dict[str, Any]]]:
    """
    Load all chunks grouped by source_id.

    Returns:
        Dictionary mapping source_id -> list of chunks
    """
    db = get_firestore_client()
    collection_ref = db.collection(CHUNKS_COLLECTION)

    sources: Dict[str, List[Dict[str, Any]]] = {}

    for doc in collection_ref.stream():
        chunk_data = doc.to_dict()
        chunk_data["id"] = doc.id

        source_id = chunk_data.get("source_id")
        if not source_id:
            continue

        if source_id not in sources:
            sources[source_id] = []
        sources[source_id].append(chunk_data)

    logger.info(
        f"Loaded {sum(len(c) for c in sources.values())} chunks from {len(sources)} sources"
    )
    return sources


def compute_similarity(embedding_a: List[float], embedding_b: List[float]) -> float:
    """Compute cosine similarity between two embeddings."""
    a = np.array(embedding_a)
    b = np.array(embedding_b)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def find_cross_source_pairs(
    sources: Dict[str, List[Dict[str, Any]]],
    similarity_threshold: float,
    limit: Optional[int] = None,
) -> List[Tuple[Dict[str, Any], Dict[str, Any], float]]:
    """
    Find all chunk pairs from different sources above similarity threshold.

    Args:
        sources: Dictionary mapping source_id -> chunks
        similarity_threshold: Minimum cosine similarity
        limit: Optional limit on number of pairs

    Returns:
        List of (chunk_a, chunk_b, similarity) tuples
    """
    pairs = []
    source_ids = list(sources.keys())

    logger.info(f"Finding cross-source pairs from {len(source_ids)} sources...")

    # Compare all source pairs
    total_comparisons = 0
    for source_a, source_b in combinations(source_ids, 2):
        chunks_a = sources[source_a]
        chunks_b = sources[source_b]

        for chunk_a in chunks_a:
            if not chunk_a.get("embedding"):
                continue

            for chunk_b in chunks_b:
                if not chunk_b.get("embedding"):
                    continue

                total_comparisons += 1
                sim = compute_similarity(chunk_a["embedding"], chunk_b["embedding"])

                if sim >= similarity_threshold:
                    pairs.append((chunk_a, chunk_b, sim))

                    if limit and len(pairs) >= limit:
                        logger.info(f"Reached limit of {limit} pairs")
                        return pairs

    # Sort by similarity (highest first)
    pairs.sort(key=lambda x: x[2], reverse=True)

    logger.info(
        f"Found {len(pairs)} cross-source pairs above {similarity_threshold} "
        f"(from {total_comparisons:,} comparisons)"
    )

    return pairs


def save_relationships(
    relationships: List[Relationship],
    dry_run: bool = False,
) -> Dict[str, int]:
    """Save relationships to Firestore."""
    if not relationships:
        return {"saved": 0, "failed": 0}

    if dry_run:
        logger.info(f"DRY RUN: Would save {len(relationships)} relationships")
        return {"saved": len(relationships), "failed": 0}

    db = get_firestore_client()
    collection_ref = db.collection(RELATIONSHIPS_COLLECTION)

    saved = 0
    failed = 0

    for i in range(0, len(relationships), BATCH_SIZE):
        batch = db.batch()
        batch_rels = relationships[i : i + BATCH_SIZE]

        for rel in batch_rels:
            try:
                doc_ref = collection_ref.document()
                batch.set(doc_ref, rel.to_dict())
                saved += 1
            except Exception as e:
                logger.error(f"Failed to prepare relationship: {e}")
                failed += 1

        try:
            batch.commit()
            logger.info(
                f"Saved batch {i // BATCH_SIZE + 1}: {len(batch_rels)} relationships"
            )
        except Exception as e:
            logger.error(f"Batch write failed: {e}")
            failed += len(batch_rels)
            saved -= len(batch_rels)

    return {"saved": saved, "failed": failed}


def process_pair(
    extractor: RelationshipExtractor,
    chunk_a: Dict[str, Any],
    chunk_b: Dict[str, Any],
    pair_index: int,
    total_pairs: int,
) -> Optional[Relationship]:
    """Process a single chunk pair and extract relationship."""
    try:
        # Use source_id as context instead of cluster_id
        source_a = chunk_a.get("source_id", "unknown")
        source_b = chunk_b.get("source_id", "unknown")
        context = f"{source_a}--{source_b}"

        rel = extractor.extract_relationship(chunk_a, chunk_b, context)

        if rel:
            logger.debug(
                f"[{pair_index}/{total_pairs}] Found: {rel.type} "
                f"(confidence: {rel.confidence:.2f})"
            )

        return rel

    except Exception as e:
        logger.warning(f"[{pair_index}/{total_pairs}] Error: {e}")
        return None


def process_pairs_sequential(
    extractor: RelationshipExtractor,
    pairs: List[Tuple[Dict[str, Any], Dict[str, Any], float]],
) -> List[Relationship]:
    """Process pairs sequentially."""
    relationships = []

    for i, (chunk_a, chunk_b, sim) in enumerate(pairs):
        if (i + 1) % 10 == 0 or i == 0:
            logger.info(f"Processing pair {i + 1}/{len(pairs)}...")

        rel = process_pair(extractor, chunk_a, chunk_b, i + 1, len(pairs))
        if rel:
            relationships.append(rel)

    return relationships


def process_pairs_parallel(
    extractor: RelationshipExtractor,
    pairs: List[Tuple[Dict[str, Any], Dict[str, Any], float]],
    max_workers: int = DEFAULT_PARALLEL,
) -> List[Relationship]:
    """Process pairs in parallel using ThreadPoolExecutor."""
    relationships = []
    total = len(pairs)
    completed = 0

    logger.info(f"Processing {total} pairs with {max_workers} parallel workers...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(process_pair, extractor, chunk_a, chunk_b, i + 1, total): i
            for i, (chunk_a, chunk_b, sim) in enumerate(pairs)
        }

        # Collect results as they complete
        for future in as_completed(futures):
            completed += 1

            if completed % 20 == 0:
                logger.info(f"Completed {completed}/{total} pairs...")

            try:
                rel = future.result()
                if rel:
                    relationships.append(rel)
            except Exception as e:
                logger.warning(f"Future failed: {e}")

    return relationships


def run_extraction(
    dry_run: bool = False,
    limit: Optional[int] = None,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    parallel: int = 0,
) -> Dict[str, Any]:
    """
    Run cross-source relationship extraction.

    Args:
        dry_run: If True, don't write to Firestore
        limit: Optional limit on pairs to process
        similarity_threshold: Minimum embedding similarity
        confidence_threshold: Minimum LLM confidence
        parallel: Number of parallel workers (0 = sequential)

    Returns:
        Pipeline results
    """
    start_time = datetime.now()

    logger.info("=" * 70)
    logger.info("Cross-Source Relationship Extraction")
    logger.info(f"Similarity threshold: {similarity_threshold}")
    logger.info(f"Confidence threshold: {confidence_threshold}")
    logger.info(f"Parallel workers: {parallel or 'sequential'}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 70)

    # Load existing pairs to skip
    existing_pairs = load_existing_pairs()

    # Load chunks by source
    sources = load_chunks_by_source()

    # Find cross-source pairs
    all_pairs = find_cross_source_pairs(sources, similarity_threshold, limit)

    # Filter out already processed pairs
    pairs = [
        (a, b, sim)
        for a, b, sim in all_pairs
        if (a["id"], b["id"]) not in existing_pairs
        and (b["id"], a["id"]) not in existing_pairs
    ]

    skipped = len(all_pairs) - len(pairs)
    if skipped > 0:
        logger.info(
            f"Skipping {skipped} already processed pairs, {len(pairs)} remaining"
        )

    if not pairs:
        logger.info("No pairs found above threshold")
        return {
            "sources": len(sources),
            "pairs": 0,
            "relationships": 0,
            "duration": 0,
        }

    # Initialize extractor
    extractor = RelationshipExtractor(
        similarity_threshold=similarity_threshold,
        confidence_threshold=confidence_threshold,
    )

    # Process pairs
    if parallel > 0:
        relationships = process_pairs_parallel(extractor, pairs, parallel)
    else:
        relationships = process_pairs_sequential(extractor, pairs)

    # Save relationships
    save_result = save_relationships(relationships, dry_run)

    duration = (datetime.now() - start_time).total_seconds()

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("Extraction Complete")
    logger.info(f"Sources: {len(sources)}")
    logger.info(f"Cross-source pairs processed: {len(pairs)}")
    logger.info(f"Relationships extracted: {len(relationships)}")
    logger.info(f"Saved: {save_result['saved']}")
    logger.info(f"Failed: {save_result['failed']}")
    logger.info(f"Duration: {duration:.1f}s")
    if len(pairs) > 0:
        logger.info(f"Avg time per pair: {duration / len(pairs):.2f}s")
    logger.info("=" * 70)

    return {
        "sources": len(sources),
        "pairs": len(pairs),
        "relationships": len(relationships),
        "saved": save_result["saved"],
        "failed": save_result["failed"],
        "duration": duration,
    }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract cross-source relationships between chunks"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Extract but don't save to Firestore"
    )
    parser.add_argument("--limit", type=int, help="Limit number of pairs to process")
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=SIMILARITY_THRESHOLD,
        help=f"Min embedding similarity (default: {SIMILARITY_THRESHOLD})",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=CONFIDENCE_THRESHOLD,
        help=f"Min LLM confidence (default: {CONFIDENCE_THRESHOLD})",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=0,
        help="Number of parallel workers (default: 0 = sequential)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        result = run_extraction(
            dry_run=args.dry_run,
            limit=args.limit,
            similarity_threshold=args.similarity_threshold,
            confidence_threshold=args.confidence_threshold,
            parallel=args.parallel,
        )

        if result.get("failed", 0) > 0:
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
