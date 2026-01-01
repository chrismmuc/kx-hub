"""
Prompt Manager for Relationship Extraction

Handles loading and formatting LLM prompts for relationship extraction.
Epic 4, Story 4.1
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Manages prompts for relationship extraction.

    Handles:
    - Loading prompt templates from files
    - Formatting prompts with chunk data
    - Caching loaded templates
    """

    def __init__(self, prompt_dir: Optional[str] = None):
        """
        Initialize prompt manager.

        Args:
            prompt_dir: Directory containing prompt files (defaults to package prompts/)
        """
        if prompt_dir is None:
            self.prompt_dir = Path(__file__).parent / "prompts"
        else:
            self.prompt_dir = Path(prompt_dir)

        self._prompt_cache: Dict[str, str] = {}

    def load_prompt(self, prompt_name: str = "relationship_prompt.txt") -> str:
        """
        Load prompt template from file.

        Args:
            prompt_name: Name of prompt file

        Returns:
            Prompt template string

        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        if prompt_name in self._prompt_cache:
            return self._prompt_cache[prompt_name]

        prompt_path = self.prompt_dir / prompt_name

        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {prompt_path}. "
                f"Available prompts: {list(self.prompt_dir.glob('*.txt'))}"
            )

        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        self._prompt_cache[prompt_name] = prompt_template
        return prompt_template

    def format_prompt(
        self,
        source_title: str,
        source_summary: str,
        target_title: str,
        target_summary: str,
        prompt_template: Optional[str] = None,
    ) -> str:
        """
        Format prompt template with chunk data.

        Args:
            source_title: Title of source chunk
            source_summary: Summary of source chunk (from knowledge card)
            target_title: Title of target chunk
            target_summary: Summary of target chunk (from knowledge card)
            prompt_template: Optional custom template

        Returns:
            Formatted prompt ready for LLM API
        """
        if prompt_template is None:
            prompt_template = self.load_prompt()

        # Use replace() to avoid conflicts with JSON braces in template
        formatted = prompt_template.replace("{source_title}", source_title or "Unknown")
        formatted = formatted.replace("{source_summary}", source_summary or "")
        formatted = formatted.replace("{target_title}", target_title or "Unknown")
        formatted = formatted.replace("{target_summary}", target_summary or "")

        return formatted

    def get_prompt_stats(self, prompt: str) -> Dict[str, Any]:
        """
        Get statistics about a formatted prompt.

        Args:
            prompt: Formatted prompt string

        Returns:
            Dictionary with char_count, word_count, estimated_tokens
        """
        char_count = len(prompt)
        word_count = len(prompt.split())
        estimated_tokens = char_count // 4  # Rough estimate

        return {
            "char_count": char_count,
            "word_count": word_count,
            "estimated_tokens": estimated_tokens,
        }


def create_relationship_prompt(
    source_title: str,
    source_summary: str,
    target_title: str,
    target_summary: str,
) -> str:
    """
    Convenience function to create a relationship extraction prompt.

    Args:
        source_title: Title of source chunk
        source_summary: Summary of source chunk
        target_title: Title of target chunk
        target_summary: Summary of target chunk

    Returns:
        Formatted prompt ready for LLM API
    """
    pm = PromptManager()
    return pm.format_prompt(source_title, source_summary, target_title, target_summary)
