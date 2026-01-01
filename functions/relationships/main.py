"""
Incremental Relationship Extraction Cloud Function

Story 4.5: When new chunks are ingested, find cross-source relationships.

Triggered after embedding step in daily pipeline.
For each new chunk, finds similar chunks from OTHER sources and
extracts relationships via LLM.

Environment Variables:
    GCP_PROJECT: Google Cloud project ID
    GCP_REGION: GCP region for Vertex AI
    SIMILARITY_THRESHOLD: Min similarity for pairs (default: 0.80)
    CONFIDENCE_THRESHOLD: Min LLM confidence (default: 0.7)
    MAX_SIMILAR_CHUNKS: Max similar chunks to check per new chunk (default: 10)
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import functions_framework
import numpy as np
from flask import Request
from google.cloud import firestore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
GCP_PROJECT = os.environ.get("GCP_PROJECT", "kx-hub")
GCP_REGION = os.environ.get("GCP_REGION", "europe-west4")
CHUNKS_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "kb_items")
RELATIONSHIPS_COLLECTION = "relationships"

SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.80"))
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))
MAX_SIMILAR_CHUNKS = int(os.environ.get("MAX_SIMILAR_CHUNKS", "10"))

# Valid relationship types
RELATIONSHIP_TYPES = [
    "relates_to",
    "extends",
    "supports",
    "contradicts",
    "applies_to",
    "none",
]

# Embedded prompt template
RELATIONSHIP_PROMPT = """Analyze the relationship between these two knowledge chunks from my personal knowledge base.

## Chunk A: {source_title}
{source_summary}

## Chunk B: {target_title}
{target_summary}

## Task
Determine if there is a meaningful semantic relationship between these chunks.

## Relationship Types
Choose ONE of these relationship types:
- **relates_to**: General thematic connection (similar topics, concepts, or domains)
- **extends**: Chunk B builds upon, develops, or evolves the ideas in Chunk A
- **supports**: Chunk B provides evidence, examples, or confirmation for Chunk A
- **contradicts**: Chunk B conflicts with, challenges, or presents an opposing view to Chunk A
- **applies_to**: Chunk B describes a practical application or implementation of concepts from Chunk A
- **none**: No meaningful relationship exists between these chunks

## Response Format
Return ONLY a JSON object with these fields:
- "type": One of the relationship types above
- "confidence": Your confidence in this relationship (0.0 to 1.0)
- "explanation": Brief explanation (1-2 sentences) of why this relationship exists

Example response:
{{"type": "extends", "confidence": 0.85, "explanation": "Chunk B elaborates on the productivity framework introduced in Chunk A with specific implementation strategies."}}

Important:
- Only identify relationships with confidence >= 0.5
- If no clear relationship exists, return type "none"
- Focus on conceptual/semantic relationships, not surface-level keyword matches
"""

# Global clients
_firestore_client = None
_vertex_model = None


def get_firestore_client() -> firestore.Client:
    """Get or create Firestore client."""
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT)
    return _firestore_client


def get_vertex_model():
    """Get or create Vertex AI model."""
    global _vertex_model
    if _vertex_model is None:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=GCP_PROJECT, location=GCP_REGION)
        _vertex_model = GenerativeModel("gemini-2.0-flash")
        logger.info("Initialized Vertex AI model: gemini-2.0-flash")
    return _vertex_model


@dataclass
class Relationship:
    """Represents a relationship between two chunks."""

    source_chunk_id: str
    target_chunk_id: str
    type: str
    confidence: float
    explanation: str
    source_context: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_chunk_id": self.source_chunk_id,
            "target_chunk_id": self.target_chunk_id,
            "type": self.type,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "source_context": self.source_context,
            "created_at": self.created_at,
        }


def get_chunk_by_id(db: firestore.Client, chunk_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single chunk by ID."""
    doc = db.collection(CHUNKS_COLLECTION).document(chunk_id).get()
    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return None


