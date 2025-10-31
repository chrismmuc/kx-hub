"""
MCP Prompt templates for common knowledge base queries.

Provides pre-defined prompts that users can invoke with parameters
to quickly perform common query patterns.
"""

import logging
from typing import Dict, Any, List
from mcp.types import Prompt, PromptArgument, PromptMessage

logger = logging.getLogger(__name__)


def get_prompts() -> List[Prompt]:
    """
    Get list of available prompt templates.

    Returns:
        List of MCP Prompt objects
    """
    return [
        Prompt(
            name="find_insights_about",
            description="Search my reading highlights for insights about a specific topic",
            arguments=[
                PromptArgument(
                    name="topic",
                    description="The topic to search for (e.g., 'decision making', 'leadership', 'productivity')",
                    required=True
                )
            ]
        ),
        Prompt(
            name="author_deep_dive",
            description="Show all highlights from a specific author and identify key themes",
            arguments=[
                PromptArgument(
                    name="author",
                    description="Author name (e.g., 'Daniel Kahneman', 'James Clear')",
                    required=True
                )
            ]
        ),
        Prompt(
            name="tag_exploration",
            description="Explore all content tagged with a specific tag",
            arguments=[
                PromptArgument(
                    name="tag",
                    description="Tag to explore (e.g., 'psychology', 'business', 'self-improvement')",
                    required=True
                )
            ]
        ),
        Prompt(
            name="related_to_chunk",
            description="Find highlights related to a specific chunk",
            arguments=[
                PromptArgument(
                    name="chunk_id",
                    description="Chunk ID to find related content for",
                    required=True
                )
            ]
        )
    ]


def get_prompt_messages(prompt_name: str, arguments: Dict[str, str]) -> List[PromptMessage]:
    """
    Generate prompt messages for a given template.

    Args:
        prompt_name: Name of the prompt template
        arguments: Dictionary of argument values

    Returns:
        List of MCP PromptMessage objects
    """
    if prompt_name == "find_insights_about":
        topic = arguments.get("topic", "")
        return [
            PromptMessage(
                role="user",
                content={
                    "type": "text",
                    "text": f"""Please search my knowledge base for insights about {topic}.

Use the search_semantic tool to find relevant chunks, then analyze and synthesize the key insights. Focus on:
1. Main concepts and ideas
2. Practical applications
3. Surprising or counterintuitive findings
4. Connections between different sources

Present your findings in a well-organized summary."""
                }
            )
        ]

    elif prompt_name == "author_deep_dive":
        author = arguments.get("author", "")
        return [
            PromptMessage(
                role="user",
                content={
                    "type": "text",
                    "text": f"""Please analyze all highlights from {author} in my knowledge base.

Use the search_by_metadata tool to get all chunks by this author, then provide:
1. Overview of the author's main themes and ideas
2. Key quotes and insights
3. Recurring concepts across their work
4. How their ideas connect or evolve
5. Practical takeaways

Organize this as a comprehensive deep dive into the author's thinking."""
                }
            )
        ]

    elif prompt_name == "tag_exploration":
        tag = arguments.get("tag", "")
        return [
            PromptMessage(
                role="user",
                content={
                    "type": "text",
                    "text": f"""Please explore all content in my knowledge base tagged with '{tag}'.

Use the search_by_metadata tool to retrieve chunks with this tag, then:
1. Summarize the main themes and topics
2. Identify patterns and common ideas
3. Highlight standout quotes or insights
4. Suggest connections between different sources
5. Provide actionable takeaways

Present this as a curated exploration of the tag."""
                }
            )
        ]

    elif prompt_name == "related_to_chunk":
        chunk_id = arguments.get("chunk_id", "")
        return [
            PromptMessage(
                role="user",
                content={
                    "type": "text",
                    "text": f"""Please find and analyze content related to chunk {chunk_id}.

Use the get_related_chunks tool to find similar chunks, then:
1. Show the source chunk for context
2. Present the related chunks
3. Explain why they're related
4. Identify common themes
5. Suggest connections or insights

Help me understand the broader context around this chunk."""
                }
            )
        ]

    else:
        logger.warning(f"Unknown prompt template: {prompt_name}")
        return [
            PromptMessage(
                role="user",
                content={
                    "type": "text",
                    "text": f"Unknown prompt template: {prompt_name}"
                }
            )
        ]
