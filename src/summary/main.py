"""
Cloud Function Entry Point for Weekly Knowledge Summary (Epic 9).

Story 9.1: Data pipeline — collects recent chunks, sources, relationships.
Story 9.2: LLM generation — Gemini 3.1 Pro narrative synthesis.
Story 9.3: Reader delivery — save to Readwise Reader inbox.
"""

import logging
import os
from datetime import datetime, timezone

import functions_framework

# Support both package imports (local/tests) and flat imports (Cloud Functions)
try:
    from .cover_image import extract_themes, generate_cover_image, upload_html_to_gcs, upload_to_gcs
    from .data_pipeline import collect_summary_data
    from .delivery import _markdown_to_html, deliver_to_reader
    from .generator import generate_summary as generate_summary_text
except ImportError:
    from cover_image import extract_themes, generate_cover_image, upload_html_to_gcs, upload_to_gcs
    from data_pipeline import collect_summary_data
    from delivery import _markdown_to_html, deliver_to_reader
    from generator import generate_summary as generate_summary_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT", "kx-hub")

# Lazy-init clients
_firestore_client = None
_secret_client = None


def get_firestore_client():
    from google.cloud import firestore

    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT, database="(default)")
    return _firestore_client


def get_secret(secret_id: str) -> str:
    """Fetch secret from Secret Manager."""
    from google.cloud import secretmanager

    global _secret_client
    if _secret_client is None:
        _secret_client = secretmanager.SecretManagerServiceClient()

    name = f"projects/{GCP_PROJECT}/secrets/{secret_id}/versions/latest"
    response = _secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def load_config() -> dict:
    """Load config from Firestore config/summary_generator."""
    db = get_firestore_client()
    doc = db.collection("config").document("summary_generator").get()

    defaults = {
        "enabled": True,
        "days": 7,
        "limit": 100,
        "deliver_to_reader": True,
    }

    if doc.exists:
        return {**defaults, **doc.to_dict()}
    return defaults


def _extract_title(data: dict) -> str:
    """Build title from pipeline data period."""
    period = data["period"]
    from datetime import datetime as dt

    months_de = {
        1: "Jan", 2: "Feb", 3: "Mär", 4: "Apr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Dez",
    }
    start = dt.strptime(period["start"], "%Y-%m-%d")
    end = dt.strptime(period["end"], "%Y-%m-%d")
    return f"Knowledge Summary: {start.day}. {months_de[start.month]} – {end.day}. {months_de[end.month]} {end.year}"


def _save_summary(
    title: str,
    markdown: str,
    period: dict,
    stats: dict,
    model: str,
    input_tokens: int,
    output_tokens: int,
    delivery: dict | None,
    timestamp: datetime,
) -> None:
    """Save summary to Firestore summaries collection."""
    db = get_firestore_client()
    doc_id = period["start"] + "_" + period["end"]
    doc_data = {
        "title": title,
        "markdown": markdown,
        "period": period,
        "stats": stats,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "delivery": delivery,
        "created_at": timestamp,
    }
    db.collection("summaries").document(doc_id).set(doc_data)
    logger.info(f"Summary saved to Firestore: summaries/{doc_id}")


@functions_framework.http
def generate_summary(request):
    """
    Cloud Function HTTP handler for weekly summary generation.

    Request body (all optional):
    {
        "days": 7,
        "limit": 100,
        "model": "gemini-3.1-pro-preview",
        "dry_run": false
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
        dry_run = request_json.get("dry_run", False)

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

        title = _extract_title(data)
        now = datetime.now(timezone.utc)

        response = {
            "status": "success",
            "timestamp": now.isoformat(),
            "stats": data["stats"],
            "period": data["period"],
            "model": result["model"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "markdown": result["markdown"],
        }

        # Cover image generation
        image_url = None
        if not dry_run:
            try:
                themes = extract_themes(result["markdown"])
                image_bytes = generate_cover_image(themes, data["period"])
                ts = now.strftime("%Y%m%d_%H%M%S")
                image_url = upload_to_gcs(image_bytes, f"{ts}_cover.png")
                logger.info(f"Cover image uploaded: {image_url}")
                response["image_url"] = image_url
            except Exception as e:
                logger.warning(f"Cover image generation failed (non-fatal): {e}")

        # Upload styled HTML page (used as "Open original" in Reader)
        html_url = None
        if not dry_run:
            try:
                ts = now.strftime("%Y%m%d_%H%M%S")
                html_body = _markdown_to_html(result["markdown"])
                html_url = upload_html_to_gcs(html_body, title, f"{ts}_summary.html", image_url)
                logger.info(f"HTML page uploaded: {html_url}")
                response["html_url"] = html_url
            except Exception as e:
                logger.warning(f"HTML upload failed (non-fatal): {e}")

        # Story 9.3: Reader delivery
        if config.get("deliver_to_reader") and not dry_run:
            api_key = get_secret("readwise-api-key")
            delivery = deliver_to_reader(
                markdown=result["markdown"],
                title=title,
                api_key=api_key,
                image_url=image_url,
                html_url=html_url,
            )
            response["delivery"] = delivery
        elif dry_run:
            response["delivery"] = {"status": "dry_run"}

        # Save to Firestore summaries collection
        if not dry_run:
            _save_summary(
                title=title,
                markdown=result["markdown"],
                period=data["period"],
                stats=data["stats"],
                model=result["model"],
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                delivery=response.get("delivery"),
                timestamp=now,
            )

        return response

    except Exception as e:
        logger.exception(f"Summary generation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
