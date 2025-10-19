#!/usr/bin/env python3
"""Fetch a sample JSON file from GCS for test fixtures."""

import json
from google.cloud import storage

PROJECT_ID = "kx-hub"
BUCKET_NAME = f"{PROJECT_ID}-raw-json"

def fetch_sample():
    """Fetch first JSON file from bucket."""
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(BUCKET_NAME)

    # Get first blob
    blobs = list(bucket.list_blobs(max_results=1))
    if not blobs:
        print("No files found in bucket")
        return

    blob = blobs[0]
    print(f"Fetching: {blob.name}")

    # Download and pretty-print
    data = json.loads(blob.download_as_text())

    # Save to fixtures
    with open("tests/fixtures/sample-book.json", "w") as f:
        json.dump(data, f, indent=2)

    print(f"✓ Saved to tests/fixtures/sample-book.json")
    print(f"  Title: {data.get('title')}")
    print(f"  Author: {data.get('author')}")
    print(f"  Highlights: {len(data.get('highlights', []))}")

if __name__ == "__main__":
    fetch_sample()
