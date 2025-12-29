"""
Claude LLM Client Implementation

Uses Anthropic SDK with Vertex AI backend.
"""

import logging
import time
from typing import Optional

from .base import BaseLLMClient, LLMProvider, GenerationConfig, LLMResponse

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 30.0


class ClaudeClient(BaseLLMClient):
    """
    Claude client using Anthropic SDK with Vertex AI.

    Supports all Claude models available on Vertex AI.
    Requires: pip install anthropic[vertex]
    """

    def __init__(
        self,
        model_id: str = "claude-haiku-4-5@20251001",
        project_id: str = None,
        region: str = "us-east5"  # Claude default region
    ):
        """
        Initialize Claude client.

        Args:
            model_id: Claude model ID (e.g., "claude-haiku-4-5@20251001")
            project_id: GCP project ID (uses GCP_PROJECT env var if None)
            region: GCP region for Claude (us-east5 recommended)
        """
        import os
        project_id = project_id or os.environ.get('GCP_PROJECT', 'kx-hub')
        region = region or os.environ.get('CLAUDE_REGION', 'us-east5')

        super().__init__(model_id, project_id, region)
        self._client = None

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.CLAUDE

    def _initialize(self) -> None:
        """Initialize Anthropic Vertex AI client."""
        try:
            from anthropic import AnthropicVertex
        except ImportError:
            raise ImportError(
                "anthropic[vertex] library required for Claude. "
                "Install with: pip install 'anthropic[vertex]'"
            )

        logger.info(f"Initializing Claude: model={self.model_id}, project={self.project_id}, region={self.region}")

        self._client = AnthropicVertex(
            project_id=self.project_id,
            region=self.region
        )

        logger.info(f"Claude client initialized: {self.model_id}")

    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """
        Generate text using Claude.

        Args:
            prompt: User prompt
            config: Generation configuration
            system_prompt: Optional system prompt

        Returns:
            LLMResponse with generated text
        """
        self._ensure_initialized()

        config = config or GenerationConfig()

        # Build messages
        messages = [{"role": "user", "content": prompt}]

        backoff = INITIAL_BACKOFF

        for attempt in range(MAX_RETRIES):
            try:
                # Build API call kwargs
                kwargs = {
                    "model": self.model_id,
                    "max_tokens": config.max_output_tokens,
                    "messages": messages,
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                }

                # Add system prompt if provided
                if system_prompt:
                    kwargs["system"] = system_prompt

                # Add top_k if supported (Claude specific)
                if config.top_k:
                    kwargs["top_k"] = config.top_k

                response = self._client.messages.create(**kwargs)

                # Extract text from response
                if not response.content or len(response.content) == 0:
                    raise ValueError("No content in Claude response")

                # Claude returns content blocks, concatenate text blocks
                text_parts = []
                for block in response.content:
                    if hasattr(block, 'text'):
                        text_parts.append(block.text)

                text = ''.join(text_parts)

                if not text.strip():
                    raise ValueError("Empty text from Claude API")

                return LLMResponse(
                    text=text,
                    model=self.model_id,
                    provider=self.provider,
                    input_tokens=response.usage.input_tokens if response.usage else None,
                    output_tokens=response.usage.output_tokens if response.usage else None,
                    finish_reason=response.stop_reason,
                    raw_response=response
                )

            except Exception as e:
                error_msg = str(e).lower()
                is_retriable = any(x in error_msg for x in ['rate', 'overloaded', '429', '500', '503', 'timeout'])

                if is_retriable and attempt < MAX_RETRIES - 1:
                    logger.warning(f"Retriable error (attempt {attempt + 1}/{MAX_RETRIES}): {e}. Retrying after {backoff}s")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                else:
                    logger.error(f"Claude generation failed after {attempt + 1} attempts: {e}")
                    raise
