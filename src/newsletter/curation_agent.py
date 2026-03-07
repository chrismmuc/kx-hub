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
            hot_news = [HotNewsItem(**n) for n in data.get("hot_news", [])]
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


def _resolve_snipd_url(snipd_url: str) -> str:
    """Fetch Snipd share page and extract original podcast URL (Spotify / YouTube / Apple).
    Returns "" if nothing found — caller will render title without link.
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
        logger.debug(f"Snipd URL resolution failed for {snipd_url}: {e}")
    logger.info(f"Snipd URL unresolvable, will render as plain text: {snipd_url}")
    return ""


def _resolve_book_url(title: str, author: str) -> str:
    """Build an Amazon search URL for a book."""
    query = f"{title} {author}".strip()
    return f"https://www.amazon.com/s?k={quote_plus(query)}"


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
            resolved_url = _resolve_snipd_url(url)

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

        if resolved_url != url:
            logger.info(f"URL resolved: {url!r} → {resolved_url!r}")
            src = src.model_copy(update={"url": resolved_url})
        resolved.append(src)

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
