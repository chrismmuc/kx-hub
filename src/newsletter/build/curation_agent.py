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


def run_curation(sources: list[dict]) -> "CurationResult":
    """
    Run the newsletter curation agent.

    Args:
        sources: List of source dicts from collect_summary_data()

    Returns:
        CurationResult with filtered_sources and hot_news
    """
    agent_engine_id = os.getenv("NEWSLETTER_AGENT_ENGINE_ID", "")

    if not agent_engine_id:
        logger.info("No NEWSLETTER_AGENT_ENGINE_ID configured — using fallback curation")
        return _fallback_curation(sources)

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
            # ADK AgentEngine returns content events
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        result_text += part.text

        if not result_text:
            logger.warning("Agent returned empty response, using fallback")
            return _fallback_curation(sources)

        return _parse_curation_result(result_text, sources)

    except Exception as e:
        logger.warning(f"Curation agent failed: {e}. Using fallback.")
        return _fallback_curation(sources)
