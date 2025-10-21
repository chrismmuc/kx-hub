# Initial Historical Data Import

This script performs a one-time import of **ALL** your historical Readwise books and highlights.

## What It Does

- ✅ Fetches complete historical data (no time filter)
- ✅ Handles pagination automatically
- ✅ Includes rate limiting and retry logic
- ✅ Uploads to `gs://kx-hub-raw-json/` (same bucket as Cloud Function)
- ✅ Checkpoint/resume capability (can safely restart if interrupted)
- ✅ Progress tracking with detailed logs

## Prerequisites

1. **Python 3.7+** installed
2. **gcloud authenticated** (you already did this for Terraform)
3. **Google Cloud Storage library**

## Installation

### Step 1: Install Python Dependencies

```bash
pip3 install -r requirements-import.txt
```

This installs:
- `google-cloud-storage` - For uploading to GCS
- `requests` - For calling Readwise API

### Step 2: Verify Authentication

Make sure you're authenticated with Google Cloud:

```bash
gcloud auth application-default login
```

(You may have already done this for Terraform)

## Running the Import

### Basic Usage

```bash
python3 initial-import.py
```

That's it! The script will:
1. Fetch all your Readwise books (all time, no date filter)
2. Upload each book to `gs://kx-hub-raw-json/readwise-book-{id}.json`
3. Show progress in real-time
4. Save checkpoints every 10 books

### Expected Output

```
============================================================
Readwise Initial Import - Full Historical Load
============================================================
Project: kx-hub
Bucket: kx-hub-raw-json

Starting Readwise data fetch...
Fetching ALL historical data (no time filter)
Fetching page 1...
Page 1: Received 100 books
✓ Uploaded: readwise-book-12345.json
✓ Uploaded: readwise-book-12346.json
...
Progress: 100 fetched, 100 uploaded, 0 skipped

Fetching page 2...
Page 2: Received 100 books
✓ Uploaded: readwise-book-12347.json
...

============================================================
Import Complete!
============================================================
Total books fetched: 543
Total books uploaded: 543
Total books skipped (already existed): 0

Data uploaded to: gs://kx-hub-raw-json/
```

## Features

### 1. Checkpoint/Resume
If the script is interrupted (Ctrl+C, network failure, etc.):
- Progress is saved to `.import-checkpoint.json`
- Simply run the script again to resume
- Already-uploaded books will be skipped

### 2. Rate Limiting
- 2 second delay between API requests
- Handles HTTP 429 (rate limit) responses
- Exponential backoff on errors
- Up to 5 retry attempts per request

### 3. Error Handling
- Network timeouts (60s per request)
- Malformed API responses
- GCS upload failures
- Validates book structure before upload

## Troubleshooting

### "Permission Denied" on GCS Upload
```bash
# Re-authenticate
gcloud auth application-default login
```

### "Module not found: google.cloud"
```bash
# Install dependencies
pip3 install -r requirements-import.txt
```

### Script Interrupted
```bash
# Just run it again - it will resume from checkpoint
python3 initial-import.py
```

### Want to Start Fresh
```bash
# Remove checkpoint file and re-run
rm .import-checkpoint.json
python3 initial-import.py
```

## Performance

- **Speed**: ~2 seconds per API request (rate limiting)
- **100 books**: ~3-4 minutes
- **1,000 books**: ~30-40 minutes
- **5,000 books**: ~3 hours

The script can safely run for hours. If interrupted, it will resume from the last checkpoint.

## After Import Completes

### Verify Data Was Uploaded

```bash
# Count files in bucket
gcloud storage ls gs://kx-hub-raw-json/ | wc -l

# View a sample file
gcloud storage cat gs://kx-hub-raw-json/readwise-book-12345.json | head -50
```

### Check Storage Usage

```bash
# See bucket size
gcloud storage du -sh gs://kx-hub-raw-json/
```

## Files Created

- `.import-checkpoint.json` - Progress tracking (deleted on completion)
- Logs to console (can redirect to file: `python3 initial-import.py > import.log 2>&1`)

## Security Note

⚠️ **The script contains your Readwise API key hardcoded.**

The script file (`initial-import.py`) is in `.gitignore` and will NOT be committed to git.

After the import is complete, you can delete the script or move it outside the git repo.

## Next Steps

After the initial import completes:

1. **Verify the data** in GCS bucket
2. **The daily Cloud Function** will handle incremental updates going forward
3. **Delete the import script** if you want (it's a one-time use)

## Summary

```bash
# One-time setup
pip3 install -r requirements-import.txt

# Run the import
python3 initial-import.py

# Verify it worked
gcloud storage ls gs://kx-hub-raw-json/ | wc -l
```

That's it! The script handles everything else automatically.
