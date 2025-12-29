"""
MCP Resource handlers for exposing kb_items chunks and clusters.

Resources provide read-only access via URIs like:
- kxhub://chunk/{chunk_id}
- kxhub://chunks/by-source/{source}
- kxhub://chunks/by-author/{author}
- kxhub://chunks/by-tag/{tag}
- kxhub://clusters
- kxhub://cluster/{cluster_id}
- kxhub://cluster/{cluster_id}/cards
"""

import logging
from typing import List
from urllib.parse import unquote
from mcp.types import Resource, TextContent
from . import firestore_client

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

        elif uri == "kxhub://clusters":
            # List all clusters
            clusters = firestore_client.get_all_clusters()

            if not clusters:
                return "# No Clusters Found\n\nNo semantic clusters available."

            return format_clusters_list(clusters)

        elif uri.startswith("kxhub://cluster/") and uri.endswith("/cards"):
            # Cluster with knowledge cards
            cluster_id = uri.replace("kxhub://cluster/", "").replace("/cards", "")
            cluster_id = unquote(cluster_id)

            cluster = firestore_client.get_cluster_by_id(cluster_id)

            if not cluster:
                return f"# Error\n\nCluster not found: {cluster_id}"

            # Get cluster members with knowledge cards
            members = firestore_client.get_chunks_by_cluster(cluster_id, limit=50)

            return format_cluster_with_cards(cluster, members)

        elif uri.startswith("kxhub://cluster/"):
            # Single cluster details
            cluster_id = uri.replace("kxhub://cluster/", "")
            cluster_id = unquote(cluster_id)

            cluster = firestore_client.get_cluster_by_id(cluster_id)

            if not cluster:
                return f"# Error\n\nCluster not found: {cluster_id}"

            # Get cluster members
            members = firestore_client.get_chunks_by_cluster(cluster_id, limit=50)

            return format_cluster_details(cluster, members)

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

    # Story 2.7: Extract URL fields
    readwise_url = chunk.get('readwise_url')
    source_url = chunk.get('source_url')
    highlight_url = chunk.get('highlight_url')

    # Build markdown
    md = f"# {title}\n\n"
    md += f"**Author:** {author}  \n"
    md += f"**Source:** {source}  \n"

    if tags:
        md += f"**Tags:** {', '.join(tags)}  \n"

    md += f"**Chunk:** {chunk_index + 1} of {total_chunks}  \n"
    md += f"**ID:** `{chunk_id}`\n\n"

    # Story 2.7: Add URL links section
    if readwise_url or source_url or highlight_url:
        md += "**Links:**  \n"
        if readwise_url:
            md += f"- [Readwise]({readwise_url})  \n"
        if source_url:
            md += f"- [Original Source]({source_url})  \n"
        if highlight_url:
            md += f"- [Highlight]({highlight_url})  \n"
        md += "\n"

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

        # Story 2.7: Extract URL fields
        readwise_url = chunk.get('readwise_url')

        # Snippet (first 300 chars)
        snippet = content[:300] + "..." if len(content) > 300 else content

        md += f"## {i}. {title} [{chunk_index + 1}/{total_chunks}]\n\n"
        md += f"**Author:** {author}  \n"
        md += f"**ID:** `{chunk_id}`"
        if readwise_url:
            md += f" | [View in Readwise]({readwise_url})"
        md += "\n\n"
        md += f"{snippet}\n\n"
        md += "---\n\n"

    return md


def format_clusters_list(clusters: List[dict]) -> str:
    """
    Format list of all clusters as markdown.

    Args:
        clusters: List of cluster dictionaries

    Returns:
        Markdown-formatted clusters overview
    """
    md = "# Knowledge Base Clusters\n\n"
    md += f"**Total Clusters:** {len(clusters)}\n\n"
    md += "Semantic clusters organize your knowledge base by topic themes.\n\n"
    md += "---\n\n"

    for i, cluster in enumerate(clusters, 1):
        cluster_id = cluster.get('id', 'unknown')
        name = cluster.get('name', f'Cluster {cluster_id}')
        description = cluster.get('description', 'No description')
        size = cluster.get('size', 0)

        md += f"## {i}. {name}\n\n"
        md += f"**Cluster ID:** `{cluster_id}`  \n"
        md += f"**Size:** {size} chunks  \n"
        md += f"**Description:** {description}\n\n"
        md += f"**View Details:** `kxhub://cluster/{cluster_id}`  \n"
        md += f"**View with Cards:** `kxhub://cluster/{cluster_id}/cards`\n\n"
        md += "---\n\n"

    return md


