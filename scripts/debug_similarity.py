#!/usr/bin/env python3
"""
Debug script to check similarity scores between a problem and specific chunks.
"""

import os
import sys

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

    # Get the "Kontinuierliches Lernen" problem
    problem_id = "prob_0e2bc4369b33"
    problem_doc = db.collection("problems").document(problem_id).get()

    if not problem_doc.exists:
        print(f"Problem {problem_id} not found!")
        return

    problem_data = problem_doc.to_dict()
    problem_embedding = problem_data.get("embedding", [])

    if hasattr(problem_embedding, "to_map_value"):
        problem_embedding = list(problem_embedding)

    print(f"Problem: {problem_data.get('problem', '')[:80]}...")
    print(f"Embedding dimensions: {len(problem_embedding)}")
    print()

    # Search for chunks from "Building a Second Brain" and "PARA Method"
    target_sources = ["Building a Second Brain", "The PARA Method"]

    print("Checking similarity scores for relevant chunks:")
    print("=" * 70)

    for doc in db.collection("kb_items").stream():
        data = doc.to_dict()
        title = data.get("title", "")

        # Check if this is from a target source
        if any(src in title for src in target_sources):
            chunk_embedding = data.get("embedding", [])

            if hasattr(chunk_embedding, "to_map_value"):
                chunk_embedding = list(chunk_embedding)

            if chunk_embedding:
                similarity = cosine_similarity(problem_embedding, chunk_embedding)

                content = data.get("content", "")[:100].replace("\n", " ")
                print(f"\nTitle: {title}")
                print(f"Chunk ID: {doc.id}")
                print(f"Similarity: {similarity:.4f} {'✓ ABOVE 0.7' if similarity >= 0.7 else '✗ BELOW 0.7'}")
                print(f"Content: {content}...")

    print("\n" + "=" * 70)
    print("Threshold is 0.7 - only scores >= 0.7 get matched as evidence")

if __name__ == "__main__":
    main()