def compute_similarity(embedding_a: List[float], embedding_b: List[float]) -> float:
    """Compute cosine similarity between two embeddings."""
    a = np.array(embedding_a)
    b = np.array(embedding_b)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def find_similar_cross_source_chunks(
    db: firestore.Client,
    chunk: Dict[str, Any],
    limit: int = MAX_SIMILAR_CHUNKS,
) -> List[Dict[str, Any]]:
    """
    Find chunks from OTHER sources similar to the given chunk.
    Uses Firestore vector search to find nearest neighbors.
    """
    embedding = chunk.get("embedding")
    source_id = chunk.get("source_id")

    if not embedding or not source_id:
        logger.warning(f"Chunk {chunk.get('id')} missing embedding or source_id")
        return []

    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    from google.cloud.firestore_v1.vector import Vector

    collection_ref = db.collection(CHUNKS_COLLECTION)
    query_limit = limit * 3  # Query more since we filter out same-source

    try:
        vector_query = collection_ref.find_nearest(
            vector_field="embedding",
            query_vector=Vector(embedding),
            distance_measure=DistanceMeasure.COSINE,
            limit=query_limit,
        )

        results = []
        for doc in vector_query.stream():
            data = doc.to_dict()
            data["id"] = doc.id

            # Skip same source and self
            if data.get("source_id") == source_id:
                continue
            if data["id"] == chunk.get("id"):
                continue

            # Compute actual similarity
            other_embedding = data.get("embedding")
            if other_embedding:
                similarity = compute_similarity(embedding, other_embedding)
                if similarity >= SIMILARITY_THRESHOLD:
                    data["_similarity"] = similarity
                    results.append(data)

            if len(results) >= limit:
                break

        results.sort(key=lambda x: x.get("_similarity", 0), reverse=True)
        return results[:limit]

    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return []


def relationship_exists(db: firestore.Client, chunk_a_id: str, chunk_b_id: str) -> bool:
    """Check if relationship already exists between two chunks."""
    query1 = (
        db.collection(RELATIONSHIPS_COLLECTION)
        .where("source_chunk_id", "==", chunk_a_id)
        .where("target_chunk_id", "==", chunk_b_id)
        .limit(1)
    )

    query2 = (
        db.collection(RELATIONSHIPS_COLLECTION)
        .where("source_chunk_id", "==", chunk_b_id)
        .where("target_chunk_id", "==", chunk_a_id)
        .limit(1)
    )

    for doc in query1.stream():
        return True
    for doc in query2.stream():
        return True

    return False


def get_chunk_summary(chunk: Dict[str, Any]) -> str:
    """Extract summary from chunk's knowledge card or content."""
    kc = chunk.get("knowledge_card", {})
    if isinstance(kc, dict) and kc.get("summary"):
        return kc["summary"]

    content = chunk.get("content", "")
    if len(content) > 500:
        content = content[:500] + "..."
    return content


def extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from LLM response text."""
    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in markdown code block
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    json_match = re.search(r'\{[^{}]*"type"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def extract_relationship(
    chunk_a: Dict[str, Any],
    chunk_b: Dict[str, Any],
    source_context: str,
) -> Optional[Relationship]:
    """Extract relationship between two chunks using LLM."""
    source_id = chunk_a.get("id")
    target_id = chunk_b.get("id")

    if not source_id or not target_id:
        return None

    # Format prompt
    prompt = RELATIONSHIP_PROMPT.format(
        source_title=chunk_a.get("title", "Unknown"),
        source_summary=get_chunk_summary(chunk_a),
        target_title=chunk_b.get("title", "Unknown"),
        target_summary=get_chunk_summary(chunk_b),
    )

    try:
        model = get_vertex_model()
        response = model.generate_content(prompt)

        if not response or not response.text:
            logger.warning("Empty LLM response")
            return None

        # Parse JSON from response
        result = extract_json_from_response(response.text)
        if not result:
            logger.warning(f"Could not parse JSON from response: {response.text[:200]}")
            return None

        rel_type = result.get("type", "none")
        confidence = float(result.get("confidence", 0))
        explanation = result.get("explanation", "")

        # Validate
        if rel_type not in RELATIONSHIP_TYPES:
            logger.warning(f"Invalid relationship type: {rel_type}")
            return None

        if rel_type == "none":
            return None

        if confidence < CONFIDENCE_THRESHOLD:
            logger.debug(
                f"Confidence {confidence} below threshold {CONFIDENCE_THRESHOLD}"
            )
            return None

        return Relationship(
            source_chunk_id=source_id,
            target_chunk_id=target_id,
            type=rel_type,
            confidence=confidence,
            explanation=explanation,
            source_context=source_context,
        )

    except Exception as e:
        logger.warning(f"Failed to extract relationship: {e}")
        return None


def save_relationship(db: firestore.Client, relationship: Relationship) -> bool:
    """Save a single relationship to Firestore."""
    try:
        db.collection(RELATIONSHIPS_COLLECTION).add(relationship.to_dict())
        return True
    except Exception as e:
        logger.error(f"Failed to save relationship: {e}")
        return False


def process_new_chunks(chunk_ids: List[str]) -> Dict[str, Any]:
    """Process new chunks and extract cross-source relationships."""
    db = get_firestore_client()

    stats = {
        "chunks_processed": 0,
        "pairs_checked": 0,
        "relationships_found": 0,
        "relationships_saved": 0,
        "skipped_existing": 0,
        "errors": 0,
    }

    for chunk_id in chunk_ids:
        try:
            chunk = get_chunk_by_id(db, chunk_id)
            if not chunk:
                logger.warning(f"Chunk not found: {chunk_id}")
                continue

            stats["chunks_processed"] += 1
            source_id = chunk.get("source_id", "unknown")

            similar_chunks = find_similar_cross_source_chunks(db, chunk)

            logger.info(
                f"Chunk {chunk_id} (source: {source_id}): "
                f"found {len(similar_chunks)} similar cross-source chunks"
            )

            for similar in similar_chunks:
                stats["pairs_checked"] += 1

                if relationship_exists(db, chunk_id, similar["id"]):
                    stats["skipped_existing"] += 1
                    continue

                context = f"{source_id}--{similar.get('source_id', 'unknown')}"

                try:
                    relationship = extract_relationship(chunk, similar, context)

                    if relationship:
                        stats["relationships_found"] += 1

                        if save_relationship(db, relationship):
                            stats["relationships_saved"] += 1
                            logger.info(
                                f"Saved: {chunk_id} --{relationship.type}--> "
                                f"{similar['id']} (conf: {relationship.confidence:.2f})"
                            )

                except Exception as e:
                    logger.warning(f"Extraction failed for pair: {e}")
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id}: {e}")
            stats["errors"] += 1

    return stats


@functions_framework.http
def extract_relationships(request: Request):
    """
    HTTP Cloud Function entry point.

    Expected JSON body:
    {
        "run_id": "2024-01-01-abc123",
        "chunk_ids": ["chunk-001", "chunk-002", ...]
    }
    """
    start_time = datetime.now()

    try:
        request_json = request.get_json(silent=True) or {}
        run_id = request_json.get("run_id", "unknown")
        chunk_ids = request_json.get("chunk_ids", [])

        logger.info(f"Starting relationship extraction for run_id: {run_id}")
        logger.info(f"Processing {len(chunk_ids)} new chunks")

        if not chunk_ids:
            logger.info("No chunk_ids provided, skipping extraction")
            return {
                "status": "skipped",
                "run_id": run_id,
                "message": "No new chunks to process",
                "relationships_saved": 0,
            }, 200

        stats = process_new_chunks(chunk_ids)

        duration = (datetime.now() - start_time).total_seconds()

        logger.info(f"Extraction complete in {duration:.1f}s")
        logger.info(f"Stats: {stats}")

        return {
            "status": "success",
            "run_id": run_id,
            "duration_seconds": duration,
            **stats,
        }, 200

    except Exception as e:
        logger.exception(f"Relationship extraction failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "relationships_saved": 0,
        }, 500
