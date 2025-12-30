#!/usr/bin/env python3
"""
Entity Type Discovery Script

Analyzes existing KB data to discover emergent entity types using LLM extraction.
Follows the emergent schema approach (no predefined types).

Usage:
    python3 scripts/analyze_entity_types.py --sample 50
    python3 scripts/analyze_entity_types.py --sample 100 --output results/entity_analysis.json

Story 4.1 Preparation: Understand what entity types naturally exist in the data.
"""

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google.cloud import firestore

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# LLM prompt for entity extraction (emergent - no predefined types)
ENTITY_EXTRACTION_PROMPT = """Analyze this text and extract all notable entities.

For each entity, provide:
1. name: The entity name as it appears (or normalized form)
2. type: What kind of thing is this? Use your judgment - be specific but not too granular
3. context: Brief note on how it's mentioned (1-2 words)

Text:
{text}

Return JSON array of entities:
[
  {{"name": "...", "type": "...", "context": "..."}},
  ...
]

Important:
- Extract ALL notable entities (people, concepts, tools, companies, etc.)
- For TYPE: use natural language labels (e.g., "person", "software_tool", "programming_concept", "company", "methodology", "book")
- Don't force entities into predefined categories - let the type emerge from context
- Include entities that appear important to the text's meaning
- Normalize obvious duplicates (e.g., "React" and "React.js" → "React")

Return ONLY the JSON array, no other text."""


def get_firestore_client() -> firestore.Client:
    """Initialize Firestore client."""
    project = os.getenv("GCP_PROJECT")
    if not project:
        raise ValueError("GCP_PROJECT environment variable not set")
    return firestore.Client(project=project)


def fetch_sample_chunks(
    db: firestore.Client, sample_size: int = 50
) -> List[Dict[str, Any]]:
    """
    Fetch a diverse sample of chunks for analysis.

    Samples from different sources and time periods for diversity.
    """
    collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")

    logger.info(f"Fetching {sample_size} sample chunks from {collection}")

    # Get chunks with knowledge cards (they have richer content)
    query = (
        db.collection(collection)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(sample_size * 2)
    )  # Fetch more, then filter

    docs = list(query.stream())

    chunks = []
    source_counts = {}  # Track how many chunks per source

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        # Prefer chunks with knowledge cards
        if data.get("knowledge_card"):
            # Ensure source diversity
            source = data.get("source", "unknown")
            current_count = source_counts.get(source, 0)
            if current_count < sample_size // 5:  # Max 20% per source
                chunks.append(data)
                source_counts[source] = current_count + 1

        if len(chunks) >= sample_size:
            break

    # If not enough with knowledge cards, add any chunks
    if len(chunks) < sample_size:
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            if data["id"] not in [c["id"] for c in chunks]:
                chunks.append(data)
                if len(chunks) >= sample_size:
                    break

    logger.info(f"Fetched {len(chunks)} chunks for analysis")
    return chunks


