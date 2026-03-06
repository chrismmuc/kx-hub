"""
LLM Summary Generation (Story 9.2).

Takes the structured data from data_pipeline.collect_summary_data() and
generates a narrative weekly knowledge summary in English using Gemini 3.1 Pro.

Output: Obsidian-flavored Markdown with frontmatter, thematic sections,
callouts, and external links.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Lazy import to support both package and flat imports (Cloud Functions)
_get_client = None
_GenerationConfig = None


def _ensure_llm_imports():
    global _get_client, _GenerationConfig
    if _get_client is None:
        try:
            from src.llm import get_client
            from src.llm.base import GenerationConfig
        except ImportError:
            from llm import get_client
            from llm.base import GenerationConfig
        _get_client = get_client
        _GenerationConfig = GenerationConfig


SUMMARY_MODEL = "gemini-3.1-pro-preview"

RELATIONSHIP_TYPE_LABELS = {
    "extends": "deepens the point",
    "contradicts": "contrasts with",
    "supports": "supports this view",
    "applies to": "applies the idea to",
    "applies_to": "applies the idea to",
    "relates to": "connects to",
    "relates_to": "connects to",
}

SYSTEM_PROMPT = """\
You are an editorial knowledge curator. You create weekly Knowledge \
Summaries from Readwise highlights.

Rules:
- Language: English
- Style: Journalistic, analytical, concrete, no filler
- Thematic grouping: Combine related sources into 2-5 thematic sections. Do \
NOT create one section per source.
- Preferred section order: optional takeaway callout directly below the H2, \
then narrative synthesis, then a Connections callout (if useful), then a \
source list at the end of the section
- Icons: 🎙️ before podcast sources, 📖 before book sources
- Links: ONLY external URLs (readwise.io, share.snipd.com, original source \
URLs). NO Obsidian wikilinks ([[...]]).
- Callout syntax: > [!tip] for takeaways, > [!example] for connections
- If a section has a clear core point, state it first as a short takeaway \
callout and explain it in the prose afterward.
- Every section MUST end with `**Sources:**`, followed by a flat bullet list \
of all relevant sources for that section. One source per bullet. Do not hide \
sources inside the prose.
- For connections, every bullet MUST link the target article clearly in the \
format `[Title](URL): Explanation`. Use the provided `Link` of the target \
source.
- For `**Sources:**`, use the format `[Title (Author)](URL)`. Prefer the \
provided `Source list link` (Readwise), and only fall back to `Link` if it is \
missing.
- Connections: phrase relationships in natural English. Do NOT use raw schema \
labels like extends, contradicts, supports, applies_to, or relates_to in the \
final text. Use short, natural phrasing such as "deepens the point", "stands \
in contrast", "supports this view", "applies the idea", or "connects to it \
thematically".
"""


def _relationship_type_hint(relationship_type: str) -> str:
    """Map schema relationship types to natural-language English hints."""
    if not relationship_type:
        return "connects to"

    normalized = relationship_type.strip().lower()
    return RELATIONSHIP_TYPE_LABELS.get(normalized, "connects to")


def _preferred_link(source_url: str | None, readwise_url: str | None) -> str:
    """Prefer the original source URL, fall back to Readwise only if needed."""
    if source_url:
        return source_url
    return readwise_url or ""


def _preferred_sources_list_link(readwise_url: str | None, source_url: str | None) -> str:
    """Prefer Readwise for section source lists, fall back to original URL."""
    if readwise_url:
        return readwise_url
    return source_url or ""


def _build_prompt(data: Dict[str, Any], recurring_themes: List[str] | None = None) -> str:
    """Build the user prompt from pipeline data."""
    period = data["period"]
    stats = data["stats"]
    sources = data["sources"]
    relationships = data["relationships"]

    # Format source type counts
    type_parts = []
    for stype, count in sorted(stats["source_types"].items()):
        if stype == "book":
            type_parts.append(f"{count} 📖 book" if count == 1 else f"{count} 📖 books")
        elif stype == "podcast":
            type_parts.append(f"{count} 🎙️ podcast" + ("s" if count > 1 else ""))
        else:
            type_parts.append(f"{count} article" + ("s" if count > 1 else ""))
    type_str = ", ".join(type_parts)

    lines = [
        f"Create a Knowledge Summary for the period {period['start']} to {period['end']}.",
        f"Stats: {stats['total_highlights']} highlights from {stats['total_sources']} sources ({type_str}), {stats['total_relationships']} connections.",
        "",
    ]

    # Recurring themes context
    if recurring_themes:
        lines.append("=== RECURRING THEMES (last 4 weeks) ===")
        for theme in recurring_themes:
            lines.append(f"- {theme}")
        lines.append(
            "Note: Acknowledge continuity where natural — e.g. 'This week continues the thread on X'. "
            "Do not force mentions. Skip if not organically relevant."
        )
        lines.append("")

    lines.append("=== SOURCES ===")

    # Sources with knowledge cards
    for src in sources:
        icon = "🎙️ " if src["type"] == "podcast" else ("📖 " if src["type"] == "book" else "")
        preferred_link = _preferred_link(src.get("source_url"), src.get("readwise_url"))
        sources_list_link = _preferred_sources_list_link(src.get("readwise_url"), src.get("source_url"))
        lines.append(f"\n### {icon}{src['title']} ({src['author']})")
        lines.append(f"Type: {src['type']}")
        if preferred_link:
            lines.append(f"Link: {preferred_link}")
        if sources_list_link:
            lines.append(f"Source list link: {sources_list_link}")

        for chunk in src["chunks"]:
            kc = chunk.get("knowledge_card", {})
            if kc.get("summary"):
                lines.append(f"\n**Chunk {chunk['chunk_id']}:**")
                lines.append(f"Summary: {kc['summary']}")
                if kc.get("takeaways"):
                    lines.append("Takeaways:")
                    for t in kc["takeaways"]:
                        lines.append(f"  - {t}")

    # Relationships
    if relationships:
        lines.append("\n=== CONNECTIONS ===")
        for rel in relationships:
            icon = ""
            if "snipd.com" in (rel.get("target_source_url") or ""):
                icon = "🎙️ "
            url = _preferred_link(rel.get("target_source_url"), rel.get("target_readwise_url"))
            lines.append(
                f"- {rel['from_title']} -> relationship hint: "
                f"{_relationship_type_hint(rel.get('relationship_type', ''))} "
                f"with {icon}[{rel['target_title']}]({url}) ({rel.get('target_author', '')}): "
                f"{rel.get('explanation', '')}"
            )

    lines.append("\n=== INSTRUCTIONS ===")
    lines.append(
        "Generate ONLY the Markdown body (WITHOUT frontmatter, WITHOUT the H1 title, "
        "WITHOUT the stats line). Start directly with the first thematic H2 section. "
        "If you use a takeaway callout, place it directly below the H2 and before the prose. "
        "In the `Connections` section, every bullet should contain a clearly linked article in the format "
        "`[Title](URL): Explanation`. "
        "End every section with `**Sources:**` and a bullet list of all sources belonging to that section. "
        "Render those sources as `[Title (Author)](URL)` and prefer `Source list link` (Readwise), otherwise `Link`. "
        "End with the footer: *Generated from N sources via kx-hub on [date] · M cross-source connections (K 🎙️ podcasts)*"
    )

    return "\n".join(lines)


def _build_frontmatter(data: Dict[str, Any]) -> str:
    """Generate YAML frontmatter from pipeline stats."""
    period = data["period"]
    stats = data["stats"]
    now = datetime.now(timezone.utc)

    return f"""---
