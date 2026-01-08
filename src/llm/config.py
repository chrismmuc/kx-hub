"""
LLM Configuration and Model Registry

Defines available models and their configurations.
Model selection via DEFAULT_MODEL or environment variables.
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

from .base import LLMProvider

logger = logging.getLogger(__name__)

# =============================================================================
# GLOBAL MODEL CONFIGURATION
# =============================================================================
# Set the default LLM model here. This is used for all text generation tasks
# (knowledge cards, cluster metadata, recommendations).
#
# NOTE: Embeddings always use gemini-embedding-001 regardless of this setting.
#
# Available models:
#   Gemini:  "gemini-2.5-flash", "gemini-2.0-flash-001", "gemini-3-flash-preview"
#   Claude:  "claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-5"
#
# Can be overridden by LLM_MODEL environment variable.
# =============================================================================
# DEFAULT_MODEL = "gemini-3-flash-preview"  # Neuestes Gemini
# DEFAULT_MODEL = "gemini-2.5-flash"  # Cost-effective default
# DEFAULT_MODEL = "sonnet"                   # Alias für claude-sonnet-4-5
DEFAULT_MODEL = "gemini-2.5-flash"


@dataclass
class ModelInfo:
    """Information about a specific model."""

    model_id: str
    provider: LLMProvider
    description: str
    input_cost_per_1m: float  # USD per 1M input tokens
    output_cost_per_1m: float  # USD per 1M output tokens
    max_context: int  # Max context window
    max_output: int  # Max output tokens
    regions: list  # Supported regions (empty = global only)


# Model Registry - All available models
MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # Gemini Models
    "gemini-2.5-flash": ModelInfo(
        model_id="gemini-2.5-flash",
        provider=LLMProvider.GEMINI,
        description="Gemini 2.5 Flash - Balanced speed/quality (GA)",
        input_cost_per_1m=0.075,
        output_cost_per_1m=0.30,
        max_context=1_000_000,
        max_output=8192,
        regions=["europe-west4", "us-central1", "asia-northeast1"],
    ),
    "gemini-2.0-flash-001": ModelInfo(
        model_id="gemini-2.0-flash-001",
        provider=LLMProvider.GEMINI,
        description="Gemini 2.0 Flash - Legacy, cost-effective",
        input_cost_per_1m=0.075,
        output_cost_per_1m=0.30,
        max_context=1_000_000,
        max_output=8192,
        regions=["europe-west4", "us-central1"],
    ),
    "gemini-3-flash-preview": ModelInfo(
        model_id="gemini-3-flash-preview",
        provider=LLMProvider.GEMINI,
        description="Gemini 3 Flash - Latest preview, best coding",
        input_cost_per_1m=0.50,
        output_cost_per_1m=3.00,
        max_context=1_000_000,
        max_output=65536,
        regions=[],  # Global only (preview)
    ),
    "gemini-3-pro-preview": ModelInfo(
        model_id="gemini-3-pro-preview",
        provider=LLMProvider.GEMINI,
        description="Gemini 3 Pro - Most capable reasoning model",
        input_cost_per_1m=2.00,
        output_cost_per_1m=12.00,
        max_context=1_000_000,
        max_output=65536,
        regions=[],  # Global only (preview)
    ),
    # Claude Models (via Vertex AI)
    "claude-3-5-haiku": ModelInfo(
        model_id="claude-3-5-haiku@20241022",
        provider=LLMProvider.CLAUDE,
        description="Claude 3.5 Haiku - Fast, cost-effective",
        input_cost_per_1m=0.80,
        output_cost_per_1m=4.00,
        max_context=200_000,
        max_output=8192,
        regions=["us-east5", "europe-west1"],
    ),
    "claude-haiku-4-5": ModelInfo(
        model_id="claude-haiku-4-5@20251001",
        provider=LLMProvider.CLAUDE,
        description="Claude Haiku 4.5 - Fast, cost-effective, GA",
        input_cost_per_1m=1.00,
        output_cost_per_1m=5.00,
        max_context=200_000,
        max_output=8192,
        regions=["us-east5", "europe-west1"],
    ),
    "claude-sonnet-4-5": ModelInfo(
        model_id="claude-sonnet-4-5@20250929",
        provider=LLMProvider.CLAUDE,
        description="Claude Sonnet 4.5 - Balanced performance",
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
        max_context=200_000,
        max_output=8192,
        regions=["us-east5", "europe-west1"],
    ),
    "claude-opus-4-5": ModelInfo(
        model_id="claude-opus-4-5@20251101",
        provider=LLMProvider.CLAUDE,
        description="Claude Opus 4.5 - Most capable",
        input_cost_per_1m=15.00,
        output_cost_per_1m=75.00,
        max_context=200_000,
        max_output=8192,
        regions=["us-east5"],
    ),
}

# Aliases for convenience
MODEL_ALIASES: Dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "gemini-flash": "gemini-2.5-flash",
    "gemini-3": "gemini-3-flash-preview",
    "gemini-3-pro": "gemini-3-pro-preview",
    "claude": "claude-haiku-4-5",
    "claude-haiku": "claude-haiku-4-5",
    "claude-sonnet": "claude-sonnet-4-5",
    "claude-opus": "claude-opus-4-5",
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-5",
    "opus": "claude-opus-4-5",
}


def resolve_model_name(name: str) -> str:
    """
    Resolve model name from alias or return as-is.

    Args:
        name: Model name or alias

    Returns:
        Resolved model name
    """
    return MODEL_ALIASES.get(name.lower(), name)


def get_model_info(name: str) -> Optional[ModelInfo]:
    """
    Get model info by name or alias.

    Args:
        name: Model name or alias

    Returns:
        ModelInfo or None if not found
    """
    resolved = resolve_model_name(name)
    return MODEL_REGISTRY.get(resolved)


def get_default_model() -> str:
    """
    Get default model from environment or config.

    Priority (highest to lowest):
        1. LLM_MODEL environment variable
        2. LLM_PROVIDER environment variable (gemini/claude)
        3. DEFAULT_MODEL constant in this file

    Returns:
        Model name to use
    """
    # Check explicit model setting from environment
    model = os.environ.get("LLM_MODEL")
    if model:
        resolved = resolve_model_name(model)
        if resolved in MODEL_REGISTRY:
            logger.info(f"Using model from LLM_MODEL: {resolved}")
            return resolved
        logger.warning(f"Unknown model '{model}', falling back to default")

    # Check provider preference from environment
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    if provider == "claude":
        logger.info("Using Claude (from LLM_PROVIDER)")
        return "claude-haiku-4-5"
    elif provider == "gemini":
        logger.info("Using Gemini (from LLM_PROVIDER)")
        return "gemini-2.5-flash"

    # Use configured default from this file
    resolved_default = resolve_model_name(DEFAULT_MODEL)
    if resolved_default in MODEL_REGISTRY:
        logger.info(f"Using default model: {resolved_default}")
        return resolved_default

    # Ultimate fallback
    logger.warning(f"Invalid DEFAULT_MODEL '{DEFAULT_MODEL}', using gemini-2.5-flash")
    return "gemini-2.5-flash"


def list_available_models() -> Dict[str, ModelInfo]:
    """Return all available models."""
    return MODEL_REGISTRY.copy()


def get_gcp_config() -> tuple[str, str]:
    """
    Get GCP project and region from environment.

    Returns:
        Tuple of (project_id, region)
    """
    project = os.environ.get("GCP_PROJECT", "kx-hub")
    region = os.environ.get("GCP_REGION", "europe-west4")
    return project, region
