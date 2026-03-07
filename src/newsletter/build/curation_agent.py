"""
Newsletter Curation Agent (Epic 15).

Uses a Vertex AI Agent Engine (ADK) with google_search to:
1. Filter/rank knowledge sources by external relevance
2. Find hot news items in AI & software from this week

Agent is pre-deployed via deploy_agent.py and referenced by
NEWSLETTER_AGENT_ENGINE_ID env var / Secret Manager.
"""

import json
import logging
import os
import re
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

GCP_PROJECT = os.getenv("GCP_PROJECT", "kx-hub")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")

# Known subscribed sources: maps lowercase title keywords → canonical external URL.
# Used to resolve podcast/video URLs before falling back to Snipd page fetch or LLM search.
KNOWN_SOURCES: dict[str, str] = {
    "ai daily brief": "https://open.spotify.com/show/6ybj5HZdxOJFhkSuFfPcOK",
    "dwarkesh": "https://podcasts.apple.com/us/podcast/dwarkesh-podcast/id1516093381",
    "karpathy": "https://podcasts.apple.com/us/podcast/lex-fridman-podcast/id1434243584",
    "armchair architects": "https://learn.microsoft.com/en-us/shows/armchair-architects/",
    "hard fork": "https://open.spotify.com/show/44fllCS2FTFr2x1ouYYZs5",
    "huberman": "https://open.spotify.com/show/79CkJF3UJTHFV8Dse3Oy0P",
    "lex fridman": "https://open.spotify.com/show/2MAi0BvDc6GTFvKFPXnkCL",
    "acquired": "https://open.spotify.com/show/7Fj0XEuUQLUqoMZQdsLXqp",
    "latent space": "https://open.spotify.com/show/2p22p6RmMeEcPEME2KNYB5",
    "practical ai": "https://open.spotify.com/show/1LaCr5TFAgYPK5qHjP3XDp",
    "changelog": "https://open.spotify.com/show/5bBki72YeKSLUqyD94qg2k",
    "software engineering daily": "https://open.spotify.com/show/6UNQ4oQTKZJJosrpnAOeEV",
    "gradient dissent": "https://open.spotify.com/show/7o9r3fFig3MhTJwehXDbXm",
    "twiml": "https://open.spotify.com/show/2sp5EL7s7EqxttxwwoJ3i7",
    "machine learning street talk": "https://open.spotify.com/show/02e6Q8kH9pDkrsoBcPOFb3",
}

AGENT_INSTRUCTION = """\
You are a tech newsletter curator for a senior software engineer audience.

Given a JSON list of personal knowledge sources (books, articles, podcasts the user
has been reading), your tasks are:

1. SELECT the 5-7 most interesting and externally relevant sources for a tech newsletter.
   Prefer sources with clear practical insights, novel ideas, or strong opinions.
   Skip overly niche or personal sources.

2. SEARCH for 3-5 hot news items in AI and software development from the past week using
   google_search. Use queries like "AI news this week", "software engineering news 2026",
   "LLM releases this week". Include only factual, verifiable items with real URLs.

Return ONLY a valid JSON object in this exact format (no markdown, no explanation):
{
  "filtered_sources": [
    {"title": "...", "url": "...", "source_type": "article|book|podcast", "summary": "...", "reason": "..."}
  ],
  "hot_news": [
    {"title": "...", "url": "...", "summary": "..."}
  ],
  "curator_notes": "..."
}
"""


def _format_sources_for_agent(sources: list[dict]) -> str:
    """Format sources as JSON string for agent input."""
    formatted = []
    for src in sources:
        formatted.append({
            "title": src.get("title", ""),
            "url": src.get("source_url", "") or src.get("readwise_url", ""),
            "source_type": src.get("type", "article"),
            "summary": _get_source_summary(src),
        })
    return json.dumps(formatted, ensure_ascii=False, indent=2)


def _get_source_summary(src: dict) -> str:
    """Extract best available summary from a source dict."""
    chunks = src.get("chunks", [])
    summaries = []
    for chunk in chunks[:2]:  # max 2 chunks for brevity
        kc = chunk.get("knowledge_card", {})
        if kc and kc.get("summary"):
            summaries.append(kc["summary"])
    return " | ".join(summaries) if summaries else ""


