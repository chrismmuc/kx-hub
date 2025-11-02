"""
Prompt Manager for Knowledge Card Generation

Handles loading, formatting, and managing LLM prompts.
Story 2.1: Knowledge Card Generation (Epic 2)
"""

import os
from pathlib import Path
from typing import Dict, Any


class PromptManager:
    """
    Manages prompts for knowledge card generation.

    Handles:
    - Loading prompt templates from files
    - Formatting prompts with chunk data
    - Validating prompt structure
    """

    def __init__(self, prompt_dir: str = None):
        """
        Initialize prompt manager.

        Args:
            prompt_dir: Directory containing prompt files (defaults to package prompts/)
        """
        if prompt_dir is None:
            # Default to prompts/ directory in this package
            self.prompt_dir = Path(__file__).parent / 'prompts'
        else:
            self.prompt_dir = Path(prompt_dir)

        self._prompt_cache = {}

    def load_prompt(self, prompt_name: str = 'card_generation_prompt.txt') -> str:
        """
        Load prompt template from file.

        Args:
            prompt_name: Name of prompt file (default: card_generation_prompt.txt)

        Returns:
            Prompt template string

        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        # Check cache first
        if prompt_name in self._prompt_cache:
            return self._prompt_cache[prompt_name]

        prompt_path = self.prompt_dir / prompt_name

        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {prompt_path}. "
                f"Available prompts: {list(self.prompt_dir.glob('*.txt'))}"
            )

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        # Cache for future use
        self._prompt_cache[prompt_name] = prompt_template

        return prompt_template

    def format_prompt(
        self,
        title: str,
        author: str,
        content: str,
        prompt_template: str = None
    ) -> str:
        """
        Format prompt template with chunk data.

        Args:
            title: Chunk title
            author: Chunk author
            content: Full chunk content (text)
            prompt_template: Optional custom template (loads default if None)

        Returns:
            Formatted prompt ready for LLM API

        Example:
            >>> pm = PromptManager()
            >>> prompt = pm.format_prompt(
            ...     title="Deep Work",
            ...     author="Cal Newport",
            ...     content="The ability to perform deep work is becoming..."
            ... )
        """
        if prompt_template is None:
            prompt_template = self.load_prompt()

        # Format with chunk data
        # Use replace() instead of format() to avoid conflicts with JSON braces in examples
        # Handle None values by converting to empty string or placeholder
        safe_title = title if title is not None else "Unknown"
        safe_author = author if author is not None else "Unknown"
        safe_content = content if content is not None else ""

        formatted_prompt = prompt_template.replace('{title}', safe_title)
        formatted_prompt = formatted_prompt.replace('{author}', safe_author)
        formatted_prompt = formatted_prompt.replace('{content}', safe_content)

        return formatted_prompt

    def get_prompt_stats(self, prompt: str) -> Dict[str, Any]:
        """
        Get statistics about a formatted prompt.

        Args:
            prompt: Formatted prompt string

        Returns:
            Dictionary with prompt statistics:
            - char_count: Total characters
            - word_count: Approximate word count
            - estimated_tokens: Rough token estimate (chars / 4)

        Note: Token estimation is approximate. Actual token count
        depends on the model's tokenizer.
        """
        char_count = len(prompt)
        word_count = len(prompt.split())

        # Rough token estimate (OpenAI-style: ~4 chars per token)
        # Gemini may have different tokenization, but this is close enough
        estimated_tokens = char_count // 4

        return {
            'char_count': char_count,
            'word_count': word_count,
            'estimated_tokens': estimated_tokens
        }


def create_knowledge_card_prompt(
    title: str,
    author: str,
    content: str
) -> str:
    """
    Convenience function to create a knowledge card prompt.

    Args:
        title: Chunk title
        author: Chunk author
        content: Full chunk content

    Returns:
        Formatted prompt ready for Gemini 2.5 Flash-Lite API

    Example:
        >>> prompt = create_knowledge_card_prompt(
        ...     title="Deep Work",
        ...     author="Cal Newport",
        ...     content="The ability to perform deep work..."
        ... )
        >>> # Pass to Gemini API
    """
    pm = PromptManager()
    return pm.format_prompt(title, author, content)


# Constants for cost estimation (from Epic 2 PRD)
GEMINI_FLASH_LITE_INPUT_COST_PER_1M = 0.10  # $0.10 per 1M input tokens
GEMINI_FLASH_LITE_OUTPUT_COST_PER_1M = 0.40  # $0.40 per 1M output tokens

# Estimated tokens per chunk (from story dev notes)
ESTIMATED_INPUT_TOKENS_PER_CHUNK = 500  # Prompt + chunk content
ESTIMATED_OUTPUT_TOKENS_PER_CHUNK = 150  # Summary + takeaways + tags


def estimate_cost(num_chunks: int) -> Dict[str, float]:
    """
    Estimate cost for generating knowledge cards.

    Args:
        num_chunks: Number of chunks to process

    Returns:
        Dictionary with cost breakdown:
        - input_cost: Cost for input tokens
        - output_cost: Cost for output tokens
        - total_cost: Total cost
        - cost_per_chunk: Average cost per chunk

    Example:
        >>> estimate_cost(813)  # For full corpus
        {
            'input_cost': 0.041,
            'output_cost': 0.049,
            'total_cost': 0.09,
            'cost_per_chunk': 0.00011
        }
    """
    # Calculate token totals
    total_input_tokens = num_chunks * ESTIMATED_INPUT_TOKENS_PER_CHUNK
    total_output_tokens = num_chunks * ESTIMATED_OUTPUT_TOKENS_PER_CHUNK

    # Calculate costs
    input_cost = (total_input_tokens / 1_000_000) * GEMINI_FLASH_LITE_INPUT_COST_PER_1M
    output_cost = (total_output_tokens / 1_000_000) * GEMINI_FLASH_LITE_OUTPUT_COST_PER_1M
    total_cost = input_cost + output_cost

    return {
        'input_cost': input_cost,
        'output_cost': output_cost,
        'total_cost': total_cost,
        'cost_per_chunk': total_cost / num_chunks if num_chunks > 0 else 0.0
    }
