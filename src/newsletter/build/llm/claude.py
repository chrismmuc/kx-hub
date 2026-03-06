"""
Claude LLM Client Implementation

Supports both:
- Direct Anthropic API (CLAUDE_BACKEND=anthropic)
- Vertex AI backend (CLAUDE_BACKEND=vertex, default)

Configuration:
    CLAUDE_BACKEND: "anthropic" or "vertex" (default: vertex)
    ANTHROPIC_API_KEY: Required for direct API (can be in Secret Manager)
    CLAUDE_REGION: GCP region for Vertex AI (default: europe-west1)
"""

import logging
import os
import time
from typing import Optional

from .base import BaseLLMClient, GenerationConfig, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 30.0

# Backend options
BACKEND_VERTEX = "vertex"
BACKEND_ANTHROPIC = "anthropic"


def get_anthropic_api_key() -> Optional[str]:
    """
    Get Anthropic API key from environment or Secret Manager.

    Priority:
        1. ANTHROPIC_API_KEY environment variable
        2. Google Cloud Secret Manager (ANTHROPIC_API_KEY secret)

    Returns:
        API key string or None if not found
    """
    # Check environment first
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        logger.debug("Using ANTHROPIC_API_KEY from environment")
        return api_key

    # Try Secret Manager
    try:
        from google.cloud import secretmanager

        project = os.environ.get("GCP_PROJECT", "kx-hub")
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project}/secrets/ANTHROPIC_API_KEY/versions/latest"

        response = client.access_secret_version(request={"name": name})
        api_key = response.payload.data.decode("UTF-8")
        logger.debug("Using ANTHROPIC_API_KEY from Secret Manager")
        return api_key
    except Exception as e:
        logger.debug(f"Could not get API key from Secret Manager: {e}")
        return None


class ClaudeClient(BaseLLMClient):
    """
    Claude client supporting both direct Anthropic API and Vertex AI.

    Backend selection via CLAUDE_BACKEND environment variable:
        - "anthropic": Direct Anthropic API (requires ANTHROPIC_API_KEY)
        - "vertex": Google Vertex AI (default, requires GCP auth)

    Requires: pip install anthropic[vertex]
    """

    def __init__(
        self,
        model_id: str = "claude-haiku-4-5@20251001",
        project_id: str = None,
        region: str = "europe-west1",
        backend: str = None,
    ):
        """
        Initialize Claude client.

        Args:
            model_id: Claude model ID (e.g., "claude-haiku-4-5@20251001")
            project_id: GCP project ID (uses GCP_PROJECT env var if None)
            region: GCP region for Vertex AI (europe-west1 for EU)
            backend: "anthropic" or "vertex" (uses CLAUDE_BACKEND env var if None)
        """
        project_id = project_id or os.environ.get("GCP_PROJECT", "kx-hub")
        region = region or os.environ.get("CLAUDE_REGION", "europe-west1")

        # Determine backend
        self._backend = (
            backend or os.environ.get("CLAUDE_BACKEND", BACKEND_VERTEX).lower()
        )
        if self._backend not in (BACKEND_VERTEX, BACKEND_ANTHROPIC):
            logger.warning(f"Unknown backend '{self._backend}', falling back to vertex")
            self._backend = BACKEND_VERTEX

        super().__init__(model_id, project_id, region)
        self._client = None

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.CLAUDE

    @property
    def backend(self) -> str:
        """Return the active backend (anthropic or vertex)."""
        return self._backend

    def _get_model_id_for_api(self) -> str:
        """
        Get the appropriate model ID for the current backend.

        Vertex AI uses versioned IDs like "claude-haiku-4-5@20251001"
        Direct API uses simple IDs like "claude-3-5-haiku-20241022"
        """
        if self._backend == BACKEND_ANTHROPIC:
            # Convert Vertex format to Anthropic API format
            model_mapping = {
                "claude-haiku-4-5@20251001": "claude-3-5-haiku-20241022",
                "claude-sonnet-4-5@20250929": "claude-sonnet-4-20250514",
                "claude-opus-4-5@20251101": "claude-opus-4-20250514",
                "claude-3-5-haiku@20241022": "claude-3-5-haiku-20241022",
            }
            return model_mapping.get(self.model_id, self.model_id)
        return self.model_id

    def _initialize(self) -> None:
        """Initialize Anthropic client (direct or Vertex AI)."""
        if self._backend == BACKEND_ANTHROPIC:
            self._initialize_anthropic()
        else:
            self._initialize_vertex()

    def _initialize_anthropic(self) -> None:
        """Initialize direct Anthropic API client."""
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "anthropic library required for Claude. "
                "Install with: pip install anthropic"
            )

        api_key = get_anthropic_api_key()
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Set environment variable or "
                "create secret in Google Cloud Secret Manager."
            )

        logger.info(f"Initializing Claude (direct API): model={self.model_id}")
        self._client = Anthropic(api_key=api_key)
        logger.info(f"Claude client initialized (anthropic): {self.model_id}")

    def _initialize_vertex(self) -> None:
        """Initialize Anthropic Vertex AI client."""
        try:
            from anthropic import AnthropicVertex
        except ImportError:
            raise ImportError(
                "anthropic[vertex] library required for Claude on Vertex AI. "
                "Install with: pip install 'anthropic[vertex]'"
            )

        logger.info(
            f"Initializing Claude (Vertex AI): model={self.model_id}, "
            f"project={self.project_id}, region={self.region}"
        )

        self._client = AnthropicVertex(project_id=self.project_id, region=self.region)
        logger.info(f"Claude client initialized (vertex): {self.model_id}")

    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
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
        model_id = self._get_model_id_for_api()

        # Build messages
        messages = [{"role": "user", "content": prompt}]

        backoff = INITIAL_BACKOFF

        for attempt in range(MAX_RETRIES):
            try:
                # Build API call kwargs
                kwargs = {
                    "model": model_id,
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
                    if hasattr(block, "text"):
                        text_parts.append(block.text)

                text = "".join(text_parts)

                if not text.strip():
                    raise ValueError("Empty text from Claude API")

                return LLMResponse(
                    text=text,
                    model=self.model_id,
                    provider=self.provider,
                    input_tokens=response.usage.input_tokens
                    if response.usage
                    else None,
                    output_tokens=response.usage.output_tokens
                    if response.usage
                    else None,
                    finish_reason=response.stop_reason,
                    raw_response=response,
                )

            except Exception as e:
                error_msg = str(e).lower()
                is_retriable = any(
                    x in error_msg
                    for x in ["rate", "overloaded", "429", "500", "503", "timeout"]
                )

                if is_retriable and attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Retriable error (attempt {attempt + 1}/{MAX_RETRIES}): {e}. "
                        f"Retrying after {backoff}s"
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                else:
                    logger.error(
                        f"Claude generation failed after {attempt + 1} attempts: {e}"
                    )
                    raise
