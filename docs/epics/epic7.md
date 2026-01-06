# Epic 7: Async MCP Interface

**Goal:** Replace long-running synchronous MCP tools with an async job pattern to prevent client timeouts and improve UX.

**Business Value:** 
- Eliminates client-side timeouts (current: ~90s limit)
- Enables parallel job execution
- Provides visibility into job progress
- Adds historical view of past recommendations

**Dependencies:** Epic 3 (Recommendations)

**Status:** Complete (Story 7.1 - Cloud Tasks, Story 7.2 - Simplified Interface)

---

## Problem Statement

Long-running MCP tools like `get_reading_recommendations` (60-120s) cause client timeouts:

```
13:05:38 - AI request starts (17 domains)
13:05:38 - Tech request starts (25 domains)  
13:05:38 - Tech completes after 85s ✅
13:07:37 - notifications/cancelled - AI aborted by client
13:07:37 - AI completes after 118.9s (too late, result lost)
```

**Root Cause:** Claude Code cancels requests after ~90s. Server-side work completes but result never reaches client.

---

## Architecture

### Async Job Pattern

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │     │  MCP Server │     │ Cloud Tasks │     │  Firestore  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │                   │
       │ recommendations() │                   │                   │
       │──────────────────▶│                   │                   │
       │                   │ create job doc    │                   │
       │                   │─────────────────────────────────────▶│
       │                   │ enqueue task      │                   │
       │                   │──────────────────▶│                   │
       │ {job_id, poll_s}  │                   │                   │
       │◀──────────────────│                   │                   │
       │                   │                   │                   │
       │                   │   [Cloud Tasks calls /jobs/run]       │
       │                   │◀──────────────────│                   │
       │                   │ execute job       │                   │
       │                   │─────────────────────────────────────▶│
       │                   │                   │                   │
       │ recommendations   │                   │                   │
       │ (job_id=...)      │                   │                   │
       │──────────────────▶│                   │                   │
       │                   │ read job status   │                   │
       │                   │─────────────────────────────────────▶│
       │ {status, progress}│                   │                   │
       │◀──────────────────│                   │                   │
       │                   │                   │                   │
       │    [poll again after poll_s]          │                   │
       │                   │                   │                   │
       │ recommendations   │                   │                   │
       │ (job_id=...)      │                   │                   │
       │──────────────────▶│                   │                   │
       │ {status: complete,│                   │                   │
       │  recommendations} │                   │                   │
       │◀──────────────────│                   │                   │
```

### Data Model

```
Firestore: async_jobs/{job_id}
├── job_id: string
├── job_type: "recommendations" | "article_ideas" | ...
├── status: "pending" | "running" | "completed" | "failed"
├── progress: float (0.0 - 1.0)
├── created_at: timestamp
├── updated_at: timestamp
├── completed_at: timestamp | null
├── expires_at: timestamp (TTL for cleanup, 14 days)
├── params: {mode, hot_sites, limit, ...}
├── result: {...} | null
├── error: string | null
└── user_id: string
```

---

## Story 7.1: Async Recommendations

**Goal:** Convert `get_reading_recommendations` to async pattern with only 2 compact tools.

### MCP Tools

#### `recommendations`

Unified tool for starting and polling recommendation jobs.

**Story 7.2 Update:** Simplified interface - settings come from `config/recommendations` in Firestore.

**Start a new job** (no `job_id`):

```python
# Simple call - uses config defaults
recommendations() -> {
    "job_id": "rec-abc123def456",
    "status": "pending",
    "poll_after_seconds": 10,
    "config_used": {
        "hot_sites": "tech",
        "limit": 10,
        "tavily_days": 30,
        "topic": null
    }
}

# With topic override
recommendations(topic="kubernetes security") -> {
    "job_id": "rec-abc123def456",
    "config_used": {"topic": "kubernetes security", ...}
}
```

**Poll for status/result** (with `job_id`):

```python
recommendations(job_id: str) -> {
    "job_id": "rec-abc123def456",
    "status": "running",  # pending | running | completed | failed
    "progress": 0.6,      # 60% complete
    "poll_after_seconds": 5,
    
    # When completed:
    "result": {
        "recommendations": [...],
        "processing_time_seconds": 80,
        ...
    },
    
    # When failed:
    "error": "Tavily API rate limit exceeded"
}
```

**Config document** (`config/recommendations` in Firestore):

```json
{
  "hot_sites": "tech",
  "tavily_days": 30,
  "limit": 10,
  "topics": ["AI agents", "platform engineering", "developer productivity"]
}
```

#### `recommendations_history`

Simple list of all recommendations from the last 14 days.

```python
recommendations_history(
    days: int = 14
) -> {
    "days": 14,
    "total_count": 23,
    "recommendations": [
        {
            "title": "Measuring Developer Productivity",
            "url": "https://newsletter.pragmaticengineer.com/p/...",
            "domain": "newsletter.pragmaticengineer.com",
            "recommended_at": "2026-01-06T13:01:20Z",
            "params": {
                "mode": "surprise_me",
                "hot_sites": "tech"
            },
            "why_recommended": "Connects to your reading: 4 North Star Metrics..."
        },
        {
            "title": "Agentic AI: The Business Realities",
            "url": "https://www.thoughtworks.com/...",
            "domain": "thoughtworks.com",
            "recommended_at": "2026-01-05T10:30:00Z",
            "params": {
                "mode": "balanced",
                "hot_sites": "ai"
            },
            "why_recommended": "Related to your recent reading on: ai"
        },
        ...
    ]
}
```

### Example Flow

```python
# 1. Start job (simple - uses config defaults)
recommendations()
# → {job_id: "rec-123", status: "pending", config_used: {hot_sites: "tech", ...}}

