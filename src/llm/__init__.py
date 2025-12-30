"""
LLM Provider Abstraction Layer

Unified interface for multiple LLM providers (Gemini, Claude).
Enables easy model switching and A/B testing.

Usage:
    # Simple - uses default model (from LLM_MODEL env var or gemini-2.5-flash)
    from llm import get_client
    client = get_client()
    response = client.generate("Summarize this text...")

    # Explicit model selection
    client = get_client("claude-haiku")  # or "gemini-3", "sonnet", etc.

    # JSON generation with automatic parsing
    data = client.generate_json("Return JSON with keys: summary, tags")

    # List available models
    from llm import list_models
    for name, info in list_models().items():
        print(f"{name}: {info.description}")

Environment Variables:
    LLM_MODEL: Default model to use (e.g., "gemini-2.5-flash", "claude-haiku")
    LLM_PROVIDER: Provider preference ("gemini" or "claude")
    GCP_PROJECT: GCP project ID
    GCP_REGION: GCP region for Gemini
    CLAUDE_REGION: GCP region for Claude (default: europe-west1)
"""

import logging
from typing import Dict, Optional

from .base import BaseLLMClient, GenerationConfig, LLMProvider, LLMResponse
from .config import (
    MODEL_ALIASES,
    MODEL_REGISTRY,
    ModelInfo,
    get_default_model,
    get_gcp_config,
    get_model_info,
    list_available_models,
    resolve_model_name,
)

logger = logging.getLogger(__name__)

# Client cache for reuse
_client_cache: Dict[str, BaseLLMClient] = {}


def get_client(
    model: Optional[str] = None,
    project_id: Optional[str] = None,
    region: Optional[str] = None,
    cache: bool = True,
) -> BaseLLMClient:
    """
    Get an LLM client for the specified model.

    Args:
        model: Model name or alias (e.g., "gemini-2.5-flash", "claude-haiku", "haiku")
               Uses LLM_MODEL env var or default if None.
        project_id: GCP project ID (uses GCP_PROJECT env var if None)
        region: GCP region (auto-selected based on provider if None)
        cache: Whether to cache and reuse client instances (default: True)

    Returns:
        Configured LLM client

    Raises:
        ValueError: If model is not supported
        ImportError: If required dependencies are missing

    Example:
        >>> client = get_client("claude-haiku")
        >>> response = client.generate("Hello!")
        >>> print(response.text)
    """
    # Resolve model name
    model_name = resolve_model_name(model) if model else get_default_model()

    # Check cache
    cache_key = f"{model_name}:{project_id}:{region}"
    if cache and cache_key in _client_cache:
        return _client_cache[cache_key]

    # Get model info
    model_info = get_model_info(model_name)
    if not model_info:
        available = ", ".join(list(MODEL_REGISTRY.keys()) + list(MODEL_ALIASES.keys()))
        raise ValueError(f"Unknown model: {model_name}. Available: {available}")

    # Get GCP config
    default_project, default_region = get_gcp_config()
    project_id = project_id or default_project

    # Create appropriate client
    if model_info.provider == LLMProvider.GEMINI:
        from .gemini import GeminiClient

        region = region or default_region
        client = GeminiClient(
            model_id=model_info.model_id, project_id=project_id, region=region
        )
    elif model_info.provider == LLMProvider.CLAUDE:
        # Claude has different region requirements
        import os

        from .claude import ClaudeClient

        region = region or os.environ.get("CLAUDE_REGION", "europe-west1")
        client = ClaudeClient(
            model_id=model_info.model_id, project_id=project_id, region=region
        )
    else:
        raise ValueError(f"Unsupported provider: {model_info.provider}")

    # Cache client
    if cache:
        _client_cache[cache_key] = client

    logger.info(f"Created LLM client: {client}")
    return client


def list_models() -> Dict[str, ModelInfo]:
    """
    List all available models.

    Returns:
        Dictionary of model name -> ModelInfo
    """
    return list_available_models()


def clear_cache() -> None:
    """Clear the client cache."""
    global _client_cache
    _client_cache.clear()
    logger.info("LLM client cache cleared")


# Convenience exports
__all__ = [
    # Main factory
    "get_client",
    # Types
    "BaseLLMClient",
    "LLMProvider",
    "GenerationConfig",
    "LLMResponse",
    "ModelInfo",
    # Config utilities
    "list_models",
    "get_model_info",
    "get_default_model",
    "clear_cache",
]
