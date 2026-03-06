"""
Cloud Function Entry Point for Weekly Tech Newsletter (Epic 15).

Orchestrates: fetch sources -> curation agent -> newsletter generation ->
Firestore draft + GCS upload + optional Reader delivery.

Dry-run mode: always True in Unit 2. No email delivery.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import functions_framework

try:
    from .curation_agent import run_curation
    from .generator import generate_newsletter
    from .models import NewsletterDraft
except ImportError:
    from curation_agent import run_curation
    from generator import generate_newsletter
    from models import NewsletterDraft

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT", "kx-hub")

_firestore_client = None
_secret_client = None


def _get_db():
    from google.cloud import firestore
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT, database="(default)")
    return _firestore_client


def _get_secret(secret_id: str) -> str:
    from google.cloud import secretmanager
    global _secret_client
    if _secret_client is None:
        _secret_client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{GCP_PROJECT}/secrets/{secret_id}/versions/latest"
    response = _secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def _load_config() -> dict:
    db = _get_db()
    doc = db.collection("config").document("newsletter_generator").get()
    defaults = {
        "enabled": True,
        "days": 7,
        "limit": 50,
        "dry_run": True,
        "deliver_to_reader": True,
    }
    if doc.exists:
        return {**defaults, **doc.to_dict()}
    return defaults


def _fetch_recent_sources(days: int = 7, limit: int = 50) -> list[dict]:
    """Fetch recent kb_items from Firestore for newsletter curation."""
    from google.cloud import firestore

    db = _get_db()
    now = datetime.now(timezone.utc)
    start_dt = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

    collection = os.getenv("FIRESTORE_COLLECTION", "kb_items")
    query = (
        db.collection(collection)
        .where("last_highlighted_at", ">=", start_dt)
        .order_by("last_highlighted_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )

    chunks: list[dict] = []
    for doc in query.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        chunks.append(data)

    # Group by source_id and build source list
    chunks_by_source: dict[str, list] = {}
    for chunk in chunks:
        sid = chunk.get("source_id", "unknown")
        chunks_by_source.setdefault(sid, []).append(chunk)

    sources = []
    for source_id, source_chunks in chunks_by_source.items():
        first = source_chunks[0]
        source_url = first.get("source_url") or first.get("readwise_url") or ""
        stype = "podcast" if "share.snipd.com" in source_url else (
            "book" if first.get("category") == "books" else "article"
        )
        formatted_chunks = []
        for c in source_chunks:
            kc = c.get("knowledge_card")
            formatted_chunks.append({
                "chunk_id": c.get("id", ""),
                "knowledge_card": {
                    "summary": kc.get("summary", "") if kc else "",
                    "takeaways": kc.get("takeaways", []) if kc else [],
                },
            })
        sources.append({
            "source_id": source_id,
            "title": first.get("title", "Untitled"),
            "author": first.get("author", "Unknown"),
            "type": stype,
            "readwise_url": first.get("readwise_url", ""),
            "source_url": source_url,
            "chunks": formatted_chunks,
        })

    logger.info(f"Fetched {len(sources)} sources for newsletter ({days} days)")
    return sources


def _upload_to_gcs(html: str, blob_name: str) -> str:
    """Upload newsletter HTML to GCS kx-hub-content/newsletter/ and return public URL."""
    from google.cloud import storage
    client = storage.Client(project=GCP_PROJECT)
    bucket = client.bucket("kx-hub-content")
    blob = bucket.blob(blob_name)
    blob.upload_from_string(html, content_type="text/html; charset=utf-8")
    return blob.public_url


def _deliver_to_reader(html: str, plain_text: str, title: str, api_key: str) -> dict:
    """Save newsletter as Readwise Reader article with tag ai-newsletter-draft."""
    import requests

    response = requests.post(
        "https://readwise.io/api/v3/save/",
        headers={"Authorization": f"Token {api_key}"},
        json={
            "title": title,
            "html": html,
            "tags": ["ai-newsletter-draft"],
            "should_clean_html": False,
        },
        timeout=30,
    )
    if response.status_code in (200, 201):
        data = response.json()
        return {"status": "success", "reader_url": data.get("url", "")}
    logger.warning(f"Reader delivery failed: {response.status_code} {response.text[:200]}")
    return {"status": "failed", "status_code": response.status_code}


def _save_draft(draft: NewsletterDraft) -> str:
    """Save newsletter draft to Firestore and return doc_id."""
    db = _get_db()
    doc_ref = db.collection("newsletter_drafts").document()
    doc_ref.set(draft.model_dump())
    logger.info(f"Newsletter draft saved: newsletter_drafts/{doc_ref.id}")
    return doc_ref.id


@functions_framework.http
def generate_newsletter_cf(request):
    """
    Cloud Function HTTP handler for weekly newsletter generation.

    Request body (all optional):
    {
        "days": 7,
        "limit": 50,
        "dry_run": true
    }
    """
    try:
        request_json = request.get_json(silent=True) or {}
        config = _load_config()

        if not config.get("enabled"):
            return {"status": "disabled", "message": "Newsletter generation disabled"}

        days = request_json.get("days", config["days"])
        limit = request_json.get("limit", config["limit"])
        dry_run = request_json.get("dry_run", config.get("dry_run", True))

        now = datetime.now(timezone.utc)
        period = {
            "start": (now.replace(hour=0, minute=0, second=0) - timedelta(days=days)).strftime("%Y-%m-%d"),
            "end": now.strftime("%Y-%m-%d"),
        }

        logger.info(f"Generating newsletter: days={days}, limit={limit}, dry_run={dry_run}")

        # 1. Fetch recent sources
        sources = _fetch_recent_sources(days=days, limit=limit)
        if not sources:
            return {"status": "success", "message": "No sources found for period"}

        # 2. Curation agent
        curation_result = run_curation(sources)
        logger.info(
            f"Curation: {len(curation_result.filtered_sources)} sources, "
            f"{len(curation_result.hot_news)} hot news"
        )

        # 3. Generate newsletter
        newsletter = generate_newsletter(curation_result, period)

        # 4. Upload to GCS
        ts = now.strftime("%Y%m%d_%H%M%S")
        gcs_url = ""
        try:
            gcs_url = _upload_to_gcs(newsletter["html"], f"newsletter/{ts}_newsletter.html")
            logger.info(f"Newsletter uploaded to GCS: {gcs_url}")
        except Exception as e:
            logger.warning(f"GCS upload failed (non-fatal): {e}")

        # 5. Optional Reader delivery
        reader_url = ""
        if config.get("deliver_to_reader") and not dry_run:
            try:
                api_key = _get_secret("readwise-api-key")
                reader_result = _deliver_to_reader(
                    newsletter["html"],
                    newsletter["plain_text"],
                    newsletter["subject"],
                    api_key,
                )
                reader_url = reader_result.get("reader_url", "")
            except Exception as e:
                logger.warning(f"Reader delivery failed (non-fatal): {e}")

        # 6. Save draft to Firestore
        draft = NewsletterDraft(
            html=newsletter["html"],
            plain_text=newsletter["plain_text"],
            subject=newsletter["subject"],
            curated_sources=curation_result.filtered_sources,
            hot_news=curation_result.hot_news,
            dry_run=dry_run,
            created_at=now.isoformat(),
            period_start=period["start"],
            period_end=period["end"],
            gcs_url=gcs_url,
            reader_url=reader_url,
        )
        draft_id = _save_draft(draft)

        return {
            "status": "success",
            "draft_id": draft_id,
            "subject": newsletter["subject"],
            "curated_sources_count": len(curation_result.filtered_sources),
            "hot_news_count": len(curation_result.hot_news),
            "gcs_url": gcs_url,
            "reader_url": reader_url,
            "dry_run": dry_run,
        }

    except Exception as e:
        logger.exception(f"Newsletter generation failed: {e}")
        return {"status": "error", "error": str(e)}
