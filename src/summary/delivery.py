"""
Reader Delivery (Story 9.3).

Saves the generated weekly summary to Readwise Reader inbox
with tag `ai-weekly-summary` and duplicate detection.
"""

import logging
import re
import requests
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

READER_API_URL = "https://readwise.io/api/v3"
SUMMARY_TAG = "ai-weekly-summary"


def _markdown_to_html(markdown: str) -> str:
    """
    Convert Obsidian-flavored Markdown to simple HTML for Reader.

    Handles: headers, bold, links, blockquotes/callouts, lists, horizontal rules.
    Strips YAML frontmatter.
    """
    lines = markdown.split("\n")
    html_lines: List[str] = []
    in_frontmatter = False
    in_blockquote = False

    for line in lines:
        # Skip YAML frontmatter
        if line.strip() == "---":
            if not in_frontmatter and not html_lines:
                in_frontmatter = True
                continue
            elif in_frontmatter:
                in_frontmatter = False
                continue
        if in_frontmatter:
            continue

        stripped = line.strip()

        # Horizontal rule
        if stripped == "---":
            if in_blockquote:
                html_lines.append("</blockquote>")
                in_blockquote = False
            html_lines.append("<hr>")
            continue

        # Headers (# to ######)
        if stripped.startswith("#"):
            level = 0
            for ch in stripped:
                if ch == "#":
                    level += 1
                else:
                    break
            if level <= 6 and len(stripped) > level and stripped[level] == " ":
                if in_blockquote:
                    html_lines.append("</blockquote>")
                    in_blockquote = False
                text = stripped[level + 1:]
                text = _inline_format(text)
                html_lines.append(f"<h{level}>{text}</h{level}>")
                continue

        # Blockquote / Callout
        if stripped.startswith("> "):
            content = stripped[2:]
            # Obsidian callout: > [!tip] Title
            callout_match = re.match(r"\[!(\w+)\]\s*(.*)", content)
            if callout_match:
                if in_blockquote:
                    html_lines.append("</blockquote>")
                callout_type = callout_match.group(1)
                callout_title = callout_match.group(2) or callout_type.capitalize()
                html_lines.append(f'<blockquote><strong>{callout_title}</strong><br>')
                in_blockquote = True
                continue
            content = _inline_format(content)
            if not in_blockquote:
                html_lines.append(f"<blockquote>{content}<br>")
                in_blockquote = True
            else:
                html_lines.append(f"{content}<br>")
            continue

        # End blockquote on non-quote line
        if in_blockquote and not stripped.startswith(">"):
            html_lines.append("</blockquote>")
            in_blockquote = False

        # Empty line
        if not stripped:
            continue

        # List items
        if stripped.startswith("- "):
            text = _inline_format(stripped[2:])
            html_lines.append(f"<li>{text}</li>")
            continue

        # Paragraph
        text = _inline_format(stripped)
        html_lines.append(f"<p>{text}</p>")

    if in_blockquote:
        html_lines.append("</blockquote>")

    return "\n".join(html_lines)


def _inline_format(text: str) -> str:
    """Apply inline formatting: bold, links, italic."""
    # Links: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Bold: **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic: *text*
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text


def deliver_to_reader(
    markdown: str,
    title: str,
    api_key: str,
    tags: Optional[List[str]] = None,
    image_url: Optional[str] = None,
    html_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Save summary to Readwise Reader inbox.

    Args:
        markdown: Full summary markdown (with frontmatter)
        title: Article title (e.g., "Knowledge Summary: 23. Feb – 2. Mar 2026")
        api_key: Readwise API token
        tags: Optional extra tags (ai-weekly-summary is always added)
        image_url: Optional cover image URL for Reader thumbnail
        html_url: Optional URL to hosted HTML page ("Open original" in Reader)

    Returns:
        Dict with status, reader_id, url
    """
    all_tags = [SUMMARY_TAG]
    if tags:
        all_tags.extend(t for t in tags if t != SUMMARY_TAG)

    html = _markdown_to_html(markdown)

    # URL used for Reader dedup and "Open original".
    # If html_url is available, use it so "Open original" opens a styled page.
    # Otherwise fall back to a stable slug-based URL for dedup.
    if html_url:
        stable_url = html_url
    else:
        stable_url = f"https://kx-hub.internal/summaries/{_slugify(title)}"

    payload = {
        "url": stable_url,
        "html": html,
        "title": title,
        "tags": all_tags,
        "saved_using": "kx-hub",
    }
    if image_url:
        payload["image_url"] = image_url

    logger.info(f"Saving summary to Reader: {title}")

    response = requests.post(
        f"{READER_API_URL}/save/",
        json=payload,
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    if not response.ok:
        logger.error(f"Reader API error {response.status_code}: {response.text}")
    response.raise_for_status()

    data = response.json()
    reader_url = data.get("url", "")

    logger.info(f"Summary saved to Reader: id={data.get('id')}")

    return {
        "status": "saved",
        "reader_id": data.get("id", ""),
        "reader_url": reader_url,
    }


def _slugify(text: str) -> str:
    """Convert title to URL-safe slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    return text.strip("-")
