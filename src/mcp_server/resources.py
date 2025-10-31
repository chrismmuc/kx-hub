"""
MCP Resource handlers for exposing kb_items chunks.

Resources provide read-only access to chunks via URIs like:
- kxhub://chunk/{chunk_id}
- kxhub://chunks/by-source/{source}
- kxhub://chunks/by-author/{author}
- kxhub://chunks/by-tag/{tag}
"""

import logging
from typing import List
from urllib.parse import unquote
from mcp.types import Resource, TextContent
import firestore_client

logger = logging.getLogger(__name__)


def list_resources() -> List[Resource]:
    """
    List all available chunk resources.

    Returns:
        List of MCP Resource objects with URIs and metadata
    """
    try:
        logger.info("Listing all chunk resources...")

        chunks = firestore_client.list_all_chunks(limit=1000)  # Increased limit for full KB

        resources = []
        for chunk in chunks:
            chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
            title = chunk.get('title', 'Untitled')
            author = chunk.get('author', 'Unknown')
            source = chunk.get('source', 'unknown')
            chunk_index = chunk.get('chunk_index', 0)
            total_chunks = chunk.get('total_chunks', 1)

            # Create resource with URI
            uri = f"kxhub://chunk/{chunk_id}"

            # Build description with metadata
            description = f"{title} by {author} (Source: {source}, Chunk {chunk_index + 1}/{total_chunks})"

            resource = Resource(
                uri=uri,
                name=f"Chunk: {title} [{chunk_index + 1}/{total_chunks}]",
                description=description,
                mimeType="text/markdown"
            )

            resources.append(resource)

        logger.info(f"Listed {len(resources)} chunk resources")
        return resources

    except Exception as e:
        logger.error(f"Failed to list resources: {e}")
        return []


def read_resource(uri: str) -> str:
    """
    Read a chunk resource by URI.

    Supported URI patterns:
    - kxhub://chunk/{chunk_id}              → Single chunk
    - kxhub://chunks/by-source/{source}     → All chunks from source
    - kxhub://chunks/by-author/{author}     → All chunks by author
    - kxhub://chunks/by-tag/{tag}           → All chunks with tag

    Args:
        uri: Resource URI

    Returns:
        Markdown content or error message
    """
    try:
        logger.info(f"Reading resource: {uri}")

        # Parse URI
        if uri.startswith("kxhub://chunk/"):
            # Single chunk
            chunk_id = uri.replace("kxhub://chunk/", "")
            chunk_id = unquote(chunk_id)  # URL decode

            chunk = firestore_client.get_chunk_by_id(chunk_id)

            if not chunk:
                return f"# Error\n\nChunk not found: {chunk_id}"

            return format_chunk_markdown(chunk)

        elif uri.startswith("kxhub://chunks/by-source/"):
            # Filter by source
            source = uri.replace("kxhub://chunks/by-source/", "")
            source = unquote(source)

            chunks = firestore_client.query_by_metadata(source=source, limit=50)

            if not chunks:
                return f"# No Chunks Found\n\nNo chunks found for source: {source}"

            return format_multiple_chunks(chunks, f"Source: {source}")

        elif uri.startswith("kxhub://chunks/by-author/"):
            # Filter by author
            author = uri.replace("kxhub://chunks/by-author/", "")
            author = unquote(author)

            chunks = firestore_client.query_by_metadata(author=author, limit=50)

            if not chunks:
                return f"# No Chunks Found\n\nNo chunks found for author: {author}"

            return format_multiple_chunks(chunks, f"Author: {author}")

        elif uri.startswith("kxhub://chunks/by-tag/"):
            # Filter by tag
            tag = uri.replace("kxhub://chunks/by-tag/", "")
            tag = unquote(tag)

            chunks = firestore_client.query_by_metadata(tags=[tag], limit=50)

            if not chunks:
                return f"# No Chunks Found\n\nNo chunks found for tag: {tag}"

            return format_multiple_chunks(chunks, f"Tag: {tag}")

        else:
            return f"# Error\n\nUnsupported URI pattern: {uri}"

    except Exception as e:
        logger.error(f"Failed to read resource {uri}: {e}")
        return f"# Error\n\nFailed to read resource: {str(e)}"


def format_chunk_markdown(chunk: dict) -> str:
    """
    Format a single chunk as markdown.

    Args:
        chunk: Chunk dictionary from Firestore

    Returns:
        Markdown-formatted chunk with metadata
    """
    chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
    title = chunk.get('title', 'Untitled')
    author = chunk.get('author', 'Unknown')
    source = chunk.get('source', 'unknown')
    tags = chunk.get('tags', [])
    chunk_index = chunk.get('chunk_index', 0)
    total_chunks = chunk.get('total_chunks', 1)
    content = chunk.get('content', '*No content available*')

    # Build markdown
    md = f"# {title}\n\n"
    md += f"**Author:** {author}  \n"
    md += f"**Source:** {source}  \n"

    if tags:
        md += f"**Tags:** {', '.join(tags)}  \n"

    md += f"**Chunk:** {chunk_index + 1} of {total_chunks}  \n"
    md += f"**ID:** `{chunk_id}`\n\n"
    md += "---\n\n"
    md += content

    return md


def format_multiple_chunks(chunks: List[dict], filter_description: str) -> str:
    """
    Format multiple chunks as markdown.

    Args:
        chunks: List of chunk dictionaries
        filter_description: Description of the filter applied

    Returns:
        Markdown-formatted list of chunks
    """
    md = f"# Chunks - {filter_description}\n\n"
    md += f"**Total Results:** {len(chunks)}\n\n"
    md += "---\n\n"

    for i, chunk in enumerate(chunks, 1):
        chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
        title = chunk.get('title', 'Untitled')
        author = chunk.get('author', 'Unknown')
        chunk_index = chunk.get('chunk_index', 0)
        total_chunks = chunk.get('total_chunks', 1)
        content = chunk.get('content', '')

        # Snippet (first 300 chars)
        snippet = content[:300] + "..." if len(content) > 300 else content

        md += f"## {i}. {title} [{chunk_index + 1}/{total_chunks}]\n\n"
        md += f"**Author:** {author}  \n"
        md += f"**ID:** `{chunk_id}`\n\n"
        md += f"{snippet}\n\n"
        md += "---\n\n"

    return md
