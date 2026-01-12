#!/usr/bin/env python3
"""
Backfill Problem Evidence: Match existing KB chunks to active problems.

This script performs a one-time backfill to connect existing knowledge base
content to Feynman-style problems. After running, the `problems(action="analyze")`
tool will return relevant evidence.

New content is automatically matched via the embed pipeline (nightly batch).

Usage:
    # Dry run (default) - see what would be matched
    python scripts/backfill_problem_evidence.py

    # Actually write matches to Firestore
    python scripts/backfill_problem_evidence.py --execute

    # Custom threshold (default 0.7)
    python scripts/backfill_problem_evidence.py --threshold 0.65 --execute

Cost: Essentially free (Firestore reads/writes only, embeddings already exist)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from google.cloud import firestore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Default similarity threshold (0.65 works better for German problems vs English content)
DEFAULT_THRESHOLD = 0.65


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def get_chunk_relationships(db: firestore.Client, chunk_id: str) -> List[Dict[str, Any]]:
    """Get ALL relationships for a chunk (both directions)."""
    relationships = []

    # Get relationships where this chunk is the SOURCE
    source_query = db.collection("relationships").where(
        "source_chunk_id", "==", chunk_id
    )
    for doc in source_query.stream():
        data = doc.to_dict()
        relationships.append({
            "type": data.get("type"),
            "target_chunk_id": data.get("target_chunk_id"),
            "context": data.get("explanation", ""),
            "direction": "outgoing",
        })

    # Get relationships where this chunk is the TARGET
    target_query = db.collection("relationships").where(
        "target_chunk_id", "==", chunk_id
    )
    for doc in target_query.stream():
        data = doc.to_dict()
        relationships.append({
            "type": data.get("type"),
            "target_chunk_id": data.get("source_chunk_id"),
            "context": data.get("explanation", ""),
            "direction": "incoming",
        })

    return relationships


def find_relationships_to_evidence(
    existing_evidence: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
    chunk_to_source: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Find ALL relationships between this chunk and existing evidence (SOURCE level)."""
    # Build set of existing evidence SOURCE IDs (not just chunks)
    existing_source_ids = {
        ev.get("source_id") for ev in existing_evidence
        if ev.get("source_id")
    }
    # Also map source_id to title for display
    source_to_title = {
        ev.get("source_id"): ev.get("source_title", "Unknown")
        for ev in existing_evidence if ev.get("source_id")
    }

    matching = []
    seen_sources = set()  # Avoid duplicate relationships to same source

    for rel in relationships:
        target_chunk_id = rel.get("target_chunk_id")
        # Get the SOURCE of the target chunk
        target_info = chunk_to_source.get(target_chunk_id, {})
        target_source_id = target_info.get("source_id", "")

        # Check if target SOURCE is in existing evidence (source-level match)
        if target_source_id and target_source_id in existing_source_ids:
            # Avoid duplicate relationships to same source
            rel_key = f"{rel.get('type')}:{target_source_id}"
            if rel_key not in seen_sources:
                seen_sources.add(rel_key)
                matching.append({
                    "type": rel.get("type"),
                    "target_source": target_source_id,
                    "target_title": source_to_title.get(target_source_id, target_info.get("title", "Unknown")),
                    "context": rel.get("context", ""),
                })

    return matching


def get_active_problems(db: firestore.Client) -> List[Dict[str, Any]]:
    """Get all active problems with embeddings."""
    problems = []
    query = db.collection("problems").where("status", "==", "active")

    for doc in query.stream():
        data = doc.to_dict()
        embedding = data.get("embedding", [])

        # Convert Vector to list if needed
        if hasattr(embedding, "to_map_value"):
            embedding = list(embedding)

        if embedding:
            problems.append({
                "problem_id": doc.id,
                "problem": data.get("problem", ""),
                "description": data.get("description", ""),
                "embedding": embedding,
                "existing_evidence": data.get("evidence", []),
            })

    return problems


def get_all_chunks(db: firestore.Client) -> List[Dict[str, Any]]:
    """Get all chunks with embeddings from kb_items."""
    chunks = []

    for doc in db.collection("kb_items").stream():
        data = doc.to_dict()
        embedding = data.get("embedding", [])

        # Convert Vector to list if needed
        if hasattr(embedding, "to_map_value"):
            embedding = list(embedding)

        if embedding:
            content = data.get("content", "")
            chunks.append({
                "chunk_id": doc.id,
                "embedding": embedding,
                "source_id": data.get("source_id"),
                "title": data.get("title", "Unknown"),
                "author": data.get("author", ""),
                "quote": content[:200] + "..." if len(content) > 200 else content,
            })

    return chunks


