# Epic 12: Automated Weekly Recommendations to Readwise

**Goal:** Batch weekly recommendations execution (Friday morning) with automatic Readwise Reader inbox integration, strict result filtering, and AI-source tagging.

**Status:** In Progress

**Last Updated:** 2026-01-20

---

## Overview

This epic implements automated weekly batch recommendations that execute every Friday at 04:00 UTC, filter strictly to 3 results with high recency, and automatically save to Readwise Reader inbox with AI-sourced tagging.

### Key Design Principle: Maximum Code Reuse

The batch function is a **consumer of the existing MCP Server API**, not a duplicate. All recommendation logic (query generation, Tavily, filtering) stays in MCP Server. The batch function only adds:
- Scheduling via Cloud Scheduler
- Reader API integration
- Deduplication checking
- Job tracking

---

## Architecture

```
Cloud Scheduler (Fri 04:00 UTC)
  ↓
Pub/Sub Topic: batch-recommendations
  ↓
Cloud Function: batch-recommendations
  ├─ 1. Load config from Firestore (config/batch_recommendations)
  ├─ 2. Call MCP Server API: POST /tools/recommendations (start async job)
  ├─ 3. Poll job status until completed
  ├─ 4. Filter results: max 3, recency < 7 days
  ├─ 5. Dedup: Query Reader /api/v3/list/ for existing URLs
  ├─ 6. Save to Reader: POST /api/v3/save/ with auto-tags
  ├─ 7. Track execution: Store in Firestore batch_jobs
  └─ 8. Notify Slack (optional, on failure)
```

---

## Implementation Details

### Story 12.1: Cloud Scheduler Setup ✅

**File:** `terraform/cloud_scheduler.tf`

Creates:
- **Cloud Scheduler job** - Weekly execution Friday 04:00 UTC with 9min timeout (max for event-triggered functions)
- **Pub/Sub topic** - `batch-recommendations` for trigger events
- **Service account** - `batch-recommendations-sa` with Firestore, Secret Manager, and Cloud Run permissions

**Firestore Configuration** (create manually or via Cloud Console):

```
Collection: config
Document: batch_recommendations

{
  "enabled": true,
  "mode": "balanced",
  "max_results": 3,
  "recency_days": 7,
  "auto_tags": ["ai-recommended"],
  "tavily_days": 30,
  "mcp_server_url": "https://mcp-server-xyz-ew.a.run.app",
  "notification_slack_enabled": false
}
```

### Story 12.2: Batch Recommendations Function ✅

**File:** `src/batch_recommendations/main.py`

Entry point: `batch_recommendations(event, context)` - Pub/Sub trigger

Key execution flow:
1. Load config from Firestore (defaults if missing)
2. Call MCP Server `/tools/recommendations` to start async job
3. Poll until completed (max 300s)
4. Filter results: max 3, published within last 7 days
5. Dedup against Reader library
6. Save each to Reader with tags
7. Store report with metrics
8. On error: Store failure report and re-raise

### Story 12.3: Readwise Reader Integration ✅

**File:** `src/batch_recommendations/reader_client.py`

Implements `ReadwiseReaderClient` class with:
- `save_url(url, tags, title)` - POST `/api/v3/save/`
- `list_documents(limit)` - GET `/api/v3/list/` with pagination

Handles rate limiting (429) with exponential backoff.

### Story 12.4: Auto-Tagging ✅

Tags per article:
1. Auto-tags from config (default: `["ai-recommended"]`)
2. Domain (e.g., `"techcrunch.com"`)
3. Topic tags (first 2 only)

Result: 2-4 deduplicated tags per article

### Story 12.5: Deduplication Check ✅

Before saving to Reader:
1. Fetch all documents from Reader library
2. Normalize URLs (lowercase, remove trailing slash)
3. Skip URLs already present
4. Fail gracefully if Reader API unavailable

### Story 12.6: Batch Job Tracking ✅

Store execution report in Firestore `batch_jobs` collection:
```json
{
  "timestamp": "2026-01-19T22:05:30Z",
  "status": "success",
  "metrics": {
    "original_count": 15,
    "filtered_count": 5,
    "deduplicated_count": 3,
    "saved_count": 3
  },
  "saved_items": [
    {
      "url": "https://...",
      "title": "...",
      "tags": ["ai-recommended", "..."],
      "reader_id": "..."
    }
  ],
  "execution_time_seconds": 42.5,
  "error": null
}
```

### Story 12.7: Error Handling & Alerts ✅

- Retry logic: Exponential backoff for Reader API (max 3 retries)
- Dedup check: Fails gracefully if Reader unavailable
- Job tracking: Failure reports stored for monitoring
- Logging: Detailed logs at each step
- TODO: Slack notifications on failure (can be added in future)

---

## Testing

### Unit Tests ✅

File: `tests/batch_recommendations/test_batch.py`

Coverage:
- Date parsing and recency filtering
- Tag deduplication and limiting
- Full pipeline scenarios

Run: `python3 -m pytest tests/batch_recommendations/test_batch.py -v`

### Integration Testing (Manual)

Prerequisites:
1. Deploy: `cd terraform && terraform apply`
2. Create Firestore config document
3. Add API key: `echo "key" | gcloud secrets create readwise-api-key --data-file=-`

Steps:
1. Trigger manually: `gcloud scheduler jobs run batch-recommendations --location=europe-west3`
2. Monitor logs: `gcloud functions logs read batch-recommendations --region=europe-west4 --limit=50`
3. Verify: Check `batch_jobs` collection and Readwise Reader inbox

---

## Files

### Created
- `terraform/cloud_scheduler.tf` - Cloud Scheduler, Pub/Sub, Cloud Function, Service Account
- `src/batch_recommendations/main.py` - Batch function entry point
- `src/batch_recommendations/reader_client.py` - Reader API client
- `src/batch_recommendations/requirements.txt` - Dependencies
- `tests/batch_recommendations/test_batch.py` - Unit tests
- `docs/epics/epic12.md` - This file

### Modified
- `docs/epics.md` - Status updated to "In Progress"

---

## Cost Estimate

- Cloud Scheduler: ~$0 (free tier)
- Cloud Function: ~$0.40/month (52 × 2-5 min)
- Readwise: Included in paid plan
- **Total: ~$0.45/month**

---

## Success Criteria

- 100% scheduled execution (no missed runs)
- 0% duplicates in Reader
- <5 min execution time
- 1-3 articles saved per week
- 100% automatic tagging rate