def _parse_curation_result(text: str, fallback_sources: list[dict]) -> "CurationResult":
    """
    Parse agent output into CurationResult.
    Tries JSON extraction first, falls back to using all sources with empty hot_news.
    """
    # Import here to avoid circular imports
    try:
        from src.newsletter.models import CurationResult, CuratedSource, HotNewsItem
    except ImportError:
        from models import CurationResult, CuratedSource, HotNewsItem

    # Try to extract JSON from the response
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            filtered = [CuratedSource(**s) for s in data.get("filtered_sources", [])]
            # Filter hot_news: drop items with grounding redirect or mailto URLs
            hot_news = []
            for n in data.get("hot_news", []):
                url = n.get("url", "")
                if _is_valid_hot_news_url(url):
                    hot_news.append(HotNewsItem(**n))
                else:
                    logger.info(f"Filtered bad hot_news URL: {url!r} for '{n.get('title', '')}'")
            return CurationResult(
                filtered_sources=filtered,
                hot_news=hot_news,
                curator_notes=data.get("curator_notes", ""),
            )
        except Exception as e:
            logger.warning(f"Failed to parse agent JSON response: {e}")

    # Fallback: use all sources, no hot news
    logger.info("Using fallback curation (all sources, no hot news)")
    return _fallback_curation(fallback_sources)


def _fallback_curation(sources: list[dict]) -> "CurationResult":
    """Return all sources as-is with empty hot_news (graceful degradation)."""
    try:
        from src.newsletter.models import CurationResult, CuratedSource
    except ImportError:
        from models import CurationResult, CuratedSource

    curated = []
    for src in sources:
        curated.append(CuratedSource(
            title=src.get("title", "Untitled"),
            url=src.get("source_url", "") or src.get("readwise_url", ""),
            source_type=src.get("type", "article"),
            summary=_get_source_summary(src),
            reason="",
        ))

    return CurationResult(filtered_sources=curated, hot_news=[], curator_notes="")


def _is_valid_hot_news_url(url: str) -> bool:
    """Return True for genuine external URLs suitable for hot news.
    Grounding redirect URLs (vertexaisearch) are accepted — they work, just unstable.
    """
    return (
        bool(url)
        and url.startswith("http")
        and "mailto:" not in url
        and "readwise.io" not in url
    )


def _match_known_source(title: str) -> str:
    """Check KNOWN_SOURCES for a matching show URL by title keyword (case-insensitive).
    Returns the show URL if matched, else "".
    """
    title_lower = title.lower()
    for keyword, url in KNOWN_SOURCES.items():
        if keyword in title_lower:
            return url
    return ""


