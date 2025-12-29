"""
Gemini LLM Client Implementation

Uses Google Gen AI SDK for Gemini models via Vertex AI.
Migrated from deprecated vertexai.generative_models (deprecated June 2025).
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


class GeminiClient(BaseLLMClient):
    """
    Gemini client using Google Gen AI SDK.

    Supports all Gemini models available on Vertex AI.
    """

    def __init__(
        self,
        model_id: str = "gemini-2.5-flash",
        project_id: str = None,
        region: str = "europe-west4"
    ):
        """
        Initialize Gemini client.

        Args:
            model_id: Gemini model ID (e.g., "gemini-2.5-flash", "gemini-2.5-pro")
            project_id: GCP project ID (uses GCP_PROJECT env var if None)
            region: GCP region (uses GCP_REGION env var if None)
        """
        import os
        project_id = project_id or os.environ.get('GCP_PROJECT', 'kx-hub')
        region = region or os.environ.get('GCP_REGION', 'europe-west4')

        super().__init__(model_id, project_id, region)
        self._client = None

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.GEMINI

    def _initialize(self) -> None:
        """Initialize Google Gen AI client for Vertex AI."""
        from google import genai

        logger.info(f"Initializing Gemini: model={self.model_id}, project={self.project_id}, region={self.region}")

        self._client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.region
        )

        logger.info(f"Gemini client initialized: {self.model_id}")

    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        system_prompt: Optional[str] = None
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

        from google.genai import types

        config = config or GenerationConfig()

        # Build generation config
        gen_config = types.GenerateContentConfig(
            temperature=config.temperature,
            max_output_tokens=config.max_output_tokens,
            top_p=config.top_p,
            top_k=config.top_k,
            # Safety settings - permissive for content generation
            safety_settings=[
                types.SafetySetting(
                    category='HARM_CATEGORY_HATE_SPEECH',
                    threshold='OFF',
                ),
                types.SafetySetting(
                    category='HARM_CATEGORY_DANGEROUS_CONTENT',
                    threshold='OFF',
                ),
                types.SafetySetting(
                    category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
                    threshold='OFF',
                ),
                types.SafetySetting(
                    category='HARM_CATEGORY_HARASSMENT',
                    threshold='OFF',
                ),
            ]
        )

        # Add system instruction if provided
        if system_prompt:
            gen_config.system_instruction = system_prompt

        backoff = INITIAL_BACKOFF

        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=gen_config
                )

                # Extract text from response
                text = response.text

                if not text or not text.strip():
                    # Check for blocked content
                    if response.candidates:
                        candidate = response.candidates[0]
                        finish_reason = getattr(candidate, 'finish_reason', None)
                        raise ValueError(f"Empty response from Gemini. Finish reason: {finish_reason}")
                    raise ValueError("Empty response from Gemini API")

                # Extract usage metadata
                usage = getattr(response, 'usage_metadata', None)
                input_tokens = getattr(usage, 'prompt_token_count', None) if usage else None
                output_tokens = getattr(usage, 'candidates_token_count', None) if usage else None

                # Get finish reason
                finish_reason = None
                if response.candidates:
                    finish_reason = getattr(response.candidates[0], 'finish_reason', None)

                return LLMResponse(
                    text=text,
                    model=self.model_id,
                    provider=self.provider,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    finish_reason=str(finish_reason) if finish_reason else None,
                    raw_response=response
                )

            except Exception as e:
                error_msg = str(e).lower()
                is_retriable = any(x in error_msg for x in ['rate', 'quota', '429', 'internal', '500', '503'])

                if is_retriable and attempt < MAX_RETRIES - 1:
                    logger.warning(f"Retriable error (attempt {attempt + 1}/{MAX_RETRIES}): {e}. Retrying after {backoff}s")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                else:
                    logger.error(f"Gemini generation failed after {attempt + 1} attempts: {e}")
                    raise