# Or with topic override:
recommendations(topic="kubernetes")
# → {job_id: "rec-456", config_used: {topic: "kubernetes", ...}}

# 2. Poll (after 10s)
recommendations(job_id="rec-123")
# → {status: "running", progress: 0.4, poll_after_seconds: 5}

# 3. Poll again (after 5s)
recommendations(job_id="rec-123")
# → {status: "completed", result: {recommendations: [...]}}

# 4. Later: view all past recommendations
recommendations_history()
# → {total_count: 23, recommendations: [{title, url, recommended_at, ...}, ...]}
```

### Tasks

1. [x] Create `async_jobs` Firestore collection with TTL (14 days)
2. [x] Implement job creation and status tracking
3. [x] ~~Implement background job execution (in-process threading)~~ → Replaced with Cloud Tasks
4. [x] Implement Cloud Tasks queue for async job execution
5. [x] Add `/jobs/run` endpoint for Cloud Tasks invocation
6. [x] Implement `recommendations` MCP tool (start + poll)
7. [x] Implement `recommendations_history` MCP tool (flat list)
8. [x] Remove `get_reading_recommendations` (replaced by `recommendations`)
9. [ ] Add progress reporting during Tavily searches
10. [ ] Add job cleanup for expired jobs (TTL-based)

### Success Metrics

- Zero client timeouts for recommendation requests
- Job status visible within 1s of starting
- Progress updates every 10s during execution
- Historical recommendations queryable for 14 days

---

## Story 7.2: Simplified Recommendations Interface ✅

**Goal:** Simplify the `recommendations` tool to require no parameters for typical use.

**Problem:** The original interface had too many parameters (mode, hot_sites, days, limit, include_seen) making it hard to call correctly.

**Solution:** 
- Settings stored in Firestore `config/recommendations`
- Only 2 parameters: `job_id` (for polling) and `topic` (optional override)
- Always uses "fresh" mode for recency-focused results

### Changes

| Before | After |
|--------|-------|
| `recommendations(mode="fresh", hot_sites="ai", days=7, limit=5)` | `recommendations()` |
| 6 parameters | 2 parameters (job_id, topic) |
| LLM had to guess params | Defaults from Firestore config |

### Tasks

1. [x] Add `get_recommendations_defaults()` to firestore_client.py
2. [x] Add `config/recommendations` Firestore document with defaults
3. [x] Remove mode, hot_sites, days, limit, include_seen from `recommendations()`
4. [x] Add optional `topic` parameter for one-time override
5. [x] Update `_get_reading_recommendations()` to accept tavily_days and topic
6. [x] Update server.py tool definition
7. [x] Update tests

---

## Story 7.3: Async Article Ideas (Optional)

**Goal:** Apply same pattern to `suggest_article_ideas` if needed.

Depends on Story 6.1 performance. If article idea generation is fast (<30s), may not need async treatment.

### Tasks

1. [ ] Evaluate article idea generation performance
2. [ ] If needed, implement async pattern
3. [ ] Reuse job infrastructure from Story 7.1

---

## Implementation Notes

### Background Execution: Cloud Tasks

Jobs are executed via Cloud Tasks for reliability:

```
terraform/async_jobs.tf    → Cloud Tasks queue "async-jobs"
src/mcp_server/tools.py    → _enqueue_cloud_task() enqueues job
src/mcp_server/server.py   → /jobs/run endpoint executes job
```

**Why Cloud Tasks instead of in-process threading:**
- Cloud Run instances can shut down anytime (timeout, scaling)
- In-process threads die with the instance
- Cloud Tasks guarantees job delivery and automatic retries

**Configuration (cloudbuild.yaml):**
- `CLOUD_TASKS_QUEUE=async-jobs`
- `CLOUD_TASKS_SA_EMAIL=cloud-tasks-invoker@$PROJECT_ID.iam.gserviceaccount.com`
- `MCP_SERVER_URL` (for /jobs/run callback)

### Job TTL Strategy

| Job Status | TTL |
|------------|-----|
| pending/running | 1 hour (auto-fail if stuck) |
| completed | 14 days |
| failed | 24 hours |

### Backwards Compatibility

`get_reading_recommendations` has been removed:
- Replaced by `recommendations()` (async with polling)
- Internal function `_get_reading_recommendations()` still exists for job execution

---

## Summary

| Story | Description | Status |
|-------|-------------|--------|
| 7.1 | Async Recommendations via Cloud Tasks | ✅ Done |
| 7.2 | Simplified Interface (config-based defaults) | ✅ Done |
| 7.3 | Async Article Ideas | Optional |

**Design Principle:** 
- `recommendations()`: No params needed, uses Firestore config
- `recommendations(topic="...")`: One-time topic override
- `recommendations(job_id="...")`: Poll for results
- `recommendations_history()`: Flat list of past recommendations
