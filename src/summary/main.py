"""
Cloud Function Entry Point for Weekly Knowledge Summary (Epic 9).

Story 9.1: Data pipeline — collects recent chunks, sources, relationships.
Story 9.2: LLM generation — Gemini 3.1 Pro narrative synthesis.
Story 9.3 will add Reader delivery.
"""

import logging
import os
from datetime import datetime, timezone

import functions_framework

# Support both package imports (local/tests) and flat imports (Cloud Functions)
try:
    from .data_pipeline import collect_summary_data
    from .generator import generate_summary as generate_summary_text
except ImportError:
    from data_pipeline import collect_summary_data
    from generator import generate_summary as generate_summary_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT", "kx-hub")

# Lazy-init Firestore
_firestore_client = None


def get_firestore_client():
    from google.cloud import firestore

    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT, database="(default)")
    return _firestore_client


def load_config() -> dict:
    """Load config from Firestore config/summary_generator."""
    db = get_firestore_client()
    doc = db.collection("config").document("summary_generator").get()

    defaults = {
        "enabled": True,
        "days": 7,
        "limit": 100,
    }

    if doc.exists:
        return {**defaults, **doc.to_dict()}
    return defaults


@functions_framework.http
def generate_summary(request):
    """
    Cloud Function HTTP handler for weekly summary generation.

    Request body (all optional):
    {
        "days": 7,
        "limit": 100,
        "model": "gemini-3.1-pro-preview"
    }
    """
    try:
        request_json = request.get_json(silent=True) or {}

        # Load config, allow request overrides
        config = load_config()
        if not config.get("enabled"):
            return {"status": "disabled", "message": "Summary generation disabled"}

        days = request_json.get("days", config["days"])
        limit = request_json.get("limit", config["limit"])
        model = request_json.get("model")

        logger.info(f"Collecting summary data: days={days}, limit={limit}")

        # Story 9.1: Data collection
        data = collect_summary_data(days=days, limit=limit)

        if not data.get("sources"):
            return {
                "status": "success",
                "message": "No sources found for period",
                "stats": data["stats"],
                "period": data["period"],
            }

        # Story 9.2: LLM generation
        result = generate_summary_text(data, model=model)

        # Story 9.3 will add: deliver_to_reader(result["markdown"])

        return {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stats": data["stats"],
            "period": data["period"],
            "model": result["model"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "markdown": result["markdown"],
        }

    except Exception as e:
        logger.exception(f"Summary generation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
