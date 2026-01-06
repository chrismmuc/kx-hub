# Epic 7: Async MCP Interface

**Goal:** Replace long-running synchronous MCP tools with an async job pattern to prevent client timeouts and improve UX.

**Business Value:** 
- Eliminates client-side timeouts (current: ~90s limit)
- Enables parallel job execution
- Provides visibility into job progress
- Adds historical view of past recommendations

**Dependencies:** Epic 3 (Recommendations)

**Status:** Complete (Story 7.1)

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
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │     │  MCP Server │     │  Firestore  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ recommendations() │                   │
       │──────────────────▶│                   │
       │                   │ create job doc    │
       │                   │──────────────────▶│
       │ {job_id, poll_s}  │                   │
       │◀──────────────────│                   │
       │                   │                   │
       │    [async work starts in background]  │
       │                   │                   │
       │ recommendations   │                   │
       │ (job_id=...)      │                   │
       │──────────────────▶│                   │
       │                   │ read job status   │
       │                   │──────────────────▶│
       │ {status, progress}│                   │
       │◀──────────────────│                   │
       │                   │                   │
       │    [poll again after poll_s]          │
       │                   │                   │
       │ recommendations   │                   │
       │ (job_id=...)      │                   │
       │──────────────────▶│                   │
       │ {status: complete,│                   │
       │  recommendations} │                   │
       │◀──────────────────│                   │
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

**Start a new job** (no `job_id`):

```python
recommendations(
    days: int = 14,
    limit: int = 10,
    hot_sites: str = None,  # "tech" | "ai" | "devops" | "business" | "all"
    mode: str = "balanced", # "balanced" | "fresh" | "deep" | "surprise_me"
    include_seen: bool = False
) -> {
    "job_id": "rec-abc123def456",
    "status": "pending",
    "poll_after_seconds": 10,
    "estimated_duration_seconds": 60,
    "created_at": "2026-01-06T13:00:00Z"
}
```

**Poll for status/result** (with `job_id`):

```python
recommendations(
    job_id: str
) -> {
    "job_id": "rec-abc123def456",
    "status": "running",  # pending | running | completed | failed
    "progress": 0.6,      # 60% complete
    "poll_after_seconds": 5,
    "created_at": "2026-01-06T13:00:00Z",
    "updated_at": "2026-01-06T13:00:45Z",
    
    # When completed:
    "completed_at": "2026-01-06T13:01:20Z",
    "result": {
        "recommendations": [...],
        "processing_time_seconds": 80,
        "queries_used": [...],
        ...
    },
    
    # When failed:
    "error": "Tavily API rate limit exceeded"
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
# 1. Start job
recommendations(hot_sites="ai", mode="surprise_me")
# → {job_id: "rec-123", status: "pending", poll_after_seconds: 10}

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
3. [x] Implement background job execution (in-process threading)
4. [ ] Add progress reporting during Tavily searches
5. [x] Implement `recommendations` MCP tool (start + poll)
6. [x] Implement `recommendations_history` MCP tool (flat list)
7. [ ] Add job cleanup for expired jobs (TTL-based)
8. [x] Update documentation
9. [ ] Deprecate `get_reading_recommendations` (keep as alias initially)

### Success Metrics

- Zero client timeouts for recommendation requests
- Job status visible within 1s of starting
- Progress updates every 10s during execution
- Historical recommendations queryable for 14 days

---

## Story 7.2: Async Article Ideas (Optional)

**Goal:** Apply same pattern to `suggest_article_ideas` if needed.

Depends on Story 6.1 performance. If article idea generation is fast (<30s), may not need async treatment.

### Tools (if needed)

| Tool | Verhalten |
|------|-----------|
| `article_ideas(...)` | Start (ohne job_id) / Poll (mit job_id) |
| `article_ideas_history(days=14)` | Flache Liste aller Ideen |

### Tasks

1. [ ] Evaluate article idea generation performance
2. [ ] If needed, implement async pattern
3. [ ] Reuse job infrastructure from Story 7.1

---

## Implementation Notes

### Background Execution Options

1. **In-Process Threading** (Simple) ← Start here
   - Start background thread for job execution
   - Works for Cloud Run (long-running instances)
   - Risk: Instance shutdown kills running jobs

2. **Cloud Tasks** (Robust)
   - Queue job to Cloud Tasks
   - Separate endpoint handles execution
   - Survives instance restarts
   - Migrate if reliability issues arise

### Job TTL Strategy

| Job Status | TTL |
|------------|-----|
| pending/running | 1 hour (auto-fail if stuck) |
| completed | 14 days |
| failed | 24 hours |

### Backwards Compatibility

Keep `get_reading_recommendations` as deprecated alias:
- Internally calls `recommendations()` and polls until complete
- Log deprecation warning

---

## Summary

| Story | Tools | Priority |
|-------|-------|----------|
| 7.1 | `recommendations`, `recommendations_history` | High |
| 7.2 | `article_ideas`, `article_ideas_history` | Low |

**Design Principle:** 
- `recommendations`: `job_id` determines Start vs Poll
- `recommendations_history`: Simple flat list, no job details

**Estimated Effort:** 2-3 days for Story 7.1
