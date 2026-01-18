#!/usr/bin/env python3
"""
Analyze similarity distribution across all problems to find optimal threshold.
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from google.cloud import firestore

def cosine_similarity(vec1, vec2):
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)

def main():
    db = firestore.Client(project="kx-hub")

    # Get all active problems
    problems = []
    for doc in db.collection("problems").where("status", "==", "active").stream():
        data = doc.to_dict()
        embedding = data.get("embedding", [])
        if hasattr(embedding, "to_map_value"):
            embedding = list(embedding)
        if embedding:
            problems.append({
                "id": doc.id,
                "problem": data.get("problem", "")[:50],
                "embedding": embedding,
            })

    print(f"Found {len(problems)} active problems with embeddings")

    # Get all chunks (limit to 100 for speed)
    chunks = []
    count = 0
    for doc in db.collection("kb_items").stream():
        data = doc.to_dict()
        embedding = data.get("embedding", [])
        if hasattr(embedding, "to_map_value"):
            embedding = list(embedding)
        if embedding:
            chunks.append({
                "id": doc.id,
                "embedding": embedding,
            })
        count += 1

    print(f"Found {len(chunks)} chunks with embeddings")

    # Calculate similarity distribution
    thresholds = [0.60, 0.65, 0.70, 0.75]
    results = defaultdict(lambda: defaultdict(int))

    print("\nCalculating similarities (this may take a minute)...")

    for problem in problems:
        for chunk in chunks:
            sim = cosine_similarity(problem["embedding"], chunk["embedding"])
            for threshold in thresholds:
                if sim >= threshold:
                    results[problem["id"]][threshold] += 1

    print("\n" + "=" * 80)
    print("EVIDENCE COUNTS BY THRESHOLD")
    print("=" * 80)
    print(f"{'Problem':<55} | " + " | ".join(f"≥{t}" for t in thresholds))
    print("-" * 80)

    for problem in problems:
        pid = problem["id"]
        name = problem["problem"]
        counts = [results[pid][t] for t in thresholds]
        print(f"{name:<55} | " + " | ".join(f"{c:>4}" for c in counts))

    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)

    total_at_07 = sum(results[p["id"]][0.70] for p in problems)
    total_at_065 = sum(results[p["id"]][0.65] for p in problems)
    total_at_06 = sum(results[p["id"]][0.60] for p in problems)

    print(f"Total evidence at 0.70: {total_at_07}")
    print(f"Total evidence at 0.65: {total_at_065} (+{total_at_065 - total_at_07})")
    print(f"Total evidence at 0.60: {total_at_06} (+{total_at_06 - total_at_07})")

    if total_at_065 > total_at_07 * 1.5:
        print("\n→ Consider lowering threshold to 0.65 for better coverage")

if __name__ == "__main__":
    main()
