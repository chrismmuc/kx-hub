"""Transform Readwise JSON data to normalized Markdown with frontmatter."""

import yaml
from datetime import datetime
from typing import Dict, List, Any, Optional


def generate_frontmatter(book: Dict[str, Any]) -> str:
    """
    Generate YAML frontmatter from book JSON.

    Args:
        book: Readwise book JSON object

    Returns:
        YAML frontmatter string with --- delimiters
    """
    # Extract highlights for metadata
    highlights = book.get("highlights", [])

    # Get timestamps - use first and last highlight if available
    created_at = None
    updated_at = None
    if highlights:
        # Sort by created_at to get earliest and latest
        sorted_by_created = sorted(
            highlights,
            key=lambda h: h.get("created_at", "")
        )
        created_at = sorted_by_created[0].get("created_at")

        sorted_by_updated = sorted(
            highlights,
            key=lambda h: h.get("updated_at", "")
        )
        updated_at = sorted_by_updated[-1].get("updated_at")

    # Extract tags from book_tags (book-level) and highlights (highlight-level)
    tags = []

    # First, get book-level tags
    for tag in book.get("book_tags", []):
        tag_name = tag.get("name") if isinstance(tag, dict) else tag
        if tag_name and tag_name not in tags:
            tags.append(tag_name)

    # Then, get highlight-level tags
    for highlight in highlights:
        for tag in highlight.get("tags", []):
            tag_name = tag.get("name") if isinstance(tag, dict) else tag
            if tag_name and tag_name not in tags:
                tags.append(tag_name)

    # Extract URL fields (Story 2.7: URL Link Storage)
    # - readwise_url: Book review URL (always present)
    # - source_url: Original source URL (often null for Kindle books)
    # - highlight_url: First highlight's readwise_url (for traceability)
    readwise_url = book.get("readwise_url")
    source_url = book.get("source_url")  # Often null for books

    # Get first highlight's readwise_url if available (for highlight-level traceability)
    highlight_url = None
    if highlights:
        highlight_url = highlights[0].get("readwise_url")

    # Build frontmatter dict
    frontmatter_data = {
        "id": str(book["user_book_id"]),
        "title": book.get("title", "Untitled"),
        "author": book.get("author", "Unknown"),
        "source": book.get("source", "unknown"),
        "url": readwise_url,  # Keep legacy field for backward compatibility
        "readwise_url": readwise_url,
        "source_url": source_url,
        "highlight_url": highlight_url,
        "created_at": created_at,
        "updated_at": updated_at,
        "tags": tags,
        "highlight_count": len(highlights),
        "user_book_id": book["user_book_id"],
        "category": book.get("category", "unknown")
    }

    # Generate YAML
    yaml_content = yaml.dump(
        frontmatter_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False
    )

    return f"---\n{yaml_content}---\n"


def transform_highlights(highlights: List[Dict[str, Any]]) -> str:
    """
    Transform highlights array to Markdown blockquotes.

    Args:
        highlights: List of highlight objects

    Returns:
        Markdown formatted highlights section
    """
    if not highlights:
        return "## Highlights\n\nNo highlights available.\n"

    lines = ["## Highlights\n"]

    for highlight in highlights:
        text = highlight.get("text", "")
        note = highlight.get("note", "")
        location = highlight.get("location")
        location_type = highlight.get("location_type", "location")
        highlighted_at = highlight.get("highlighted_at")

        # Add blockquote
        lines.append(f"> {text}")

        # Add metadata
        if location:
            # Capitalize location type (page, location, etc.)
            location_label = location_type.capitalize() if location_type != "location" else "Location"
            lines.append(f"> - {location_label}: {location}")

        if note:
            lines.append(f"> - Note: {note}")

        if highlighted_at:
            lines.append(f"> - Highlighted: {highlighted_at}")

        # Empty line between highlights
        lines.append("")

    return "\n".join(lines)


def json_to_markdown(book: Dict[str, Any]) -> str:
    """
    Convert complete book JSON to Markdown with frontmatter.

    Args:
        book: Readwise book JSON object

    Returns:
        Complete Markdown document with YAML frontmatter
    """
    # Generate frontmatter
    frontmatter = generate_frontmatter(book)

    # Generate title section
    title = book.get("title", "Untitled")
    author = book.get("author", "Unknown")
    source = book.get("source", "unknown")

    # Capitalize source for display
    source_display = source.capitalize()

    title_section = f"""# {title}

**Author:** {author}
**Source:** {source_display}

"""

    # Generate highlights
    highlights_section = transform_highlights(book.get("highlights", []))

    # Combine all sections
    return frontmatter + "\n" + title_section + highlights_section
