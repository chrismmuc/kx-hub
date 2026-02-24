# Epic 15: Google Search for Recommendations

**Goal:** Replace Tavily with Google-based web search for recommendation queries to dramatically improve result quality (higher-authority sources, better query understanding).

**Value:** Research comparing the same 6 queries on Tavily vs Google showed Google returns tier-1 sources (McKinsey, Gottman Institute, PubMed, Harvard Business School) while Tavily returns tier-3 blogs and podcast transcripts. The quality gap is not marginal — it's dramatic across all queries tested.

**Dependencies:** Epic 14 (Evidence-Aware Query Generation)

**Status:** Planned

---

## Problem

### Tavily Result Quality

Results from the 2026-02-24 recommendation run (Epic 14 LLM-generated queries):

| Query | Tavily Result | Authority |
|-------|---------------|-----------|
| "Organizational change management frameworks" | remesh.ai (generic overview) | Low |
| "Parental burnout impact marital intimacy" | yourparentingmojo.com (podcast) | Low |
| "Personal brand authenticity expert interviews" | whatdoyouknowtobetrue.com (podcast) | Low |
| "Thought leadership impact measurement" | twenty-one-twelve.com (agency blog) | Low |

### Google Results for the Same Queries

| Query | Google Results | Authority |
|-------|---------------|-----------|
| "Organizational change management frameworks" | Prosci, McKinsey, IDEO U | High |
| "Parental burnout impact marital intimacy" | PubMed (3 peer-reviewed), ScienceDirect | Very High |
| "Personal brand authenticity expert interviews" | Harvard Business School Online | Very High |
| "Thought leadership impact measurement" | ExecViva, LinkedIn frameworks | Medium-High |

---

## API Options & Cost Analysis

### Option A: Google Custom Search JSON API

- **100 free queries/day** (3,000/month)
- $5/1,000 queries after free tier
- Our usage: ~8 queries/week = **$0/month** (well within free tier)
- **Deprecated:** Closed to new customers. Existing customers must migrate by Jan 2027.
- Simple REST API, API key auth

### Option B: Vertex AI Search (Recommended)

- **10,000 free queries/month**
- $1.50/1,000 queries after free tier
- Our usage: ~32 queries/month = **$0/month** (well within free tier)
- Already in GCP ecosystem (same project, same auth)
- Google's official replacement for Custom Search API
- OAuth 2.0 auth (or API key via `searchLite`)
- Supports open web search + site-restricted search

### Option C: Keep Tavily (Current)

- 1,000 free credits/month (basic search = 1 credit)
- $0.008/credit after free tier
- Our usage: ~32 credits/month = **$0/month** (within free tier)
- Lower result quality (proven by research)

### Cost Summary

| Option | Monthly Cost | Annual Cost | Quality |
|--------|-------------|-------------|---------|
| Vertex AI Search | $0 (free tier) | $0 | High |
| Custom Search API | $0 (free tier) | $0 | High (deprecated) |
| Tavily (current) | $0 (free tier) | $0 | Low |

**All options are free at our scale (~32 queries/month).** The decision is purely about quality and longevity.

**Recommendation:** Vertex AI Search — best quality, native GCP integration, long-term supported.

---

## Implementation

### Architecture

```
recommendations() → generate_problem_queries() → search queries
                                                      ↓
                                            google_search_client.search()  [NEW]
                                                      ↓ (fallback on error)
                                            tavily_client.search()         [EXISTING]
```

### Task 1: Create `google_search_client.py`

New file `src/mcp_server/google_search_client.py` with the same interface as `tavily_client.py`:

```python
def search(
    query: str,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    days: int = 30,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    Search the web using Vertex AI Search.

    Returns same structure as tavily_client.search():
    {
        "query": str,
        "results": [{"title", "url", "content", "published_date", "domain", "score"}],
        "response_time": float,
        "result_count": int
    }
    """
```

Key implementation details:
- Use Vertex AI Search API (`discoveryengine` client library)
- Create a search app/data store in Terraform for web search
- Map Vertex AI response format to existing result structure
- Retry logic similar to `tavily_client.py`

### Task 2: Integrate into Recommendation Pipeline

Modify `tools.py` recommendation search loop (~line 1619) to use Google search:

```python
# Try Google search first, fall back to Tavily
try:
    search_result = google_search_client.search(
        query=query_str,
        exclude_domains=excluded_domains,
        include_domains=include_domains,
        days=tavily_days,
        max_results=5,
    )
except Exception as e:
    logger.warning(f"Google search failed, falling back to Tavily: {e}")
    search_result = tavily_client.search(...)
```

Add `search_provider: "google" | "tavily"` to result metadata for observability.

### Task 3: Terraform — Vertex AI Search App

```hcl
resource "google_discovery_engine_search_engine" "recommendations" {
  location     = "global"
  engine_id    = "kx-recommendations"
  display_name = "KX Recommendations Web Search"
  data_store_ids = [google_discovery_engine_data_store.web.data_store_id]
  search_engine_config {
    search_tier = "SEARCH_TIER_STANDARD"
  }
}

resource "google_discovery_engine_data_store" "web" {
  location      = "global"
  data_store_id = "kx-web-search"
  display_name  = "Web Search"
  content_config = "PUBLIC_WEBSITE"
  industry_vertical = "GENERIC"
}
```

### Task 4: Tests

- Unit tests for `google_search_client.py` (mock Vertex AI responses)
- Integration: verify fallback to Tavily on Google error
- Verify result format matches existing pipeline expectations

---

## Non-Goals

- No removal of Tavily (kept as fallback)
- No changes to ranking/scoring logic (same pipeline, better input)
- No changes to query generation (Epic 14 handles that)

## Success Criteria

- Google search results have higher average authority scores than Tavily
- Fallback to Tavily works seamlessly on Google API errors
- Zero additional cost (free tier sufficient)
- `search_provider` logged for all recommendation runs

---

## Sources

- [Google Custom Search API Pricing](https://developers.google.com/custom-search/v1/overview)
- [Vertex AI Search Pricing](https://cloud.google.com/generative-ai-app-builder/pricing)
- [Tavily API Credits & Pricing](https://docs.tavily.com/documentation/api-credits)
- [Custom Search API Deprecation / Vertex AI Migration](https://support.google.com/programmable-search/thread/307464533)