def extract_entities_from_chunk(
    client,  # BaseLLMClient
    chunk: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Extract entities from a single chunk using LLM.

    Uses knowledge card summary if available, falls back to content.
    """
    # Build text for analysis
    text_parts = []

    # Title
    if chunk.get("title"):
        text_parts.append(f"Title: {chunk['title']}")

    # Knowledge card summary (preferred - already distilled)
    knowledge_card = chunk.get("knowledge_card", {})
    has_knowledge_card = False
    if isinstance(knowledge_card, dict):
        if knowledge_card.get("summary"):
            text_parts.append(f"Summary: {knowledge_card['summary']}")
            has_knowledge_card = True
        if knowledge_card.get("key_points"):
            points = knowledge_card["key_points"]
            if isinstance(points, list):
                text_parts.append(f"Key Points: {'; '.join(points[:5])}")
                has_knowledge_card = True
        if knowledge_card.get("takeaways"):
            takeaways = knowledge_card["takeaways"]
            if isinstance(takeaways, list):
                text_parts.append(f"Takeaways: {'; '.join(takeaways[:5])}")
                has_knowledge_card = True

    # Fall back to content if no knowledge card data
    if not has_knowledge_card:
        content = chunk.get("content", "")
        if content:
            # Truncate to avoid token limits
            text_parts.append(f"Content: {content[:2000]}")

    text = "\n".join(text_parts)

    if not text.strip():
        return []

    try:
        prompt = ENTITY_EXTRACTION_PROMPT.format(text=text)
        response = client.generate(prompt)

        # Parse JSON from response text
        response_text = response.text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            # Remove first and last lines (```json and ```)
            response_text = "\n".join(lines[1:-1])

        entities = json.loads(response_text)

        if isinstance(entities, list):
            return entities
        elif isinstance(entities, dict) and "entities" in entities:
            return entities["entities"]
        else:
            logger.warning(f"Unexpected response format: {type(entities)}")
            return []

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed for chunk {chunk.get('id', 'unknown')}: {e}")
        logger.debug(
            f"Response was: {response_text[:200] if 'response_text' in dir() else 'N/A'}"
        )
        return []
    except Exception as e:
        logger.warning(
            f"Entity extraction failed for chunk {chunk.get('id', 'unknown')}: {e}"
        )
        return []


def analyze_entity_types(entities: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Analyze extracted entities to discover emergent types.

    Returns statistics about types, frequencies, and examples.
    """
    type_counter = Counter()
    type_examples = defaultdict(list)
    entity_type_mapping = defaultdict(set)

    for entity in entities:
        entity_type = entity.get("type", "unknown").lower().strip()
        entity_name = entity.get("name", "").strip()
        context = entity.get("context", "")

        if not entity_name:
            continue

        type_counter[entity_type] += 1

        # Store examples (max 10 per type)
        if len(type_examples[entity_type]) < 10:
            type_examples[entity_type].append({"name": entity_name, "context": context})

        # Track which entities have which type
        entity_type_mapping[entity_name].add(entity_type)

    # Find entities with multiple types (inconsistency)
    multi_typed = {
        name: list(types)
        for name, types in entity_type_mapping.items()
        if len(types) > 1
    }

    # Calculate type hierarchy suggestions
    type_groups = group_similar_types(list(type_counter.keys()))

    return {
        "type_frequencies": dict(type_counter.most_common()),
        "type_examples": dict(type_examples),
        "total_entities": len(entities),
        "unique_types": len(type_counter),
        "multi_typed_entities": multi_typed,
        "suggested_type_groups": type_groups,
    }


def group_similar_types(types: List[str]) -> Dict[str, List[str]]:
    """
    Group similar entity types together.

    Uses simple heuristics - could be enhanced with embeddings.
    """
    groups = defaultdict(list)

    # Common groupings
    person_keywords = [
        "person",
        "author",
        "developer",
        "researcher",
        "founder",
        "ceo",
        "engineer",
    ]
    tech_keywords = [
        "technology",
        "tool",
        "framework",
        "library",
        "language",
        "software",
        "platform",
        "service",
    ]
    concept_keywords = [
        "concept",
        "methodology",
        "pattern",
        "principle",
        "theory",
        "approach",
        "practice",
    ]
    org_keywords = ["company", "organization", "startup", "corporation", "institution"]
    work_keywords = ["book", "article", "paper", "publication", "blog", "newsletter"]

    for t in types:
        t_lower = t.lower()

        if any(kw in t_lower for kw in person_keywords):
            groups["PERSON"].append(t)
        elif any(kw in t_lower for kw in tech_keywords):
            groups["TECHNOLOGY"].append(t)
        elif any(kw in t_lower for kw in concept_keywords):
            groups["CONCEPT"].append(t)
        elif any(kw in t_lower for kw in org_keywords):
            groups["ORGANIZATION"].append(t)
        elif any(kw in t_lower for kw in work_keywords):
            groups["WORK"].append(t)
        else:
            groups["OTHER"].append(t)

    return dict(groups)


def print_analysis_report(analysis: Dict[str, Any], chunks_analyzed: int):
    """Print human-readable analysis report."""
    print("\n" + "=" * 60)
    print("ENTITY TYPE DISCOVERY REPORT")
    print("=" * 60)

    print(f"\nChunks analyzed: {chunks_analyzed}")
    print(f"Total entities extracted: {analysis['total_entities']}")
    print(f"Unique entity types: {analysis['unique_types']}")

    print("\n" + "-" * 40)
    print("TOP ENTITY TYPES (by frequency)")
    print("-" * 40)

    for entity_type, count in list(analysis["type_frequencies"].items())[:20]:
        pct = (count / analysis["total_entities"]) * 100
        print(f"  {entity_type:30} {count:4} ({pct:5.1f}%)")

    print("\n" + "-" * 40)
    print("EXAMPLES BY TYPE")
    print("-" * 40)

    for entity_type in list(analysis["type_frequencies"].keys())[:10]:
        examples = analysis["type_examples"].get(entity_type, [])
        example_names = [e["name"] for e in examples[:5]]
        print(f"\n  {entity_type}:")
        print(f"    {', '.join(example_names)}")

    print("\n" + "-" * 40)
    print("SUGGESTED TYPE GROUPINGS")
    print("-" * 40)

    for group_name, types in analysis["suggested_type_groups"].items():
        if types:
            print(f"\n  {group_name}:")
            for t in types[:10]:
                print(f"    - {t}")

    if analysis["multi_typed_entities"]:
        print("\n" + "-" * 40)
        print("ENTITIES WITH MULTIPLE TYPES (inconsistency)")
        print("-" * 40)

        for entity, types in list(analysis["multi_typed_entities"].items())[:10]:
            print(f"  {entity}: {', '.join(types)}")

    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)

    # Calculate recommendations
    top_types = list(analysis["type_frequencies"].keys())[:10]
    if analysis["total_entities"] > 0:
        coverage = (
            sum(analysis["type_frequencies"][t] for t in top_types)
            / analysis["total_entities"]
            * 100
        )
    else:
        coverage = 0

    print(f"\n1. Top 10 types cover {coverage:.1f}% of all entities")
    print("2. Consider these as potential core entity types for your schema")
    print("3. Review 'OTHER' group for domain-specific types to add")
    print("4. Multi-typed entities suggest need for normalization rules")
    print("\n")