def _resolve_snipd_url(snipd_url: str, title: str = "") -> str:
    """Resolve a Snipd share URL to an original podcast/video URL via page fetch.

    Snipd pages are JS-rendered so this rarely succeeds. Unresolved sources
    fall through to _batch_resolve_missing_urls (Gemini + Google Search).
    Returns "" if page fetch finds nothing.
    """
    try:
        import requests
        resp = requests.get(snipd_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        text = resp.text
        for pattern in [
            r'https://open\.spotify\.com/episode/[a-zA-Z0-9]+',
            r'https://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_\-]+',
            r'https://youtu\.be/[a-zA-Z0-9_\-]+',
            r'https://podcasts\.apple\.com/[^\s"\'<>&]+',
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(0)
    except Exception as e:
        logger.debug(f"Snipd page fetch failed for {snipd_url}: {e}")
    logger.info(f"Snipd URL unresolvable from page, queuing for batch resolve: {snipd_url}")
    return ""


def _resolve_book_url(title: str, author: str) -> str:
    """Build an Amazon search URL for a book."""
    query = f"{title} {author}".strip()
    return f"https://www.amazon.com/s?k={quote_plus(query)}"


def _batch_resolve_missing_urls(sources_to_resolve: list[dict]) -> dict[str, str]:
    """Use Gemini with Google Search grounding to find URLs for unresolved sources.

    Args:
        sources_to_resolve: list of {"title": ..., "author": ..., "type": ...}

    Returns:
        dict mapping title → URL (empty string if not found)
    """
    if not sources_to_resolve:
        return {}
    try:
        import os
        from google import genai
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

        client = genai.Client(
            vertexai=True,
            project=GCP_PROJECT,
            location="global",
        )

        items = "\n".join(
            f'- "{s["title"]}" ({s["type"]}) by {s["author"]}'
            for s in sources_to_resolve
        )
        prompt = (
            f"Search for the best direct URL for each of these podcast episodes, YouTube videos, and books.\n\n"
            f"{items}\n\n"
            f"For each item, search Google and return the most relevant URL you find.\n"
            f"Podcasts: use Spotify episode URL, Apple Podcasts episode URL, or the show's official page.\n"
            f"YouTube videos: use the youtube.com URL.\n"
            f"Books: use Amazon product page URL.\n\n"
            f"Return ONLY a JSON object (no markdown, no explanation):\n"
            f"{{\"exact title here\": \"https://...\"}}\n"
            f"Use the exact titles as keys. Do NOT return empty strings — include the best URL you found."
        )

        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=prompt,
            config=GenerateContentConfig(
                tools=[Tool(google_search=GoogleSearch())],
            ),
        )
        text = response.text.strip()
        logger.info(f"Batch URL resolution raw response (first 800 chars): {text[:800]}")

        # Strip markdown code fences if present
        text_clean = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text_clean = re.sub(r"\s*```$", "", text_clean, flags=re.MULTILINE).strip()

        m = re.search(r"\{.*\}", text_clean, re.DOTALL)
        if m:
            data = json.loads(m.group())
            logger.info(f"Batch URL resolution parsed: {data}")
            # Filter out grounding redirect URLs (unstable) and empty values
            clean = {}
            for k, v in data.items():
                if isinstance(v, str) and v and "vertexaisearch.cloud.google.com" not in v:
                    clean[k] = v
            logger.info(f"Batch URL resolution final: {clean}")
            return clean
        else:
            logger.warning(f"Batch URL resolution: no JSON found in response")
    except Exception as e:
        logger.warning(f"Batch URL resolution via Gemini grounding failed: {e}")
    return {}


def _infer_type_from_url(url: str, current_type: str) -> str:
    """Correct source_type based on the resolved URL."""
    if not url:
        return current_type
    if "youtube.com" in url or "youtu.be" in url:
        return "video"
    if "open.spotify.com/episode" in url or "podcasts.apple.com" in url:
        return "podcast"
    if "amazon.com" in url:
        return "book"
    return current_type


def _resolve_filtered_source_urls(result: "CurationResult", original_sources: list[dict]) -> "CurationResult":
    """Post-process: resolve snipd/readwise/internal URLs to direct external URLs.

    - snipd.com → Spotify / YouTube / Apple (or "" if unresolvable)
    - readwise.io (all types) → source_url from original data; for books → Amazon search
    - Any remaining internal/unresolvable URL → ""
    URL "" means: render title as plain text without hyperlink.
    """
    # Build lookup: title → source_url and author from original sources
    source_url_by_title: dict[str, str] = {}
    author_by_title: dict[str, str] = {}
    for s in original_sources:
        title = s.get("title", "")
        raw_url = s.get("source_url", "") or ""
        # Only keep genuinely external URLs
        if raw_url and "readwise.io" not in raw_url and "snipd.com" not in raw_url:
            source_url_by_title[title] = raw_url
        author_by_title[title] = s.get("author", "")

    resolved = []
    for src in result.filtered_sources:
        url = src.url

        if "snipd.com" in url:
            resolved_url = _resolve_snipd_url(url, title=src.title)

        elif "readwise.io" in url:
            # Try original source_url first
            direct = source_url_by_title.get(src.title, "")
            if direct:
                resolved_url = direct
            elif src.source_type == "book":
                author = src.author or author_by_title.get(src.title, "")
                resolved_url = _resolve_book_url(src.title, author)
            else:
                logger.info(f"Readwise URL unresolvable, will render as plain text: {url}")
                resolved_url = ""

        else:
            resolved_url = url

        updates: dict = {}
        if resolved_url != url:
            logger.info(f"URL resolved: {url!r} → {resolved_url!r}")
            updates["url"] = resolved_url
        # Fix source_type based on resolved URL
        corrected_type = _infer_type_from_url(resolved_url, src.source_type)
        if corrected_type != src.source_type:
            logger.info(f"Type corrected: {src.source_type!r} → {corrected_type!r} for '{src.title}'")
            updates["source_type"] = corrected_type
        if updates:
            src = src.model_copy(update=updates)
        resolved.append(src)

    # Batch-resolve remaining empty URLs via Gemini + Google Search grounding
    unresolved = [
        {"title": src.title, "author": src.author, "type": src.source_type}
        for src in resolved
        if not src.url
    ]
    if unresolved:
        llm_urls = _batch_resolve_missing_urls(unresolved)
        final = []
        for src in resolved:
            if not src.url and src.title in llm_urls and llm_urls[src.title]:
                new_url = llm_urls[src.title]
                logger.info(f"LLM-resolved URL for '{src.title}': {new_url}")
                updates = {"url": new_url}
                corrected = _infer_type_from_url(new_url, src.source_type)
                if corrected != src.source_type:
                    updates["source_type"] = corrected
                src = src.model_copy(update=updates)
            final.append(src)
        resolved = final

    return result.model_copy(update={"filtered_sources": resolved})


def run_curation(sources: list[dict]) -> "CurationResult":
    """
    Run the newsletter curation agent.

    Args:
        sources: List of source dicts from collect_summary_data()

    Returns:
        CurationResult with filtered_sources and hot_news
    """
    agent_engine_id = os.getenv("NEWSLETTER_AGENT_ENGINE_ID", "")

    # Env var may be stale placeholder "NOT_SET" — read live from Secret Manager
    if not agent_engine_id or agent_engine_id == "NOT_SET":
        try:
            from google.cloud import secretmanager as sm
            sm_client = sm.SecretManagerServiceClient()
            name = f"projects/{GCP_PROJECT}/secrets/newsletter-agent-engine-id/versions/latest"
            resp = sm_client.access_secret_version(request={"name": name})
            agent_engine_id = resp.payload.data.decode("UTF-8").strip()
            if agent_engine_id == "NOT_SET":
                agent_engine_id = ""
            logger.info(f"Loaded agent engine ID from Secret Manager: {bool(agent_engine_id)}")
        except Exception as e:
            logger.warning(f"Could not read agent engine ID from Secret Manager: {e}")
            agent_engine_id = ""

    if not agent_engine_id:
        logger.info("No NEWSLETTER_AGENT_ENGINE_ID configured — using fallback curation")
        result = _fallback_curation(sources)
        return _resolve_filtered_source_urls(result, sources)

    try:
        import vertexai
        from vertexai import agent_engines

        vertexai.init(project=GCP_PROJECT, location=GCP_REGION)
        remote_app = agent_engines.get(agent_engine_id)

        prompt = f"Here are the knowledge sources to curate:\n\n{_format_sources_for_agent(sources)}"

        result_text = ""
        for event in remote_app.stream_query(
            user_id="newsletter-generator",
            message=prompt,
        ):
            # Event is a dict: {"content": {"parts": [{"text": "..."}]}, ...}
            if isinstance(event, dict):
                content = event.get("content") or {}
                for part in (content.get("parts") or []):
                    if isinstance(part, dict) and part.get("text"):
                        result_text += part["text"]
            elif isinstance(event, str):
                result_text += event
            elif hasattr(event, "text") and event.text:
                result_text += event.text
            elif hasattr(event, "content") and event.content:
                for part in (getattr(event.content, "parts", None) or []):
                    if hasattr(part, "text") and part.text:
                        result_text += part.text

        logger.info(f"Agent raw response length: {len(result_text)} chars")
        if not result_text:
            logger.warning("Agent returned empty response, using fallback")
            result = _fallback_curation(sources)
        else:
            result = _parse_curation_result(result_text, sources)
        return _resolve_filtered_source_urls(result, sources)

    except Exception as e:
        logger.warning(f"Curation agent failed: {e}. Using fallback.")
        result = _fallback_curation(sources)
        return _resolve_filtered_source_urls(result, sources)
