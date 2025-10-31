"""
Query embedding generation using Vertex AI gemini-embedding-001.

Reuses the same embedding model and configuration as the document pipeline
to ensure semantic consistency (768 dimensions).
"""

import os
import time
import logging
from typing import List
from google.cloud import aiplatform
from vertexai.preview.language_models import TextEmbeddingModel
from google.api_core.exceptions import ResourceExhausted, InternalServerError

logger = logging.getLogger(__name__)

# Global Vertex AI model (lazy initialization)
_vertex_ai_model = None

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds
MAX_BACKOFF = 32  # seconds


def get_embedding_model() -> TextEmbeddingModel:
    """
    Get or create Vertex AI embedding model instance (cached).

    Returns:
        Initialized TextEmbeddingModel
    """
    global _vertex_ai_model

    if _vertex_ai_model is None:
        project = os.getenv('GCP_PROJECT')
        region = os.getenv('GCP_REGION')

        logger.info(f"Initializing Vertex AI in project={project}, region={region}")

        # Initialize Vertex AI
        aiplatform.init(project=project, location=region)

        # Load embedding model
        logger.info("Loading gemini-embedding-001 model...")
        _vertex_ai_model = TextEmbeddingModel.from_pretrained("gemini-embedding-001")
        logger.info("Embedding model loaded successfully")

    return _vertex_ai_model


def generate_query_embedding(text: str) -> List[float]:
    """
    Generate 768-dimensional embedding for query text.

    Uses the same gemini-embedding-001 model and dimensionality as
    the document embedding pipeline to ensure semantic consistency.

    Args:
        text: Query text to embed

    Returns:
        768-dimensional embedding vector

    Raises:
        Exception: If embedding generation fails after retries
    """
    model = get_embedding_model()

    backoff = INITIAL_BACKOFF

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Generating embedding for query (attempt {attempt + 1}/{MAX_RETRIES})")

            # Use output_dimensionality=768 to match document embeddings
            # (gemini-embedding-001 defaults to 3072 dimensions)
            embeddings = model.get_embeddings([text], output_dimensionality=768)
            embedding_vector = embeddings[0].values

            logger.info(f"Generated embedding with {len(embedding_vector)} dimensions")
            return list(embedding_vector)  # Convert to list of floats

        except ResourceExhausted as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    f"Rate limit exceeded (attempt {attempt + 1}/{MAX_RETRIES}), "
                    f"retrying after {backoff}s"
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
            else:
                logger.error(f"Rate limit exceeded after {MAX_RETRIES} attempts")
                raise Exception(f"Rate limit exceeded: {e}") from e

        except InternalServerError as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    f"Server error (attempt {attempt + 1}/{MAX_RETRIES}), "
                    f"retrying after {backoff}s"
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
            else:
                logger.error(f"Server error after {MAX_RETRIES} attempts")
                raise Exception(f"Server error: {e}") from e

        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {e}")
            raise Exception(f"Embedding generation failed: {e}") from e

    # Should never reach here
    raise Exception("Failed to generate embedding after maximum retries")