tags:
  - ai-weekly-summary
date: {now.strftime('%Y-%m-%d')}
period: {period['start']} to {period['end']}
sources: {stats['total_sources']}
highlights: {stats['total_highlights']}
connections: {stats['total_relationships']}
---"""


def _build_header(data: Dict[str, Any]) -> str:
    """Generate the H1 header + stats line."""
    period = data["period"]
    stats = data["stats"]

    # Format period as "28. Feb – 2. Mar 2026"
    from datetime import datetime as dt
    start = dt.strptime(period["start"], "%Y-%m-%d")
    end = dt.strptime(period["end"], "%Y-%m-%d")

    months_en = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }

    start_str = f"{start.day}. {months_en[start.month]}"
    end_str = f"{end.day}. {months_en[end.month]} {end.year}"

    # Source type breakdown
    type_parts = []
    st = stats["source_types"]
    if st.get("book"):
        n = st["book"]
        type_parts.append(f"{n} book" if n == 1 else f"{n} books")
    if st.get("article"):
        n = st["article"]
        type_parts.append(f"{n} article" if n == 1 else f"{n} articles")
    if st.get("podcast"):
        n = st["podcast"]
        type_parts.append(f"{n} 🎙️ podcast" + ("s" if n > 1 else ""))
    type_str = ", ".join(type_parts)

    header = f"# Knowledge Summary: {start_str} – {end_str}\n"
    header += f"\n**{stats['total_highlights']} new highlights** from {stats['total_sources']} sources ({type_str})"
    if stats["total_relationships"] > 0:
        header += f" · **{stats['total_relationships']} connection" + ("s" if stats["total_relationships"] != 1 else "") + "**"

    return header


def generate_summary(
    data: Dict[str, Any],
    model: str | None = None,
    recurring_themes: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Generate a weekly knowledge summary using Gemini 3.1 Pro.

    Args:
        data: Output from collect_summary_data()
        model: Override model (default: gemini-3.1-pro-preview)

    Returns:
        Dict with:
          - markdown: Full Obsidian Markdown (frontmatter + header + body)
          - model: Model used
          - input_tokens: Token count
          - output_tokens: Token count
    """
    model_name = model or os.environ.get("SUMMARY_MODEL", SUMMARY_MODEL)

    if not data.get("sources"):
        return {
            "markdown": "",
            "model": model_name,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    _ensure_llm_imports()
    logger.info(f"Generating summary with {model_name}")

    client = _get_client(model_name)
    prompt = _build_prompt(data, recurring_themes=recurring_themes)

    config = _GenerationConfig(
        temperature=0.7,
        max_output_tokens=8192,
    )

    response = client.generate(prompt, config=config, system_prompt=SYSTEM_PROMPT)

    # Assemble full markdown
    frontmatter = _build_frontmatter(data)
    header = _build_header(data)
    body = response.text.strip()

    markdown = f"{frontmatter}\n\n{header}\n\n---\n\n{body}\n"

    logger.info(
        f"Summary generated: {len(markdown)} chars, "
        f"{response.input_tokens} in / {response.output_tokens} out tokens"
    )

    return {
        "markdown": markdown,
        "model": model_name,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }
