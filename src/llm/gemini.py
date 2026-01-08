"""
Gemini LLM Client Implementation

Uses Vertex AI SDK for Gemini models.
"""

import logging
import time
from typing import Optional

from .base import BaseLLMClient, GenerationConfig, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 30.0


# Models that require global endpoint (preview models)
GLOBAL_ONLY_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
]


class GeminiClient(BaseLLMClient):
    """
    Gemini client using Vertex AI SDK.

    Supports all Gemini models available on Vertex AI.
    Note: Preview models (gemini-3-*) require global endpoint.
    """

    def __init__(
        self,
        model_id: str = "gemini-2.5-flash",
        project_id: str = None,
        region: str = "europe-west4",
    ):
        """
        Initialize Gemini client.

        Args:
            model_id: Gemini model ID (e.g., "gemini-2.5-flash", "gemini-3-flash-preview")
            project_id: GCP project ID (uses GCP_PROJECT env var if None)
            region: GCP region (uses GCP_REGION env var if None, or "global" for preview models)
        """
        import os

        project_id = project_id or os.environ.get("GCP_PROJECT", "kx-hub")
        region = region or os.environ.get("GCP_REGION", "europe-west4")

        # Force global region for preview models
        if model_id in GLOBAL_ONLY_MODELS:
            region = "global"

        super().__init__(model_id, project_id, region)
        self._model = None

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.GEMINI

    def _initialize(self) -> None:
        """Initialize Vertex AI and load model."""
        from google.cloud import aiplatform
        from vertexai.generative_models import GenerativeModel

        logger.info(
            f"Initializing Gemini: model={self.model_id}, project={self.project_id}, region={self.region}"
        )

        aiplatform.init(project=self.project_id, location=self.region)
        self._model = GenerativeModel(self.model_id)

        logger.info(f"Gemini model initialized: {self.model_id}")

    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """
        Generate text using Gemini.

        Args:
            prompt: User prompt
            config: Generation configuration
            system_prompt: Optional system instruction

        Returns:
            LLMResponse with generated text
        """
        self._ensure_initialized()

        from vertexai.generative_models import HarmBlockThreshold, HarmCategory

        config = config or GenerationConfig()

        # Convert to Gemini config as dict to support thinking_config
        gemini_config = {
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
            "top_p": config.top_p,
            "top_k": config.top_k,
            "candidate_count": 1,
        }

        # Thinking mode: disabled by default to avoid $3.50/1M token costs
        # Enable explicitly via config.enable_thinking=True for complex reasoning
        # Note: Only gemini-3-flash supports thinking_budget=0, Pro models don't
        if not config.enable_thinking and "flash" in self.model_id.lower():
            gemini_config["thinking_config"] = {"thinking_budget": 0}

        # Safety settings - permissive for content generation
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        }

        # Build content
        contents = []
        if system_prompt:
            # Gemini uses system instruction differently - prepend to prompt
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt

        backoff = INITIAL_BACKOFF

        for attempt in range(MAX_RETRIES):
            try:
                response = self._model.generate_content(
                    full_prompt,
                    generation_config=gemini_config,
                    safety_settings=safety_settings,
                )

                # Extract text from response
                if not response.candidates or len(response.candidates) == 0:
                    raise ValueError("No response candidates from Gemini API")

                candidate = response.candidates[0]
                finish_reason = getattr(candidate, "finish_reason", None)

                if not candidate.content or not candidate.content.parts:
                    raise ValueError(
                        f"Empty response from Gemini. Finish reason: {finish_reason}"
                    )

                text = "".join(
                    [
                        part.text
                        for part in candidate.content.parts
                        if hasattr(part, "text")
                    ]
                )

                if not text.strip():
                    raise ValueError("Empty text from Gemini API")

                # Extract usage if available
                usage_metadata = getattr(response, "usage_metadata", None)
                input_tokens = (
                    getattr(usage_metadata, "prompt_token_count", None)
                    if usage_metadata
                    else None
                )
                output_tokens = (
                    getattr(usage_metadata, "candidates_token_count", None)
                    if usage_metadata
                    else None
                )

                return LLMResponse(
                    text=text,
                    model=self.model_id,
                    provider=self.provider,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    finish_reason=str(finish_reason) if finish_reason else None,
                    raw_response=response,
                )

            except Exception as e:
                error_msg = str(e).lower()
                is_retriable = any(
                    x in error_msg
                    for x in ["rate", "quota", "429", "internal", "500", "503"]
                )

                if is_retriable and attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Retriable error (attempt {attempt + 1}/{MAX_RETRIES}): {e}. Retrying after {backoff}s"
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                else:
                    logger.error(
                        f"Gemini generation failed after {attempt + 1} attempts: {e}"
                    )
                    raise
