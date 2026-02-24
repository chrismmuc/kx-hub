# Epic 15: Google Search for Recommendations

**Goal:** Replace Tavily with Google Custom Search for recommendation queries to dramatically improve result quality (higher-authority sources, better query understanding).

**Value:** Research comparing the same 6 queries on Tavily vs Google showed Google returns tier-1 sources (McKinsey, Gottman Institute, PubMed, Harvard Business School) while Tavily returns tier-3 blogs and podcast transcripts. The quality gap is dramatic across all queries tested.

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

## API Options Evaluated

### Vertex AI Search (Discovery Engine) — NOT suitable

Vertex AI Search is a **site-restricted** search product. You must pre-define domains to index. It does NOT support open web search. Not usable for our recommendation discovery use case.

### Grounding with Google Search (via Gemini) — Poor fit

Requires an LLM call for every search ($35/1K queries). No domain or date filtering. Returns LLM-synthesized answers, not raw search results. Would require restructuring the entire pipeline.

### Google Custom Search JSON API — Recommended

- **Open web search** with Google quality
- **100 free queries/day** (~3,000/month) — our usage: ~8/week
- $5/1,000 queries after free tier
- **Domain filtering** via `siteSearch` / `siteSearchFilter` params
- **Date filtering** via `dateRestrict` param (e.g., `d30` for last 30 days)
- Raw results: title, link, snippet, page metadata
- Simple REST API with API key auth
- Requires a Programmable Search Engine (CSE) configured for "Search the entire web"

**Note:** The *Site Restricted* variant of this API was deprecated (Jan 2025). The standard Custom Search JSON API remains available. Monitor for future deprecation.

### Keep Tavily — Fallback

Same interface, lower quality. Keep as fallback for when Google search fails.

### Cost Comparison

| Option | Open Web? | Domain Filter? | Date Filter? | Cost/1K | Our Cost |
|--------|-----------|----------------|--------------|---------|----------|
| Custom Search API | Yes | Yes | Yes (`dateRestrict`) | $5 | **$0** (free tier) |
| Tavily (current) | Yes | Yes | Yes (`days`) | $5-8 | $0 (free tier) |
| Vertex AI Search | No | At index time | No | Enterprise | N/A |
| Grounding + Gemini | Yes | No | No | $35 | Overkill |

**All options are free at our scale (~32 queries/month).**

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

### Task 1: Create Programmable Search Engine

Manual setup in [Google Programmable Search Engine Console](https://programmablesearchengine.google.com/):
1. Create a new search engine
2. Set to "Search the entire web"
3. Note the Search Engine ID (cx)
4. Create API key in Google Cloud Console (or reuse existing)
5. Store both in Secret Manager: `google-cse-api-key`, `google-cse-cx`

### Task 2: Create `google_search_client.py`

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
    Search the web using Google Custom Search JSON API.

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
- REST API: `GET https://www.googleapis.com/customsearch/v1?key={key}&cx={cx}&q={query}`
- `dateRestrict=d{days}` for recency filtering
- `siteSearch={domain}&siteSearchFilter=i` for domain inclusion (one domain per request, or use `site:` in query)
- Map response items to existing result structure
- `num` param for max results (max 10 per request, pagination via `start`)
- Retry logic matching `tavily_client.py`

### Task 3: Integrate into Recommendation Pipeline

Modify `tools.py` recommendation search loop (~line 1619):

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
    search_result["search_provider"] = "google"
except Exception as e:
    logger.warning(f"Google search failed, falling back to Tavily: {e}")
    search_result = tavily_client.search(...)
    search_result["search_provider"] = "tavily"
```

### Task 4: Tests

- Unit tests for `google_search_client.py` (mock HTTP responses)
- Integration: verify fallback to Tavily on Google error
- Verify result format matches existing pipeline expectations
- Verify `search_provider` field in recommendation output

---

## Domain Filtering Approach

Google CSE's `siteSearch` param only accepts one domain. For multi-domain filtering, options:

1. **Use `site:` operator in query**: `"change management" site:mckinsey.com OR site:hbr.org` — limited to ~32 `site:` operators
2. **Configure CSE to search entire web** and rely on Google's natural ranking (recommended for our case — we want diverse discovery)
3. **Use `exclude_domains` via `-site:` in query** to filter out known low-quality domains

**Recommendation:** Don't restrict domains for Google search. Google's ranking already surfaces authoritative sources. Only use `exclude_domains` for known-bad domains (e.g., medium.com).

---

## Non-Goals

- No removal of Tavily (kept as fallback)
- No changes to ranking/scoring logic (same pipeline, better input)
- No changes to query generation (Epic 14 handles that)
- No Terraform changes (CSE is configured in Google Console, not GCP)

## Success Criteria

- Google search results have higher average authority scores than Tavily
- Fallback to Tavily works seamlessly on Google API errors
- Zero additional cost (free tier sufficient)
- `search_provider` logged for all recommendation runs

---

## Sources

- [Custom Search JSON API Overview](https://developers.google.com/custom-search/v1/overview)
- [Custom Search JSON API Reference](https://developers.google.com/custom-search/v1)
- [Vertex AI Search — NOT suitable for open web](https://docs.cloud.google.com/generative-ai-app-builder/docs/create-data-store-es)
- [Grounding with Google Search](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search)
- [Tavily API Credits & Pricing](https://docs.tavily.com/documentation/api-credits)
