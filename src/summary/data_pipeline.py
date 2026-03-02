"""
Summary Data Pipeline (Story 9.1).

Collects recent KB data (chunks, sources, relationships) for weekly
knowledge summary generation. Outputs a structured dict consumed by
the LLM prompt in Story 9.2.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse

from google.cloud import firestore

logger = logging.getLogger(__name__)

# Lazy-init Firestore
_firestore_client = None


def _get_db() -> firestore.Client:
    global _firestore_client
    if _firestore_client is None:
        project = os.getenv("GCP_PROJECT", "kx-hub")
        _firestore_client = firestore.Client(project=project, database="(default)")
    return _firestore_client


def _get_collection() -> str:
    return os.getenv("FIRESTORE_COLLECTION", "kb_items")


# ---------------------------------------------------------------------------
# Source type detection
# ---------------------------------------------------------------------------

def detect_source_type(chunk: Dict[str, Any]) -> str:
    """Detect whether a chunk comes from a podcast, book, or article."""
    source_url = chunk.get("source_url", "") or ""
    if "share.snipd.com" in source_url:
        return "podcast"

    category = chunk.get("category", "")
    if category == "books":
        return "book"

    return "article"


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------

def resolve_url(chunk: Dict[str, Any]) -> str:
    """Pick the best URL for a chunk: source_url > readwise_url > highlight_url."""
    return (
        chunk.get("source_url")
        or chunk.get("readwise_url")
        or chunk.get("highlight_url")
        or ""
    )


# ---------------------------------------------------------------------------
# Fetch recent chunks
# ---------------------------------------------------------------------------

def fetch_recent_chunks(days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
    """Query kb_items by last_highlighted_at within the given window."""
    db = _get_db()
    collection = _get_collection()

    now = datetime.now(timezone.utc)
    start_dt = (now - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    query = (
        db.collection(collection)
        .where("last_highlighted_at", ">=", start_dt)
        .order_by("last_highlighted_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )

    chunks = []
    for doc in query.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        chunks.append(data)

    logger.info(f"Fetched {len(chunks)} recent chunks (last {days} days)")
    return chunks


# ---------------------------------------------------------------------------
# Fetch relationships for a set of source IDs (batch)
# ---------------------------------------------------------------------------

def fetch_relationships_for_sources(
    source_ids: List[str],
    chunks_by_source: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    Fetch cross-source relationships for the given source IDs.

    Re-implements the logic from firestore_client.get_source_relationships
    but batches across all sources in one pass to avoid redundant reads.
    """
    db = _get_db()

    # Collect all chunk_ids across sources
    all_chunk_ids: List[str] = []
    chunk_to_source: Dict[str, str] = {}
    for sid, chunks in chunks_by_source.items():
        for c in chunks:
            cid = c.get("id", "")
            if cid:
                all_chunk_ids.append(cid)
                chunk_to_source[cid] = sid

    if not all_chunk_ids:
        return []

    chunk_ids_set = set(all_chunk_ids)

    # Batch fetch relationships (IN queries, max 30 per batch)
    raw_rels: List[Dict[str, Any]] = []
    for i in range(0, len(all_chunk_ids), 30):
        batch = all_chunk_ids[i : i + 30]

        for doc in (
            db.collection("relationships")
            .where("source_chunk_id", "in", batch)
            .stream()
        ):
            raw_rels.append(doc.to_dict())

        for doc in (
            db.collection("relationships")
            .where("target_chunk_id", "in", batch)
            .stream()
        ):
            data = doc.to_dict()
            if data.get("source_chunk_id") not in chunk_ids_set:
                raw_rels.append(data)

    if not raw_rels:
        return []

    # Collect target chunk IDs we need to resolve
    target_chunk_ids: set = set()
    for rel in raw_rels:
        src_cid = rel.get("source_chunk_id")
        tgt_cid = rel.get("target_chunk_id")
        other = tgt_cid if src_cid in chunk_ids_set else src_cid
        if other:
            target_chunk_ids.add(other)

    # Batch fetch target chunks
    target_chunks = _batch_fetch_chunks(list(target_chunk_ids))

    # Build flat relationship list
    seen = set()
    relationships: List[Dict[str, Any]] = []

    for rel in raw_rels:
        src_cid = rel.get("source_chunk_id", "")
        tgt_cid = rel.get("target_chunk_id", "")

        # Determine "our" side vs "other" side
        if src_cid in chunk_ids_set:
            from_source_id = chunk_to_source.get(src_cid, "")
            other_cid = tgt_cid
        else:
            from_source_id = chunk_to_source.get(tgt_cid, "")
            other_cid = src_cid

        other_chunk = target_chunks.get(other_cid, {})
        target_source_id = other_chunk.get("source_id", "unknown")

        # Skip same-source relationships
        if target_source_id == from_source_id:
            continue

        dedup_key = (from_source_id, target_source_id, rel.get("type", ""))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        relationships.append(
            {
                "from_source_id": from_source_id,
                "target_source_id": target_source_id,
                "target_title": other_chunk.get("title", "Unknown"),
                "target_author": other_chunk.get("author", "Unknown"),
                "target_readwise_url": other_chunk.get("readwise_url", ""),
                "target_source_url": other_chunk.get("source_url", ""),
                "relationship_type": rel.get("type", "unknown"),
                "explanation": rel.get("explanation", ""),
            }
        )

    logger.info(f"Fetched {len(relationships)} cross-source relationships")
    return relationships