def format_cluster_details(cluster: dict, members: List[dict]) -> str:
    """
    Format cluster details with member chunks.

    Args:
        cluster: Cluster dictionary
        members: List of member chunk dictionaries

    Returns:
        Markdown-formatted cluster overview
    """
    cluster_id = cluster.get('id', 'unknown')
    name = cluster.get('name', f'Cluster {cluster_id}')
    description = cluster.get('description', 'No description')
    size = cluster.get('size', 0)

    md = f"# {name}\n\n"
    md += f"**Cluster ID:** `{cluster_id}`  \n"
    md += f"**Total Members:** {size} chunks  \n"
    md += f"**Description:** {description}\n\n"
    md += "---\n\n"

    md += "## Member Chunks\n\n"

    for i, chunk in enumerate(members, 1):
        chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
        title = chunk.get('title', 'Untitled')
        author = chunk.get('author', 'Unknown')
        source = chunk.get('source', 'unknown')
        content = chunk.get('content', '')

        # Story 2.7: Extract URL fields
        readwise_url = chunk.get('readwise_url')

        # Snippet
        snippet = content[:200] + "..." if len(content) > 200 else content

        md += f"### {i}. {title}\n\n"
        md += f"**Author:** {author} | **Source:** {source}  \n"
        md += f"**ID:** `{chunk_id}`"
        if readwise_url:
            md += f" | [Readwise]({readwise_url})"
        md += "\n\n"
        md += f"{snippet}\n\n"

    md += f"\n**View with Knowledge Cards:** `kxhub://cluster/{cluster_id}/cards`\n"

    return md


def format_cluster_with_cards(cluster: dict, members: List[dict]) -> str:
    """
    Format cluster with knowledge card summaries for each member.

    Args:
        cluster: Cluster dictionary
        members: List of member chunk dictionaries

    Returns:
        Markdown-formatted cluster with knowledge cards
    """
    cluster_id = cluster.get('id', 'unknown')
    name = cluster.get('name', f'Cluster {cluster_id}')
    description = cluster.get('description', 'No description')
    size = cluster.get('size', 0)

    md = f"# {name} - Knowledge Cards\n\n"
    md += f"**Cluster ID:** `{cluster_id}`  \n"
    md += f"**Total Members:** {size} chunks  \n"
    md += f"**Description:** {description}\n\n"
    md += "---\n\n"

    md += "## Member Highlights (AI Summaries)\n\n"

    for i, chunk in enumerate(members, 1):
        chunk_id = chunk.get('id') or chunk.get('chunk_id', 'unknown')
        title = chunk.get('title', 'Untitled')
        author = chunk.get('author', 'Unknown')
        source = chunk.get('source', 'unknown')
        knowledge_card = chunk.get('knowledge_card', {})

        # Story 2.7: Extract URL fields
        readwise_url = chunk.get('readwise_url')

        md += f"### {i}. {title}\n\n"
        md += f"**Author:** {author} | **Source:** {source}  \n"
        md += f"**ID:** `{chunk_id}`"
        if readwise_url:
            md += f" | [Readwise]({readwise_url})"
        md += "\n\n"

        if knowledge_card:
            summary = knowledge_card.get('summary', 'No summary available')
            takeaways = knowledge_card.get('takeaways', [])

            md += f"**Summary:** {summary}\n\n"

            if takeaways:
                md += "**Key Takeaways:**\n\n"
                for takeaway in takeaways:
                    md += f"- {takeaway}\n"
                md += "\n"
        else:
            md += "*Knowledge card not available*\n\n"

    return md
