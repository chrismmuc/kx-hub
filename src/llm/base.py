"""
LLM Provider Abstraction Layer - Base Classes

Provides a unified interface for different LLM providers (Gemini, Claude, etc.)
to enable easy model switching and A/B testing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    CLAUDE = "claude"


@dataclass
class GenerationConfig:
    """
    Model-agnostic generation configuration.

    Maps to provider-specific configs internally.
    """
    temperature: float = 0.7
    max_output_tokens: int = 2048
    top_p: float = 0.95
    top_k: int = 40

    # Provider-specific overrides (optional)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """
    Unified response from any LLM provider.
    """
    text: str
    model: str
    provider: LLMProvider

    # Usage stats (if available)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    # Raw response for debugging
    raw_response: Optional[Any] = None

    # Finish reason
    finish_reason: Optional[str] = None


class BaseLLMClient(ABC):
    """
    Abstract base class for LLM clients.

    All provider implementations must inherit from this class.
    """

    def __init__(
        self,
        model_id: str,
        project_id: str,
        region: str = "europe-west4"
    ):
        """
        Initialize LLM client.

        Args:
            model_id: Model identifier (e.g., "gemini-2.5-flash", "claude-haiku-4-5@20251001")
            project_id: GCP project ID
            region: GCP region
        """
        self.model_id = model_id
        self.project_id = project_id
        self.region = region
        self._initialized = False

    @property
    @abstractmethod
    def provider(self) -> LLMProvider:
        """Return the provider type."""
        pass

    @abstractmethod
    def _initialize(self) -> None:
        """Initialize the underlying client. Called lazily on first use."""
        pass

    def _ensure_initialized(self) -> None:
        """Ensure client is initialized before use."""
        if not self._initialized:
            self._initialize()
            self._initialized = True

    @abstractmethod
    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """
        Generate text from a prompt.

        Args:
            prompt: User prompt
            config: Generation configuration (uses defaults if None)
            system_prompt: Optional system prompt (Claude) / system instruction (Gemini)

        Returns:
            LLMResponse with generated text and metadata
        """
        pass

    def generate_json(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate and parse JSON response.

        Handles markdown code block stripping automatically.

        Args:
            prompt: User prompt (should request JSON output)
            config: Generation configuration
            system_prompt: Optional system prompt

        Returns:
            Parsed JSON as dictionary

        Raises:
            ValueError: If response is not valid JSON
        """
        import json

        response = self.generate(prompt, config, system_prompt)
        text = response.text.strip()

        # Strip markdown code blocks if present
        if text.startswith('```'):
            # Remove opening fence
            text = text.split('\n', 1)[1] if '\n' in text else text[3:]
            # Remove closing fence
            if text.endswith('```'):
                text = text.rsplit('\n```', 1)[0]
            # Remove json language tag if present
            if text.startswith('json\n'):
                text = text[5:]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from {self.provider.value}: {text[:200]}") from e

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_id}, region={self.region})"
