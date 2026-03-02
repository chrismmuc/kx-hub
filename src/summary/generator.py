"""
LLM Summary Generation (Story 9.2).

Takes the structured data from data_pipeline.collect_summary_data() and
generates a narrative weekly knowledge summary in German using Gemini 3.1 Pro.

Output: Obsidian-flavored Markdown with frontmatter, thematic sections,
callouts, and external links.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

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

SYSTEM_PROMPT = """\
Du bist ein redaktioneller Wissens-Kurator. Du erstellst wöchentliche \
Knowledge Summaries aus Readwise-Highlights.

Regeln:
- Sprache: Deutsch
- Stil: Journalistisch-analytisch, keine Floskeln, konkrete Aussagen
- Thematische Gruppierung: Fasse verwandte Quellen in 2-5 thematische \
Abschnitte zusammen. NICHT eine Sektion pro Quelle.
- Jeder Abschnitt hat: Fließtext-Zusammenfassung, optional Takeaway-Callout, \
Verbindungen-Callout (wenn vorhanden), Quellenlinks
- Icons: 🎙️ vor Podcast-Quellen, 📖 vor Buch-Quellen
- Links: NUR externe URLs (readwise.io, share.snipd.com, Original-URLs). \
KEINE Obsidian-Wikilinks ([[...]]).
- Callout-Syntax: > [!tip] für Takeaways, > [!example] für Verbindungen
- Verbindungen: Nutze relationship_type (extends, contradicts, supports, \
applies to, relates to) als Präfix in **Bold**
"""


def _build_prompt(data: Dict[str, Any]) -> str:
    """Build the user prompt from pipeline data."""
    period = data["period"]
    stats = data["stats"]
    sources = data["sources"]
    relationships = data["relationships"]

    # Format source type counts
    type_parts = []
    for stype, count in sorted(stats["source_types"].items()):
        if stype == "book":
            type_parts.append(f"{count} 📖 Buch" if count == 1 else f"{count} 📖 Bücher")
        elif stype == "podcast":
            type_parts.append(f"{count} 🎙️ Podcast" + ("s" if count > 1 else ""))
        else:
            type_parts.append(f"{count} Artikel")
    type_str = ", ".join(type_parts)

    lines = [
        f"Erstelle eine Knowledge Summary für den Zeitraum {period['start']} bis {period['end']}.",
        f"Statistik: {stats['total_highlights']} Highlights aus {stats['total_sources']} Quellen ({type_str}), {stats['total_relationships']} Verbindungen.",
        "",
        "=== QUELLEN ===",
    ]

    # Sources with knowledge cards
    for src in sources:
        icon = "🎙️ " if src["type"] == "podcast" else ("📖 " if src["type"] == "book" else "")
        lines.append(f"\n### {icon}{src['title']} ({src['author']})")
        lines.append(f"Typ: {src['type']}")
        if src.get("readwise_url"):
            lines.append(f"Readwise: {src['readwise_url']}")
        if src.get("source_url") and src["source_url"] != src.get("readwise_url"):
            lines.append(f"Original: {src['source_url']}")

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
        lines.append("\n=== VERBINDUNGEN ===")
        for rel in relationships:
            icon = ""
            if "snipd.com" in (rel.get("target_source_url") or ""):
                icon = "🎙️ "
            url = rel.get("target_readwise_url") or rel.get("target_source_url") or ""
            lines.append(
                f"- {rel['from_title']} → **{rel['relationship_type']}** "
                f"{icon}[{rel['target_title']}]({url}) ({rel.get('target_author', '')}): "
                f"{rel.get('explanation', '')}"
            )

    lines.append("\n=== ANWEISUNGEN ===")
    lines.append(
        "Generiere NUR den Markdown-Body (OHNE Frontmatter, OHNE die H1-Überschrift, "
        "OHNE die Statistik-Zeile). Beginne direkt mit dem ersten thematischen H2-Abschnitt. "
        "Ende mit der Fußzeile: *Generiert aus N Quellen via kx-hub am [Datum] · M Cross-Source-Verbindungen (K 🎙️ Podcasts)*"
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

    months_de = {
        1: "Jan", 2: "Feb", 3: "Mär", 4: "Apr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Dez",
    }

    start_str = f"{start.day}. {months_de[start.month]}"
    end_str = f"{end.day}. {months_de[end.month]} {end.year}"

    # Source type breakdown
    type_parts = []
    st = stats["source_types"]
    if st.get("book"):
        n = st["book"]
        type_parts.append(f"{n} Buch" if n == 1 else f"{n} Bücher")
    if st.get("article"):
        type_parts.append(f"{st['article']} Artikel")
    if st.get("podcast"):
        n = st["podcast"]
        type_parts.append(f"{n} 🎙️ Podcast" + ("s" if n > 1 else ""))
    type_str = ", ".join(type_parts)

    header = f"# Knowledge Summary: {start_str} – {end_str}\n"
    header += f"\n**{stats['total_highlights']} neue Highlights** aus {stats['total_sources']} Quellen ({type_str})"
    if stats["total_relationships"] > 0:
        header += f" · **{stats['total_relationships']} Verbindungen**"

    return header


def generate_summary(data: Dict[str, Any], model: str | None = None) -> Dict[str, Any]:
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
    prompt = _build_prompt(data)

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
