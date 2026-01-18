import os
import sys
import json
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "src" / "mcp_server"))

# Set environment variables
os.environ.setdefault("GCP_PROJECT", "kx-hub")
os.environ.setdefault(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        "/path/to/kx-hub-mcp-key.json",
    ),
)

import firestore_client


def main():
    job_id = "rec-9f4226046adb"
    print(f"Retrieving results for job: {job_id}")

    job = firestore_client.get_async_job(job_id)

    if not job:
        print(f"Error: Job {job_id} not found.")
        return

    print(f"Status: {job.get('status')}")
    print(f"Progress: {job.get('progress')}")

    if job.get("status") == "completed":
        print("\nResults:")
        print(json.dumps(job.get("result"), indent=2))
    elif job.get("status") == "failed":
        print(f"\nError: {job.get('error')}")
    else:
        print("\nJob is still in progress or pending.")


if __name__ == "__main__":
    main()
