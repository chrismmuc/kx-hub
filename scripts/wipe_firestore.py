#!/usr/bin/env python3
"""
Firestore collection wipe script for chunking migration.
Deletes all documents in kb_items and pipeline_items collections.
"""

from google.cloud import firestore
import sys

def delete_collection(db, collection_name, batch_size=10):
    """Delete all documents in a collection in batches."""
    coll_ref = db.collection(collection_name)
    deleted = 0

    while True:
        # Get a batch of documents
        docs = list(coll_ref.limit(batch_size).stream())

        if not docs:
            break

        # Delete documents one by one to avoid transaction size limits
        for doc in docs:
            doc.reference.delete()
            deleted += 1
            if deleted % 10 == 0:
                print(f"Deleted {deleted} documents from {collection_name}...")

    return deleted

def main():
    project_id = 'kx-hub'

    print(f"Connecting to Firestore in project: {project_id}")
    db = firestore.Client(project=project_id)

    # Confirm with user
    print("\nWARNING: This will delete ALL documents in:")
    print("  - kb_items collection")
    print("  - pipeline_items collection")
    response = input("\nType 'YES' to confirm: ")

    if response != 'YES':
        print("Aborted. No changes made.")
        sys.exit(0)

    print("\nDeleting kb_items collection...")
    kb_deleted = delete_collection(db, 'kb_items')
    print(f"✓ Deleted {kb_deleted} documents from kb_items")

    print("\nDeleting pipeline_items collection...")
    pipeline_deleted = delete_collection(db, 'pipeline_items')
    print(f"✓ Deleted {pipeline_deleted} documents from pipeline_items")

    print(f"\n✓ Total deleted: {kb_deleted + pipeline_deleted} documents")
    print("Data wipe complete!")

if __name__ == '__main__':
    main()