def find_matches(
    db: firestore.Client,
    problems: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    threshold: float,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Find all chunk-problem matches above threshold.

    Returns:
        Dict mapping problem_id to list of evidence dicts
    """
    matches: Dict[str, List[Dict[str, Any]]] = {p["problem_id"]: [] for p in problems}

    total_comparisons = len(problems) * len(chunks)
    logger.info(f"Running {total_comparisons:,} similarity comparisons...")

    # Build chunk_id -> source info mapping for relationship resolution
    chunk_to_source: Dict[str, Dict[str, str]] = {
        c["chunk_id"]: {"source_id": c["source_id"], "title": c["title"]}
        for c in chunks
    }

    # Cache relationships per chunk to avoid repeated lookups
    relationships_cache: Dict[str, List[Dict[str, Any]]] = {}

    comparison_count = 0
    match_count = 0
    relationships_found = 0

    for problem in problems:
        problem_embedding = problem["embedding"]
        existing_chunk_ids = {
            ev.get("chunk_id") for ev in problem["existing_evidence"]
        }
        # Track accumulated evidence for this problem (for relationship matching)
        accumulated_evidence = list(problem["existing_evidence"])

        for chunk in chunks:
            comparison_count += 1

            # Skip if already matched
            if chunk["chunk_id"] in existing_chunk_ids:
                continue

            similarity = cosine_similarity(problem_embedding, chunk["embedding"])

            if similarity >= threshold:
                match_count += 1
                chunk_id = chunk["chunk_id"]
                source_id = chunk["source_id"]

                # Get relationships for this chunk (cached)
                if chunk_id not in relationships_cache:
                    relationships_cache[chunk_id] = get_chunk_relationships(db, chunk_id)

                relationships = relationships_cache.get(chunk_id, [])

                # Find relationships to existing evidence
                matching_rels = find_relationships_to_evidence(
                    accumulated_evidence, relationships, chunk_to_source
                )

                # Check for contradiction
                is_contradiction = any(
                    rel.get("type") == "contradicts" for rel in matching_rels
                )

                # Build evidence object
                evidence = {
                    "chunk_id": chunk_id,
                    "source_id": source_id,
                    "source_title": chunk["title"],
                    "author": chunk["author"],
                    "quote": chunk["quote"],
                    "similarity": round(similarity, 4),
                    "added_at": datetime.now(timezone.utc),
                    "is_contradiction": is_contradiction,
                    "backfill": True,
                }

                # Add ALL matching relationships
                if matching_rels:
                    relationships_found += 1
                    # Store the most significant relationship
                    priority = {"contradicts": 0, "extends": 1, "supports": 2, "applies_to": 3}
                    sorted_rels = sorted(
                        matching_rels,
                        key=lambda r: priority.get(r.get("type", ""), 99)
                    )
                    evidence["relationship"] = sorted_rels[0]
                    if len(matching_rels) > 1:
                        evidence["all_relationships"] = matching_rels

                matches[problem["problem_id"]].append(evidence)

                # Add to accumulated evidence for subsequent relationship matching
                accumulated_evidence.append(evidence)

            # Progress logging
            if comparison_count % 5000 == 0:
                logger.info(
                    f"Progress: {comparison_count:,}/{total_comparisons:,} "
                    f"({match_count} matches, {relationships_found} with relationships)"
                )

    logger.info(f"Found {relationships_found} evidence items with relationships")
    return matches


def write_matches(
    db: firestore.Client,
    matches: Dict[str, List[Dict[str, Any]]],
    problems: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Write matches to Firestore."""
    stats = {"problems_updated": 0, "evidence_added": 0}

    for problem in problems:
        problem_id = problem["problem_id"]
        new_evidence = matches.get(problem_id, [])

        if not new_evidence:
            continue

        # Merge with existing evidence
        existing = problem["existing_evidence"]
        combined = existing + new_evidence

        # Update Firestore
        doc_ref = db.collection("problems").document(problem_id)
        doc_ref.update({
            "evidence": combined,
            "evidence_count": len(combined),
            "updated_at": datetime.now(timezone.utc),
        })

        stats["problems_updated"] += 1
        stats["evidence_added"] += len(new_evidence)

        logger.info(
            f"Updated {problem_id}: +{len(new_evidence)} evidence "
            f"(total: {len(combined)})"
        )

    return stats


def print_summary(
    problems: List[Dict[str, Any]],
    matches: Dict[str, List[Dict[str, Any]]],
    dry_run: bool,
):
    """Print a summary of matches."""
    print("\n" + "=" * 60)
    print("BACKFILL SUMMARY" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)

    total_new = 0
    total_with_relationships = 0

    for problem in problems:
        pid = problem["problem_id"]
        existing = len(problem["existing_evidence"])
        new_matches = matches.get(pid, [])
        new = len(new_matches)
        total_new += new

        # Count relationships
        with_rels = sum(1 for m in new_matches if m.get("relationship"))
        total_with_relationships += with_rels

        status = f"+{new}" if new > 0 else "no new"
        print(f"\n{problem['problem'][:60]}...")
        print(f"  ID: {pid}")
        print(f"  Existing: {existing}, New: {status}")
        if with_rels > 0:
            print(f"  With relationships: {with_rels}")

        # Show top 3 new matches
        if new > 0:
            print("  Top matches:")
            sorted_matches = sorted(
                new_matches, key=lambda x: x["similarity"], reverse=True
            )
            for m in sorted_matches[:3]:
                rel_info = ""
                if m.get("relationship"):
                    rel = m["relationship"]
                    rel_info = f" [{rel['type']} -> {rel.get('target_title', '')[:20]}]"
                print(f"    - {m['source_title'][:35]} (sim={m['similarity']:.3f}){rel_info}")

    print("\n" + "-" * 60)
    print(f"Total problems: {len(problems)}")
    print(f"Total new evidence: {total_new}")
    print(f"Evidence with relationships: {total_with_relationships}")

    if dry_run:
        print("\nRun with --execute to write these matches to Firestore")


def clear_evidence(db: firestore.Client, problems: List[Dict[str, Any]]) -> int:
    """Clear all evidence from problems for re-backfill."""
    cleared = 0
    for problem in problems:
        pid = problem["problem_id"]
        doc_ref = db.collection("problems").document(pid)
        doc_ref.update({
            "evidence": [],
            "evidence_count": 0,
            "contradiction_count": 0,
        })
        cleared += len(problem["existing_evidence"])
        logger.info(f"Cleared {len(problem['existing_evidence'])} evidence from {pid}")
    return cleared


def main():
    parser = argparse.ArgumentParser(
        description="Backfill problem evidence from existing KB chunks"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write matches (default is dry run)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing evidence before backfill (use with --execute)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Similarity threshold (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=os.getenv("GCP_PROJECT", "kx-hub"),
        help="GCP project ID",
    )

    args = parser.parse_args()
    dry_run = not args.execute

    logger.info(f"Starting backfill (dry_run={dry_run}, threshold={args.threshold}, clear={args.clear})")
    logger.info(f"Project: {args.project}")

    # Initialize Firestore
    db = firestore.Client(project=args.project)

    # Load data
    logger.info("Loading active problems...")
    problems = get_active_problems(db)
    logger.info(f"Found {len(problems)} active problems with embeddings")

    if not problems:
        logger.warning("No active problems found. Nothing to do.")
        return

    # Clear existing evidence if requested
    if args.clear and args.execute:
        logger.info("Clearing existing evidence...")
        cleared = clear_evidence(db, problems)
        print(f"Cleared {cleared} existing evidence items")
        # Reload problems with empty evidence
        for p in problems:
            p["existing_evidence"] = []

    logger.info("Loading KB chunks...")
    chunks = get_all_chunks(db)
    logger.info(f"Found {len(chunks)} chunks with embeddings")

    if not chunks:
        logger.warning("No chunks found. Nothing to do.")
        return

    # Find matches (pass db for relationship lookups)
    matches = find_matches(db, problems, chunks, args.threshold)

    # Print summary
    print_summary(problems, matches, dry_run)

    # Write if not dry run
    if not dry_run:
        logger.info("Writing matches to Firestore...")
        stats = write_matches(db, matches, problems)
        print(f"\nWritten: {stats['evidence_added']} evidence to {stats['problems_updated']} problems")
    else:
        print("\n[DRY RUN] No changes made.")
        if args.clear:
            print("Note: --clear only works with --execute")


if __name__ == "__main__":
    main()
