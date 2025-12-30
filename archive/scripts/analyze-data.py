#!/usr/bin/env python3
"""
Quick analysis of ingested Readwise data

Shows statistics about your imported books and highlights.
"""

import json
from collections import Counter
from google.cloud import storage

PROJECT_ID = "kx-hub"
BUCKET_NAME = f"{PROJECT_ID}-raw-json"

def analyze_bucket():
    """Analyze the ingested Readwise data."""
    print("=" * 60)
    print("Readwise Data Analysis")
    print("=" * 60)
    print()

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blobs = list(bucket.list_blobs())

    print(f"Total files: {len(blobs)}")
    print()

    # Sample analysis on first 100 books
    sample_size = min(100, len(blobs))
    print(f"Analyzing sample of {sample_size} books...")
    print()

    total_highlights = 0
    sources = Counter()
    categories = Counter()
    books_with_highlights = 0

    for i, blob in enumerate(blobs[:sample_size]):
        try:
            data = json.loads(blob.download_as_text())

            # Count highlights
            highlights = data.get('highlights', [])
            num_highlights = len(highlights)
            total_highlights += num_highlights

            if num_highlights > 0:
                books_with_highlights += 1

            # Track source
            source = data.get('source', 'unknown')
            sources[source] += 1

            # Track category
            category = data.get('category', 'unknown')
            categories[category] += 1

        except Exception as e:
            print(f"Error processing {blob.name}: {e}")

    # Print statistics
    print("Statistics:")
    print("-" * 60)
    print(f"Books analyzed: {sample_size}")
    print(f"Books with highlights: {books_with_highlights}")
    print(f"Total highlights: {total_highlights}")
    print(f"Average highlights per book: {total_highlights / sample_size:.1f}")
    print()

    print("Sources:")
    print("-" * 60)
    for source, count in sources.most_common():
        print(f"  {source}: {count}")
    print()

    print("Categories:")
    print("-" * 60)
    for category, count in categories.most_common():
        print(f"  {category}: {count}")
    print()

    # Show sample book
    print("Sample Book:")
    print("-" * 60)
    first_blob = blobs[0]
    sample_data = json.loads(first_blob.download_as_text())
    print(f"Title: {sample_data.get('title', 'N/A')}")
    print(f"Author: {sample_data.get('author', 'N/A')}")
    print(f"Source: {sample_data.get('source', 'N/A')}")
    print(f"Highlights: {len(sample_data.get('highlights', []))}")
    if sample_data.get('highlights'):
        print(f"First highlight: {sample_data['highlights'][0].get('text', '')[:100]}...")
    print()

    print("=" * 60)
    print("Analysis Complete!")
    print("=" * 60)

if __name__ == "__main__":
    analyze_bucket()