def _batch_fetch_chunks(chunk_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Batch fetch chunks by ID using Firestore get_all()."""
    if not chunk_ids:
        return {}

    db = _get_db()
    collection = _get_collection()

    result: Dict[str, Dict[str, Any]] = {}
    # Firestore get_all max ~100
    for i in range(0, len(chunk_ids), 100):
        batch = chunk_ids[i : i + 100]
        refs = [db.collection(collection).document(cid) for cid in batch]
        for doc in db.get_all(refs):
            if doc.exists:
                data = doc.to_dict()
                data["id"] = doc.id
                result[doc.id] = data

    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def collect_summary_data(days: int = 7, limit: int = 100) -> Dict[str, Any]:
    """
    Collect all data needed for weekly summary generation.

    Returns a structured dict with period, stats, sources (with knowledge cards),
    and cross-source relationships.
    """
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=days)

    # 1. Fetch recent chunks
    chunks = fetch_recent_chunks(days=days, limit=limit)

    if not chunks:
        return {
            "period": {
                "start": start_dt.strftime("%Y-%m-%d"),
                "end": now.strftime("%Y-%m-%d"),
                "days": days,
            },
            "stats": {
                "total_chunks": 0,
                "total_sources": 0,
                "total_highlights": 0,
                "total_relationships": 0,
                "source_types": {},
            },
            "sources": [],
            "relationships": [],
        }

    # 2. Group chunks by source_id
    chunks_by_source: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in chunks:
        sid = chunk.get("source_id", "unknown")
        chunks_by_source.setdefault(sid, []).append(chunk)

    # 3. Build sources list with metadata and knowledge cards
    source_type_counts: Dict[str, int] = {}
    sources: List[Dict[str, Any]] = []

    for source_id, source_chunks in chunks_by_source.items():
        first_chunk = source_chunks[0]
        stype = detect_source_type(first_chunk)
        source_type_counts[stype] = source_type_counts.get(stype, 0) + 1

        formatted_chunks = []
        for c in source_chunks:
            kc = c.get("knowledge_card")
            formatted_chunks.append(
                {
                    "chunk_id": c.get("id", ""),
                    "knowledge_card": {
                        "summary": kc.get("summary", "") if kc else "",
                        "takeaways": kc.get("takeaways", []) if kc else [],
                    },
                    "highlight_url": c.get("highlight_url", ""),
                }
            )

        sources.append(
            {
                "source_id": source_id,
                "title": first_chunk.get("title", "Untitled"),
                "author": first_chunk.get("author", "Unknown"),
                "type": stype,
                "readwise_url": first_chunk.get("readwise_url", ""),
                "source_url": resolve_url(first_chunk),
                "chunks": formatted_chunks,
            }
        )

    # 4. Fetch relationships
    relationships = fetch_relationships_for_sources(
        list(chunks_by_source.keys()), chunks_by_source
    )

    # Add from_title to relationships
    source_titles = {s["source_id"]: s["title"] for s in sources}
    for rel in relationships:
        rel["from_title"] = source_titles.get(rel["from_source_id"], "Unknown")

    # 5. Build output
    return {
        "period": {
            "start": start_dt.strftime("%Y-%m-%d"),
            "end": now.strftime("%Y-%m-%d"),
            "days": days,
        },
        "stats": {
            "total_chunks": len(chunks),
            "total_sources": len(sources),
            "total_highlights": len(chunks),
            "total_relationships": len(relationships),
            "source_types": source_type_counts,
        },
        "sources": sources,
        "relationships": relationships,
    }
