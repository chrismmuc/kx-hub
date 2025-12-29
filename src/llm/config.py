"""
LLM Configuration and Model Registry

Defines available models and their configurations.
Model selection via environment variables.
"""

import os
import logging
from dataclasses import dataclass
from typing import Dict, Optional
from .base import LLMProvider

logger = logging.getLogger(__name__)


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
        regions=["europe-west4", "us-central1", "asia-northeast1"]
    ),
    "gemini-2.0-flash-001": ModelInfo(
        model_id="gemini-2.0-flash-001",
        provider=LLMProvider.GEMINI,
        description="Gemini 2.0 Flash - Legacy, cost-effective",
        input_cost_per_1m=0.075,
        output_cost_per_1m=0.30,
        max_context=1_000_000,
        max_output=8192,
        regions=["europe-west4", "us-central1"]
    ),
    "gemini-3-flash-preview": ModelInfo(
        model_id="gemini-3-flash-preview",
        provider=LLMProvider.GEMINI,
        description="Gemini 3 Flash - Latest preview, best coding",
        input_cost_per_1m=0.50,
        output_cost_per_1m=3.00,
        max_context=1_000_000,
        max_output=65536,
        regions=[]  # Global only (preview)
    ),

    # Claude Models (via Vertex AI)
    "claude-haiku-4-5": ModelInfo(
        model_id="claude-haiku-4-5@20251001",
        provider=LLMProvider.CLAUDE,
        description="Claude Haiku 4.5 - Fast, cost-effective, GA",
        input_cost_per_1m=1.00,
        output_cost_per_1m=5.00,
        max_context=200_000,
        max_output=8192,
        regions=["us-east5", "europe-west1"]
    ),
    "claude-sonnet-4-5": ModelInfo(
        model_id="claude-sonnet-4-5@20250929",
        provider=LLMProvider.CLAUDE,
        description="Claude Sonnet 4.5 - Balanced performance",
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
        max_context=200_000,
        max_output=8192,
        regions=["us-east5", "europe-west1"]
    ),
    "claude-opus-4-5": ModelInfo(
        model_id="claude-opus-4-5@20251101",
        provider=LLMProvider.CLAUDE,
        description="Claude Opus 4.5 - Most capable",
        input_cost_per_1m=15.00,
        output_cost_per_1m=75.00,
        max_context=200_000,
        max_output=8192,
        regions=["us-east5"]
    ),
}

# Aliases for convenience
MODEL_ALIASES: Dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "gemini-flash": "gemini-2.5-flash",
    "gemini-3": "gemini-3-flash-preview",
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
    Get default model from environment or fallback.

    Environment variables:
        LLM_MODEL: Primary model selection
        LLM_PROVIDER: Provider preference (gemini/claude)

    Returns:
        Model name to use
    """
    # Check explicit model setting
    model = os.environ.get('LLM_MODEL')
    if model:
        resolved = resolve_model_name(model)
        if resolved in MODEL_REGISTRY:
            logger.info(f"Using model from LLM_MODEL: {resolved}")
            return resolved
        logger.warning(f"Unknown model '{model}', falling back to default")

    # Check provider preference
    provider = os.environ.get('LLM_PROVIDER', '').lower()
    if provider == 'claude':
        logger.info("Using Claude (from LLM_PROVIDER)")
        return "claude-haiku-4-5"

    # Default to Gemini
    logger.info("Using default model: gemini-2.5-flash")
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
    project = os.environ.get('GCP_PROJECT', 'kx-hub')
    region = os.environ.get('GCP_REGION', 'europe-west4')
    return project, region
