#!/usr/bin/env python3
"""
LLM Data Regeneration Tool

Regenerates LLM-generated content in Firestore when switching models.
Useful for A/B testing or upgrading to better models.

Usage:
    # Regenerate all knowledge cards with Claude
    LLM_MODEL=claude-haiku python -m src.llm.regenerate knowledge-cards --all

    # Regenerate only old cards (older than 30 days)
    LLM_MODEL=gemini-3 python -m src.llm.regenerate knowledge-cards --older-than 30

    # Regenerate cluster names/descriptions
    LLM_MODEL=claude-haiku python -m src.llm.regenerate clusters --all

    # Dry run with cost estimate
    python -m src.llm.regenerate knowledge-cards --all --dry-run

    # Compare models (generate with both, show side-by-side)
    python -m src.llm.regenerate compare --sample 5
"""

import argparse
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from . import BaseLLMClient, get_client, get_model_info, list_models

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RegenerationStats:
    """Track regeneration progress and costs."""

    def __init__(self):
        self.total = 0
        self.processed = 0
        self.failed = 0
        self.skipped = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.start_time = None
        self.model_id = None

    def start(self, total: int, model_id: str):
        self.total = total
        self.model_id = model_id
        self.start_time = time.time()
        logger.info(f"Starting regeneration: {total} items with {model_id}")

    def record_success(self, input_tokens: int = 0, output_tokens: int = 0):
        self.processed += 1
        self.input_tokens += input_tokens or 0
        self.output_tokens += output_tokens or 0

    def record_failure(self):
        self.failed += 1

    def record_skip(self):
        self.skipped += 1

    def estimate_cost(self) -> Dict[str, float]:
        """Estimate cost based on model pricing."""
        model_info = get_model_info(self.model_id)
        if not model_info:
            return {"input_cost": 0, "output_cost": 0, "total_cost": 0}

        input_cost = (self.input_tokens / 1_000_000) * model_info.input_cost_per_1m
        output_cost = (self.output_tokens / 1_000_000) * model_info.output_cost_per_1m

        return {
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": input_cost + output_cost,
        }

    def summary(self) -> Dict[str, Any]:
        duration = time.time() - self.start_time if self.start_time else 0
        cost = self.estimate_cost()

        return {
            "model": self.model_id,
            "total": self.total,
            "processed": self.processed,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_seconds": round(duration, 1),
            "items_per_second": round(self.processed / duration, 2)
            if duration > 0
            else 0,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(cost["total_cost"], 4),
        }


def get_firestore_client() -> firestore.Client:
    """Get Firestore client."""
    project = os.environ.get("GCP_PROJECT", "kx-hub")
    return firestore.Client(project=project)