def main():
    parser = argparse.ArgumentParser(description="Discover entity types from KB data")
    parser.add_argument(
        "--sample", type=int, default=50, help="Number of chunks to analyze"
    )
    parser.add_argument("--output", type=str, help="Output JSON file path")
    parser.add_argument(
        "--model", type=str, default="gemini-2.5-flash", help="LLM model to use"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize
    logger.info("Starting entity type discovery analysis")

    try:
        from src.llm import get_client
    except ImportError:
        logger.error(
            "Could not import LLM client. Make sure you're in the project root."
        )
        sys.exit(1)

    # Get LLM client
    logger.info(f"Using model: {args.model}")
    client = get_client(args.model)

    # Get Firestore client
    db = get_firestore_client()

    # Fetch sample chunks
    chunks = fetch_sample_chunks(db, args.sample)

    if not chunks:
        logger.error("No chunks found in database")
        sys.exit(1)

    # Extract entities from each chunk
    all_entities = []

    for i, chunk in enumerate(chunks):
        logger.info(
            f"Processing chunk {i + 1}/{len(chunks)}: {chunk.get('title', 'untitled')[:50]}"
        )

        entities = extract_entities_from_chunk(client, chunk)

        # Add source tracking
        for entity in entities:
            entity["source_chunk_id"] = chunk["id"]

        all_entities.extend(entities)

        if args.verbose:
            logger.debug(f"  Extracted {len(entities)} entities")

    # Analyze entity types
    analysis = analyze_entity_types(all_entities)

    # Add metadata
    analysis["metadata"] = {
        "analysis_date": datetime.now(timezone.utc).isoformat(),
        "chunks_analyzed": len(chunks),
        "model_used": args.model,
        "sample_size": args.sample,
    }

    # Save raw entities for further analysis
    analysis["raw_entities"] = all_entities

    # Print report
    print_analysis_report(analysis, len(chunks))

    # Save to file if requested
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(analysis, f, indent=2, default=str)
        logger.info(f"Analysis saved to {args.output}")

    return analysis


if __name__ == "__main__":
    main()