def regenerate_knowledge_cards(
    db: firestore.Client,
    client: BaseLLMClient,
    filter_mode: str = "all",
    older_than_days: int = 30,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> RegenerationStats:
    """
    Regenerate knowledge cards for KB items.

    Args:
        db: Firestore client
        client: LLM client to use
        filter_mode: 'all', 'missing', 'older_than'
        older_than_days: Days threshold for 'older_than' mode
        limit: Max items to process (for testing)
        dry_run: If True, don't write to Firestore

    Returns:
        RegenerationStats with results
    """
    from src.knowledge_cards.prompt_manager import PromptManager
    from src.knowledge_cards.schema import validate_knowledge_card_response

    from . import GenerationConfig

    stats = RegenerationStats()
    prompt_manager = PromptManager()

    # Build query based on filter mode
    collection = db.collection("kb_items")

    if filter_mode == "missing":
        # Items without knowledge_card
        query = collection.where("knowledge_card", "==", None)
    elif filter_mode == "older_than":
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        cutoff_str = cutoff.isoformat() + "Z"
        # Items with old knowledge cards
        query = collection.where("knowledge_card.generated_at", "<", cutoff_str)
    else:
        # All items with content
        query = collection

    # Load documents
    docs = list(query.stream())

    if limit:
        docs = docs[:limit]

    # Filter to only docs with content
    items = []
    for doc in docs:
        data = doc.to_dict()
        if data.get("content"):
            items.append({"id": doc.id, **data})

    stats.start(len(items), client.model_id)

    if dry_run:
        logger.info(f"[DRY RUN] Would regenerate {len(items)} knowledge cards")
        # Estimate tokens (rough: 500 input, 300 output per item)
        stats.input_tokens = len(items) * 500
        stats.output_tokens = len(items) * 300
        stats.processed = len(items)
        return stats

    # Generation config
    config = GenerationConfig(
        temperature=0.7, max_output_tokens=2048, top_p=0.95, top_k=40
    )

    batch = db.batch()
    batch_count = 0

    for i, item in enumerate(items):
        try:
            # Build prompt
            prompt = prompt_manager.format_prompt(
                title=item.get("title", "Untitled"),
                author=item.get("author", "Unknown"),
                content=item.get("content", ""),
            )

            # Generate
            response_data = client.generate_json(prompt, config)

            # Validate
            knowledge_card = validate_knowledge_card_response(response_data)

            # Update Firestore
            doc_ref = collection.document(item["id"])
            batch.set(doc_ref, {"knowledge_card": knowledge_card.to_dict()}, merge=True)
            batch_count += 1

            # Track tokens if available
            # Note: generate_json doesn't return token counts, so we estimate
            stats.record_success(input_tokens=500, output_tokens=300)

            # Commit batch
            if batch_count >= 100:
                batch.commit()
                logger.info(
                    f"Progress: {i + 1}/{len(items)} ({stats.processed} succeeded, {stats.failed} failed)"
                )
                batch = db.batch()
                batch_count = 0

        except Exception as e:
            logger.warning(f"Failed to regenerate {item['id']}: {e}")
            stats.record_failure()

    # Final batch
    if batch_count > 0:
        batch.commit()

    return stats


def regenerate_clusters(
    db: firestore.Client, client: BaseLLMClient, dry_run: bool = False
) -> RegenerationStats:
    """
    Regenerate cluster names and descriptions.

    Args:
        db: Firestore client
        client: LLM client to use
        dry_run: If True, don't write to Firestore

    Returns:
        RegenerationStats with results
    """
    from src.clustering.cluster_metadata import ClusterMetadataGenerator

    stats = RegenerationStats()

    project = os.environ.get("GCP_PROJECT", "kx-hub")
    region = os.environ.get("GCP_REGION", "europe-west4")

    generator = ClusterMetadataGenerator(
        project_id=project, region=region, dry_run=dry_run, llm_client=client
    )

    # Count clusters
    clusters = list(db.collection("clusters").stream())
    stats.start(len(clusters), client.model_id)

    if dry_run:
        logger.info(
            f"[DRY RUN] Would regenerate {len(clusters)} cluster names/descriptions"
        )
        stats.input_tokens = len(clusters) * 1000  # Estimate
        stats.output_tokens = len(clusters) * 100
        stats.processed = len(clusters)
        return stats

    try:
        result = generator.generate_all_clusters()
        stats.processed = result["total_clusters"]
    except Exception as e:
        logger.error(f"Cluster regeneration failed: {e}")
        stats.failed = len(clusters)

    return stats


def compare_models(
    db: firestore.Client, models: List[str], sample_size: int = 5
) -> Dict[str, Any]:
    """
    Compare outputs from different models side-by-side.

    Args:
        db: Firestore client
        models: List of model names to compare
        sample_size: Number of items to sample

    Returns:
        Comparison results
    """
    from src.knowledge_cards.prompt_manager import PromptManager

    from . import GenerationConfig

    prompt_manager = PromptManager()
    config = GenerationConfig(temperature=0.7, max_output_tokens=4096)

    # Sample random items
    docs = list(db.collection("kb_items").limit(sample_size * 3).stream())
    items = [
        {"id": doc.id, **doc.to_dict()} for doc in docs if doc.to_dict().get("content")
    ][:sample_size]

    results = []

    for item in items:
        prompt = prompt_manager.format_prompt(
            title=item.get("title", "Untitled"),
            author=item.get("author", "Unknown"),
            content=item.get("content", "")[:2000],  # Truncate for comparison
        )

        comparison = {
            "chunk_id": item["id"],
            "title": item.get("title", "Untitled"),
            "outputs": {},
        }

        for model_name in models:
            try:
                client = get_client(model_name, cache=False)
                response = client.generate_json(prompt, config)
                comparison["outputs"][model_name] = {
                    "summary": response.get("summary", ""),
                    "takeaways": response.get("takeaways", []),
                    "tags": response.get("tags", []),
                }
            except Exception as e:
                comparison["outputs"][model_name] = {"error": str(e)}

        results.append(comparison)

        # Print side-by-side
        print(f"\n{'=' * 80}")
        print(f"CHUNK: {item.get('title', 'Untitled')[:60]}")
        print(f"{'=' * 80}")

        for model_name in models:
            output = comparison["outputs"].get(model_name, {})
            print(f"\n--- {model_name} ---")
            if "error" in output:
                print(f"  ERROR: {output['error']}")
            else:
                print(f"  Summary: {output.get('summary', 'N/A')[:100]}...")
                print(f"  Tags: {', '.join(output.get('tags', []))}")
                print(f"  Takeaways: {len(output.get('takeaways', []))} items")

    return {"comparisons": results, "models": models, "sample_size": sample_size}


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate LLM-generated content in Firestore",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Regenerate all knowledge cards with Claude Haiku
    LLM_MODEL=claude-haiku python -m src.llm.regenerate knowledge-cards --all

    # Regenerate cards older than 30 days
    LLM_MODEL=gemini-3 python -m src.llm.regenerate knowledge-cards --older-than 30

    # Regenerate cluster metadata
    LLM_MODEL=claude-haiku python -m src.llm.regenerate clusters

    # Dry run to estimate cost
    python -m src.llm.regenerate knowledge-cards --all --dry-run

    # Compare models side-by-side
    python -m src.llm.regenerate compare --models gemini,claude-haiku --sample 3

    # List available models
    python -m src.llm.regenerate list-models
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # knowledge-cards command
    kc_parser = subparsers.add_parser(
        "knowledge-cards", help="Regenerate knowledge cards"
    )
    kc_group = kc_parser.add_mutually_exclusive_group(required=True)
    kc_group.add_argument("--all", action="store_true", help="Regenerate all cards")
    kc_group.add_argument(
        "--missing", action="store_true", help="Only generate missing cards"
    )
    kc_group.add_argument(
        "--older-than",
        type=int,
        metavar="DAYS",
        help="Regenerate cards older than N days",
    )
    kc_parser.add_argument(
        "--limit", type=int, help="Limit number of items (for testing)"
    )
    kc_parser.add_argument(
        "--dry-run", action="store_true", help="Estimate cost without writing"
    )

    # clusters command
    cl_parser = subparsers.add_parser(
        "clusters", help="Regenerate cluster names/descriptions"
    )
    cl_parser.add_argument(
        "--dry-run", action="store_true", help="Estimate cost without writing"
    )

    # compare command
    cmp_parser = subparsers.add_parser(
        "compare", help="Compare model outputs side-by-side"
    )
    cmp_parser.add_argument(
        "--models", required=True, help="Comma-separated model names"
    )
    cmp_parser.add_argument("--sample", type=int, default=5, help="Number of samples")

    # list-models command
    subparsers.add_parser("list-models", help="List available models with pricing")

    args = parser.parse_args()

    if args.command == "list-models":
        print("\nAvailable Models:\n")
        print(
            f"{'Model':<25} {'Provider':<10} {'Input $/1M':<12} {'Output $/1M':<12} {'Description'}"
        )
        print("-" * 100)
        for name, info in list_models().items():
            print(
                f"{name:<25} {info.provider.value:<10} ${info.input_cost_per_1m:<11.2f} ${info.output_cost_per_1m:<11.2f} {info.description[:40]}"
            )

        print(
            f"\nCurrent model: {os.environ.get('LLM_MODEL', 'gemini-2.5-flash (default)')}"
        )
        print("\nSet LLM_MODEL environment variable to change model.")
        return

    if args.command == "compare":
        models = [m.strip() for m in args.models.split(",")]
        db = get_firestore_client()
        compare_models(db, models, args.sample)
        return

    # Get LLM client
    client = get_client()
    db = get_firestore_client()

    logger.info(f"Using model: {client.model_id}")

    if args.command == "knowledge-cards":
        if args.all:
            filter_mode = "all"
        elif args.missing:
            filter_mode = "missing"
        else:
            filter_mode = "older_than"

        stats = regenerate_knowledge_cards(
            db=db,
            client=client,
            filter_mode=filter_mode,
            older_than_days=args.older_than or 30,
            limit=args.limit,
            dry_run=args.dry_run,
        )

    elif args.command == "clusters":
        stats = regenerate_clusters(db=db, client=client, dry_run=args.dry_run)

    else:
        parser.print_help()
        return

    # Print summary
    summary = stats.summary()
    print(f"\n{'=' * 60}")
    print("REGENERATION SUMMARY")
    print(f"{'=' * 60}")
    print(f"Model:             {summary['model']}")
    print(f"Total items:       {summary['total']}")
    print(f"Processed:         {summary['processed']}")
    print(f"Failed:            {summary['failed']}")
    print(f"Skipped:           {summary['skipped']}")
    print(f"Duration:          {summary['duration_seconds']}s")
    print(f"Speed:             {summary['items_per_second']} items/sec")
    print(
        f"Estimated tokens:  {summary['input_tokens']:,} in / {summary['output_tokens']:,} out"
    )
    print(f"Estimated cost:    ${summary['estimated_cost_usd']:.4f}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
