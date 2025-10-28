# Implementierungsplan: Chunking-Strategie für Embedding-Funktion

**Projekt:** KX-Hub Knowledge Base
**Feature:** Semantic Highlight-Level Chunking
**Autor:** Claude (Automatisch generiert)
**Datum:** 2025-10-28
**Version:** 1.0

---

## Übersicht

Dieser Plan beschreibt die schrittweise Implementierung der Chunking-Strategie für die Embedding-Funktion, basierend auf der [Chunking-Strategie-Analyse](../analysis/chunking-strategy-analysis.md).

**Ziel:** Migration von Document-Level zu Chunk-Level Embeddings für bessere Retrieval-Qualität und Performance.

**Zeitrahmen:** 10-12 Wochen
**Geschätzte Entwicklungszeit:** 40-60 Entwicklungsstunden

---

## Phase 1: Prototype & Validation (Woche 1-2)

### Ziel
Proof of Concept mit realen Daten validieren

### Tasks

#### 1.1 Highlight-Extraktion implementieren
**Datei:** `src/embed/chunk_utils.py` (neu)

**Funktionen:**
```python
def extract_highlights_from_markdown(markdown_content: str) -> List[dict]:
    """
    Extrahiert Highlights aus Markdown-Content.

    Args:
        markdown_content: Der Markdown-Body (ohne Frontmatter)

    Returns:
        Liste von Highlight-Dicts mit Keys:
        - text: str (Highlight-Text)
        - location: int (optional)
        - location_type: str (optional)
        - note: str (optional)
        - highlighted_at: str (ISO timestamp)

    Example Input:
        > Highlight text here
        > - Location: 1081
        > - Highlighted: 2024-06-01T04:56:00Z

        > Another highlight
        > - Note: My note
        > - Location: 1599

    Example Output:
        [
            {
                'text': 'Highlight text here',
                'location': 1081,
                'highlighted_at': '2024-06-01T04:56:00Z'
            },
            {
                'text': 'Another highlight',
                'location': 1599,
                'note': 'My note'
            }
        ]
    """
    highlights = []
    current_highlight = None
    in_blockquote = False

    for line in markdown_content.split('\n'):
        line_stripped = line.strip()

        # Start of highlight (blockquote without metadata marker)
        if line_stripped.startswith('> ') and not line_stripped.startswith('> -'):
            if not in_blockquote:
                # New highlight
                if current_highlight:
                    highlights.append(current_highlight)
                current_highlight = {'text': line_stripped[2:]}
                in_blockquote = True
            else:
                # Continuation of highlight text
                current_highlight['text'] += ' ' + line_stripped[2:]

        # Metadata lines
        elif line_stripped.startswith('> - Location:'):
            location_str = line_stripped.split(':', 1)[1].strip()
            try:
                current_highlight['location'] = int(location_str)
                current_highlight['location_type'] = 'kindle_location'
            except ValueError:
                pass  # Skip invalid locations

        elif line_stripped.startswith('> - Highlighted:'):
            timestamp = line_stripped.split(':', 1)[1].strip()
            current_highlight['highlighted_at'] = timestamp

        elif line_stripped.startswith('> - Note:'):
            note = line_stripped.split(':', 1)[1].strip()
            current_highlight['note'] = note

        # End of blockquote (empty line)
        elif line_stripped == '' and in_blockquote:
            if current_highlight:
                highlights.append(current_highlight)
                current_highlight = None
            in_blockquote = False

    # Don't forget last highlight
    if current_highlight:
        highlights.append(current_highlight)

    return highlights
```

**Tests:** `tests/test_chunk_utils.py`
```python
def test_extract_highlights_from_markdown():
    markdown = """
# Title

## Highlights

> First highlight text
> - Location: 1081
> - Highlighted: 2024-06-01T04:56:00Z

> Second highlight text
> - Note: My note
> - Location: 1599
> - Highlighted: 2024-06-01T04:57:00Z
"""
    highlights = extract_highlights_from_markdown(markdown)
    assert len(highlights) == 2
    assert highlights[0]['text'] == 'First highlight text'
    assert highlights[0]['location'] == 1081
    assert highlights[1]['note'] == 'My note'
```

**Acceptance Criteria:**
- ✅ Extrahiert alle Highlights korrekt
- ✅ Parsed Location, Note, Timestamp
- ✅ Handhabt mehrzeilige Highlights
- ✅ Tests mit 3+ Fixture-Files erfolgreich

---

#### 1.2 Chunk-Erstellung implementieren
**Datei:** `src/embed/chunk_utils.py`

**Funktion:**
```python
def create_highlight_chunk(
    metadata: dict,
    highlight: dict,
    index: int
) -> dict:
    """
    Erstellt einen Chunk für ein einzelnes Highlight.

    Args:
        metadata: Document metadata (aus parse_markdown)
        highlight: Highlight dict (aus extract_highlights_from_markdown)
        index: Highlight-Index (1-based)

    Returns:
        Chunk dict mit allen Firestore-Fields
    """
    chunk_id = f"{metadata['id']}-h{index}"

    chunk = {
        # Identity
        'chunk_id': chunk_id,
        'document_id': metadata['id'],
        'chunk_type': 'highlight',
        'chunk_index': index,

        # Content
        'highlight_text': highlight['text'],
        'highlight_location': highlight.get('location'),
        'highlight_location_type': highlight.get('location_type', 'unknown'),
        'highlight_note': highlight.get('note'),
        'highlighted_at': highlight.get('highlighted_at'),

        # Parent Document Context
        'document_title': metadata['title'],
        'document_author': metadata['author'],
        'document_source': metadata['source'],
        'document_url': metadata.get('url'),
        'document_tags': metadata.get('tags', []),
        'document_category': metadata.get('category'),

        # Timestamps
        'created_at': metadata.get('created_at'),
        'updated_at': metadata.get('updated_at')
    }

    return chunk


def format_chunk_for_embedding(chunk: dict) -> str:
    """
    Formatiert Chunk als String für Embedding (mit Context Enrichment).

    Args:
        chunk: Chunk dict (aus create_highlight_chunk)

    Returns:
        Formatted text für generate_embedding()

    Example Output:
        Title: Geschwister Als Team
        Author: Nicola Schmidt
        Source: kindle
        Tags: parenting, psychology

        Highlight:
        Strafen helfen nachweislich nicht. Auch wenn der Impuls...

        Note: Important insight about aggression
    """
    parts = [
        f"Title: {chunk['document_title']}",
        f"Author: {chunk['document_author']}",
        f"Source: {chunk['document_source']}"
    ]

    if chunk['document_tags']:
        parts.append(f"Tags: {', '.join(chunk['document_tags'])}")

    parts.append("")  # Empty line
    parts.append("Highlight:")
    parts.append(chunk['highlight_text'])

    if chunk.get('highlight_note'):
        parts.append("")
        parts.append(f"Note: {chunk['highlight_note']}")

    return "\n".join(parts)
```

**Tests:**
```python
def test_create_highlight_chunk():
    metadata = {
        'id': '41094950',
        'title': 'Test Book',
        'author': 'Test Author',
        'source': 'kindle',
        'tags': ['test'],
        'created_at': '2024-06-01T00:00:00Z'
    }
    highlight = {
        'text': 'Test highlight',
        'location': 1081
    }
    chunk = create_highlight_chunk(metadata, highlight, 1)

    assert chunk['chunk_id'] == '41094950-h1'
    assert chunk['document_id'] == '41094950'
    assert chunk['highlight_text'] == 'Test highlight'
    assert chunk['document_title'] == 'Test Book'


def test_format_chunk_for_embedding():
    chunk = {
        'document_title': 'Test',
        'document_author': 'Author',
        'document_source': 'kindle',
        'document_tags': ['tag1'],
        'highlight_text': 'Highlight text',
        'highlight_note': 'My note'
    }
    text = format_chunk_for_embedding(chunk)

    assert 'Title: Test' in text
    assert 'Highlight:' in text
    assert 'Highlight text' in text
    assert 'Note: My note' in text
```

**Acceptance Criteria:**
- ✅ Chunk enthält alle Required Fields
- ✅ chunk_id Format korrekt (`{doc_id}-h{index}`)
- ✅ Context Enrichment korrekt formatiert
- ✅ Tests erfolgreich

---

#### 1.3 Token-Counting Funktion
**Datei:** `src/embed/chunk_utils.py`

**Funktion:**
```python
def estimate_token_count(text: str) -> int:
    """
    Schätzt Token-Count für Text (konservative Schätzung).

    Args:
        text: Input text

    Returns:
        Geschätzte Anzahl Tokens

    Note:
        Verwendet einfache Heuristik: 1 Token ≈ 0.75 Wörter
        Für Deutsch etwas konservativer: 1 Token ≈ 0.7 Wörter
    """
    # Simple word-based estimation
    words = len(text.split())
    # Conservative estimate for German
    estimated_tokens = int(words / 0.7)
    return estimated_tokens


def validate_chunk_token_limit(chunk_text: str, max_tokens: int = 2048) -> bool:
    """
    Validiert, dass Chunk unter Token-Limit liegt.

    Args:
        chunk_text: Formatted chunk text (aus format_chunk_for_embedding)
        max_tokens: Maximum allowed tokens (default: 2048)

    Returns:
        True wenn unter Limit, sonst False

    Raises:
        ValueError: Wenn Chunk Token-Limit überschreitet
    """
    token_count = estimate_token_count(chunk_text)

    if token_count > max_tokens:
        raise ValueError(
            f"Chunk exceeds token limit: {token_count} > {max_tokens}. "
            f"Text length: {len(chunk_text)} characters"
        )

    return True
```

**Tests:**
```python
def test_estimate_token_count():
    text = "This is a test " * 100  # 400 words
    tokens = estimate_token_count(text)
    assert 500 < tokens < 600  # ~571 tokens


def test_validate_chunk_token_limit_ok():
    short_text = "Short text"
    assert validate_chunk_token_limit(short_text) is True


def test_validate_chunk_token_limit_exceeds():
    long_text = "word " * 2000  # ~2857 tokens
    with pytest.raises(ValueError, match="exceeds token limit"):
        validate_chunk_token_limit(long_text)
```

**Acceptance Criteria:**
- ✅ Token-Schätzung im ±20% Bereich
- ✅ Validation wirft Exception bei Überschreitung
- ✅ Tests erfolgreich

---

#### 1.4 Integration in embed/main.py (Prototype)
**Datei:** `src/embed/main.py`

**Neue Funktion:**
```python
from .chunk_utils import (
    extract_highlights_from_markdown,
    create_highlight_chunk,
    format_chunk_for_embedding,
    validate_chunk_token_limit
)


def embed_document_chunked(
    markdown: str,
    run_id: str,
    dry_run: bool = False
) -> dict:
    """
    Embed Document mit Chunking-Strategie (PROTOTYPE).

    Args:
        markdown: Full markdown content (mit Frontmatter)
        run_id: Pipeline run ID
        dry_run: Wenn True, nur simulieren (kein Firestore/Vector Search)

    Returns:
        Stats dict mit:
        - document_id: str
        - chunk_count: int
        - chunks_embedded: int
        - chunks_skipped: int (token limit exceeded)
        - total_tokens: int

    Raises:
        ValueError: Bei invalid markdown format
    """
    # Parse markdown
    metadata, markdown_content = parse_markdown(markdown)
    document_id = metadata['id']

    logger.info(f"[Chunked] Processing document {document_id}")

    # Extract highlights
    highlights = extract_highlights_from_markdown(markdown_content)
    logger.info(f"[Chunked] Extracted {len(highlights)} highlights")

    if not highlights:
        logger.warning(f"[Chunked] No highlights found in {document_id}")
        return {
            'document_id': document_id,
            'chunk_count': 0,
            'chunks_embedded': 0,
            'chunks_skipped': 0,
            'total_tokens': 0
        }

    # Create and embed chunks
    chunks_embedded = 0
    chunks_skipped = 0
    total_tokens = 0

    for i, highlight in enumerate(highlights, start=1):
        chunk = create_highlight_chunk(metadata, highlight, i)
        chunk_text = format_chunk_for_embedding(chunk)

        # Token validation
        try:
            validate_chunk_token_limit(chunk_text)
            token_count = estimate_token_count(chunk_text)
            total_tokens += token_count
        except ValueError as e:
            logger.warning(f"[Chunked] Skipping chunk {chunk['chunk_id']}: {e}")
            chunks_skipped += 1
            continue

        if dry_run:
            logger.info(f"[DRY RUN] Would embed {chunk['chunk_id']} (~{token_count} tokens)")
            chunks_embedded += 1
            continue

        # Generate embedding
        try:
            embedding_vector = generate_embedding(chunk_text)

            # Upsert to Vector Search
            upsert_to_vector_search(
                item_id=chunk['chunk_id'],
                embedding_vector=embedding_vector,
                run_id=run_id
            )

            # TODO: Upsert to Firestore kb_chunks collection (Phase 2)

            chunks_embedded += 1
            logger.debug(f"[Chunked] Embedded {chunk['chunk_id']}")

        except Exception as e:
            logger.error(f"[Chunked] Failed to embed {chunk['chunk_id']}: {e}")
            chunks_skipped += 1

    stats = {
        'document_id': document_id,
        'chunk_count': len(highlights),
        'chunks_embedded': chunks_embedded,
        'chunks_skipped': chunks_skipped,
        'total_tokens': total_tokens
    }

    logger.info(f"[Chunked] Completed {document_id}: {stats}")
    return stats
```

**Tests:**
```python
def test_embed_document_chunked_dry_run(sample_markdown):
    stats = embed_document_chunked(sample_markdown, run_id='test-run', dry_run=True)

    assert stats['document_id'] == '41094950'
    assert stats['chunk_count'] == 3
    assert stats['chunks_embedded'] == 3
    assert stats['chunks_skipped'] == 0
    assert stats['total_tokens'] > 0
```

**Acceptance Criteria:**
- ✅ Prototype läuft fehlerfrei (dry_run)
- ✅ Alle Highlights werden verarbeitet
- ✅ Stats korrekt
- ✅ Logging aussagekräftig

---

#### 1.5 Vergleichstest: Document vs Chunk
**Datei:** `tests/test_chunking_comparison.py`

**Test:**
```python
def test_document_vs_chunk_embeddings(sample_book_with_many_highlights):
    """
    Vergleiche Document-Level vs Chunk-Level Embeddings.

    Metriken:
    1. Token Coverage (% der Highlights im Embedding)
    2. Token Count (total tokens embedded)
    3. Embedding Count (Anzahl Embeddings)
    """
    markdown = sample_book_with_many_highlights  # 50+ highlights

    # Document-Level (existing)
    doc_stats = embed_document_original(markdown, run_id='doc-test')

    # Chunk-Level (new)
    chunk_stats = embed_document_chunked(markdown, run_id='chunk-test', dry_run=True)

    # Assertions
    assert chunk_stats['total_tokens'] > doc_stats['total_tokens'], \
        "Chunked should embed MORE tokens (no truncation)"

    assert chunk_stats['chunks_embedded'] == 50, \
        "Should embed all 50 highlights"

    assert doc_stats['embeddings'] == 1, \
        "Document-level creates 1 embedding"

    assert chunk_stats['chunks_embedded'] == 50, \
        "Chunk-level creates 50 embeddings"

    # Token coverage
    doc_coverage = min(2048, doc_stats['total_tokens']) / doc_stats['total_tokens']
    chunk_coverage = 1.0  # All chunks embedded

    print(f"Document-Level Token Coverage: {doc_coverage:.1%}")
    print(f"Chunk-Level Token Coverage: {chunk_coverage:.1%}")

    assert chunk_coverage > doc_coverage, \
        "Chunk-level should have better token coverage"
```

**Acceptance Criteria:**
- ✅ Test zeigt Chunk-Level Vorteile klar
- ✅ Token Coverage: Chunk > Document
- ✅ Metriken dokumentiert

---

### Deliverables Phase 1
- [ ] `src/embed/chunk_utils.py` mit allen Helper Functions
- [ ] `tests/test_chunk_utils.py` mit ≥90% Coverage
- [ ] `tests/test_chunking_comparison.py` mit Vergleichstest
- [ ] Prototype `embed_document_chunked()` in `src/embed/main.py`
- [ ] Test-Report mit Metriken (Token Coverage, Latenz, etc.)

### Success Criteria Phase 1
- ✅ Alle Tests erfolgreich
- ✅ Chunk-Level zeigt +30% Token Coverage vs Document-Level
- ✅ Alle Chunks unter 2.048 Token-Limit
- ✅ Code Review approved

---

## Phase 2: Schema & Infrastructure (Woche 3-4)

### Ziel
Production-ready Datenmodell und Firestore Setup

### Tasks

#### 2.1 Firestore Collection `kb_chunks` erstellen
**Datei:** `scripts/setup_firestore_schema.py` (neu)

**Schema:**
```python
from google.cloud import firestore

def create_kb_chunks_collection():
    """
    Erstellt kb_chunks Collection mit Indizes.
    """
    db = firestore.Client()

    # Collection wird automatisch erstellt beim ersten Write
    # Aber wir erstellen Indizes proaktiv

    # Index 1: document_id (für Parent Lookup)
    # Index 2: embedding_status (für Processing Queries)
    # Index 3: updated_at (für Sorting)
    # Index 4: Composite: document_id + chunk_index (für geordneten Abruf)

    print("Collection kb_chunks bereit.")
    print("WICHTIG: Indizes manuell in Firebase Console erstellen:")
    print("  1. Single Field Index: document_id")
    print("  2. Single Field Index: embedding_status")
    print("  3. Single Field Index: updated_at")
    print("  4. Composite Index: document_id ASC, chunk_index ASC")

    # Example document schreiben (für Index-Erstellung)
    example_chunk = {
        'chunk_id': 'example-h1',
        'document_id': 'example',
        'chunk_type': 'highlight',
        'chunk_index': 1,
        'highlight_text': 'Example highlight text',
        'document_title': 'Example Book',
        'document_author': 'Example Author',
        'document_source': 'kindle',
        'document_tags': [],
        'embedding_status': 'pending',
        'created_at': firestore.SERVER_TIMESTAMP,
        'updated_at': firestore.SERVER_TIMESTAMP
    }

    db.collection('kb_chunks').document('example-h1').set(example_chunk)
    print("Example document erstellt: example-h1")
```

**Firestore Indexes (firestore.indexes.json):**
```json
{
  "indexes": [
    {
      "collectionGroup": "kb_chunks",
      "queryScope": "COLLECTION",
      "fields": [
        {
          "fieldPath": "document_id",
          "order": "ASCENDING"
        },
        {
          "fieldPath": "chunk_index",
          "order": "ASCENDING"
        }
      ]
    },
    {
      "collectionGroup": "kb_chunks",
      "queryScope": "COLLECTION",
      "fields": [
        {
          "fieldPath": "embedding_status",
          "order": "ASCENDING"
        },
        {
          "fieldPath": "updated_at",
          "order": "DESCENDING"
        }
      ]
    }
  ],
  "fieldOverrides": []
}
```

**Deployment:**
```bash
gcloud firestore indexes create --file=firestore.indexes.json --project=kx-hub
```

**Acceptance Criteria:**
- ✅ Collection `kb_chunks` existiert
- ✅ Alle Indizes deployed
- ✅ Example document erfolgreich geschrieben

---

#### 2.2 Update `kb_items` Collection Schema
**Datei:** `src/embed/firestore_utils.py` (erweitern)

**Neue Fields:**
```python
def update_document_with_chunks(
    document_id: str,
    chunk_count: int,
    chunk_ids: List[str]
) -> None:
    """
    Aktualisiert kb_items Document mit Chunk-Informationen.

    Args:
        document_id: Document ID
        chunk_count: Anzahl Chunks
        chunk_ids: Liste von Chunk IDs
    """
    db = get_firestore_client()
    doc_ref = db.collection('kb_items').document(document_id)

    doc_ref.update({
        'chunk_count': chunk_count,
        'chunk_ids': chunk_ids,
        'last_chunked_at': firestore.SERVER_TIMESTAMP
    })

    logger.info(f"Updated document {document_id} with {chunk_count} chunks")
```

**Migration Script für Existing Documents:**
```python
def migrate_existing_documents_schema():
    """
    Fügt neue Fields zu allen existierenden kb_items hinzu.
    """
    db = get_firestore_client()
    docs = db.collection('kb_items').stream()

    updated = 0
    for doc in docs:
        doc.reference.update({
            'chunk_count': 0,
            'chunk_ids': [],
            'last_chunked_at': None
        })
        updated += 1

    logger.info(f"Migrated {updated} documents")
```

**Acceptance Criteria:**
- ✅ Migration Script erfolgreich
- ✅ Alle kb_items haben neue Fields
- ✅ Keine Datenverluste

---

#### 2.3 Firestore Security Rules
**Datei:** `firestore.rules`

**Rules für kb_chunks:**
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Existing rules für kb_items...

    // Rules für kb_chunks
    match /kb_chunks/{chunkId} {
      // Nur Cloud Functions dürfen lesen/schreiben
      allow read, write: if false;
    }

    // Exception: Service Account via Admin SDK (Cloud Functions)
    // → Implicitly allowed durch Admin SDK, keine explizite Rule nötig
  }
}
```

**Deployment:**
```bash
firebase deploy --only firestore:rules --project=kx-hub
```

**Acceptance Criteria:**
- ✅ Rules deployed
- ✅ Public Access blockiert
- ✅ Cloud Functions können lesen/schreiben

---

#### 2.4 Vector Search Configuration Check
**Task:** Prüfe, ob bestehender Index Chunk-IDs unterstützt

**Check:**
```python
def test_vector_search_chunk_ids():
    """
    Testet, ob Vector Search Chunk-IDs (Format: {doc_id}-h{index}) akzeptiert.
    """
    index_endpoint = get_vector_search_client()

    # Test Upsert mit Chunk-ID
    test_datapoint = aiplatform.MatchingEngineIndexEndpoint.Datapoint(
        datapoint_id='test-doc-h1',
        feature_vector=[0.1] * 768,
        crowding_tag='test-doc'
    )

    try:
        index_endpoint.upsert_datapoints(
            deployed_index_id=VECTOR_SEARCH_DEPLOYED_INDEX_ID,
            datapoints=[test_datapoint]
        )
        print("✅ Vector Search akzeptiert Chunk-IDs")
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
```

**Acceptance Criteria:**
- ✅ Test erfolgreich
- ✅ Chunk-IDs funktionieren mit bestehender Konfiguration

---

### Deliverables Phase 2
- [ ] Firestore Collection `kb_chunks` mit Indizes
- [ ] Schema Migration für `kb_items`
- [ ] Firestore Security Rules deployed
- [ ] Vector Search Configuration validiert
- [ ] Documentation: Schema & Index Übersicht

### Success Criteria Phase 2
- ✅ Infrastruktur production-ready
- ✅ Alle Tests erfolgreich
- ✅ Security Rules korrekt

---

## Phase 3: Embedding Pipeline Refactoring (Woche 5-6)

### Ziel
Produktionsreife Chunking-Pipeline

### Tasks

#### 3.1 Firestore Chunk Operations
**Datei:** `src/embed/firestore_utils.py` (erweitern)

**Funktionen:**
```python
def upsert_chunk_to_firestore(chunk_id: str, chunk: dict, embedding_status: str) -> None:
    """
    Schreibt Chunk in kb_chunks Collection.

    Args:
        chunk_id: Chunk ID (z.B. "41094950-h3")
        chunk: Chunk dict (aus create_highlight_chunk)
        embedding_status: "complete" | "pending" | "failed"
    """
    db = get_firestore_client()

    # Compute content hash
    chunk_text = format_chunk_for_embedding(chunk)
    content_hash = _compute_markdown_hash(chunk_text)

    doc_data = {
        'chunk_id': chunk['chunk_id'],
        'document_id': chunk['document_id'],
        'chunk_type': chunk['chunk_type'],
        'chunk_index': chunk['chunk_index'],

        'highlight_text': chunk['highlight_text'],
        'highlight_location': chunk.get('highlight_location'),
        'highlight_location_type': chunk.get('highlight_location_type'),
        'highlight_note': chunk.get('highlight_note'),
        'highlighted_at': chunk.get('highlighted_at'),

        'document_title': chunk['document_title'],
        'document_author': chunk['document_author'],
        'document_source': chunk['document_source'],
        'document_url': chunk.get('document_url'),
        'document_tags': chunk['document_tags'],
        'document_category': chunk.get('document_category'),

        'content_hash': content_hash,
        'embedding_status': embedding_status,
        'last_embedded_at': firestore.SERVER_TIMESTAMP if embedding_status == 'complete' else None,

        'created_at': chunk.get('created_at'),
        'updated_at': chunk.get('updated_at')
    }

    db.collection('kb_chunks').document(chunk_id).set(doc_data)
    logger.debug(f"Upserted chunk {chunk_id} to Firestore")


def get_chunk_from_firestore(chunk_id: str) -> Optional[dict]:
    """
    Holt Chunk aus Firestore.

    Args:
        chunk_id: Chunk ID

    Returns:
        Chunk dict oder None wenn nicht vorhanden
    """
    db = get_firestore_client()
    doc = db.collection('kb_chunks').document(chunk_id).get()

    if not doc.exists:
        return None

    return doc.to_dict()


def get_chunks_by_document(document_id: str) -> List[dict]:
    """
    Holt alle Chunks für ein Dokument (geordnet nach chunk_index).

    Args:
        document_id: Document ID

    Returns:
        Liste von Chunk dicts
    """
    db = get_firestore_client()
    chunks = (
        db.collection('kb_chunks')
        .where('document_id', '==', document_id)
        .order_by('chunk_index')
        .stream()
    )

    return [chunk.to_dict() for chunk in chunks]
```

**Acceptance Criteria:**
- ✅ CRUD Operations funktionieren
- ✅ Content Hash Tracking funktioniert
- ✅ Queries mit Indizes optimiert

---

#### 3.2 Delta Processing für Chunks
**Datei:** `src/embed/main.py` (erweitern)

**Logic:**
```python
def should_re_embed_chunk(chunk_id: str, new_content_hash: str) -> bool:
    """
    Prüft, ob Chunk re-embedded werden muss.

    Args:
        chunk_id: Chunk ID
        new_content_hash: Neuer Content Hash

    Returns:
        True wenn re-embedding nötig
    """
    existing_chunk = get_chunk_from_firestore(chunk_id)

    if not existing_chunk:
        # Chunk existiert noch nicht
        return True

    if existing_chunk.get('embedding_status') != 'complete':
        # Embedding nicht vollständig
        return True

    old_hash = existing_chunk.get('content_hash')
    if old_hash != new_content_hash:
        # Content hat sich geändert
        logger.info(f"Content changed for {chunk_id}, re-embedding")
        return True

    # Alles unverändert, skip
    return False
```

**Integration in embed_document_chunked:**
```python
def embed_document_chunked(markdown: str, run_id: str, force: bool = False) -> dict:
    # ... (existing code)

    for i, highlight in enumerate(highlights, start=1):
        chunk = create_highlight_chunk(metadata, highlight, i)
        chunk_text = format_chunk_for_embedding(chunk)
        content_hash = _compute_markdown_hash(chunk_text)

        # Delta Processing
        if not force and not should_re_embed_chunk(chunk['chunk_id'], content_hash):
            logger.debug(f"Skipping unchanged chunk {chunk['chunk_id']}")
            chunks_skipped += 1
            continue

        # ... (embedding logic)
```

**Acceptance Criteria:**
- ✅ Delta Processing funktioniert
- ✅ Nur geänderte Chunks werden re-embedded
- ✅ Force-Flag überschreibt Delta Logic

---

#### 3.3 Error Handling & Retry Logic
**Datei:** `src/embed/main.py`

**Enhancements:**
```python
def embed_chunk_with_retry(chunk: dict, run_id: str, max_retries: int = 3) -> bool:
    """
    Embeddet Chunk mit Retry-Logic.

    Args:
        chunk: Chunk dict
        run_id: Run ID
        max_retries: Max Versuche

    Returns:
        True bei Erfolg, False bei Failure
    """
    chunk_id = chunk['chunk_id']
    chunk_text = format_chunk_for_embedding(chunk)

    for attempt in range(max_retries):
        try:
            # Token validation
            validate_chunk_token_limit(chunk_text)

            # Generate embedding
            embedding_vector = generate_embedding(chunk_text)

            # Upsert to Vector Search
            upsert_to_vector_search(
                item_id=chunk_id,
                embedding_vector=embedding_vector,
                run_id=run_id
            )

            # Upsert to Firestore
            upsert_chunk_to_firestore(chunk_id, chunk, embedding_status='complete')

            logger.info(f"Successfully embedded {chunk_id}")
            return True

        except ValueError as e:
            # Token limit exceeded - nicht retry-bar
            logger.error(f"Chunk {chunk_id} exceeds token limit: {e}")
            upsert_chunk_to_firestore(chunk_id, chunk, embedding_status='failed')
            return False

        except (ResourceExhausted, InternalServerError) as e:
            if attempt < max_retries - 1:
                backoff = INITIAL_BACKOFF * (2 ** attempt)
                logger.warning(f"Retry {attempt+1}/{max_retries} for {chunk_id} after {backoff}s")
                time.sleep(backoff)
            else:
                logger.error(f"Failed to embed {chunk_id} after {max_retries} attempts: {e}")
                upsert_chunk_to_firestore(chunk_id, chunk, embedding_status='failed')
                return False

        except Exception as e:
            logger.error(f"Unexpected error embedding {chunk_id}: {e}")
            upsert_chunk_to_firestore(chunk_id, chunk, embedding_status='failed')
            return False

    return False
```

**Acceptance Criteria:**
- ✅ Retry Logic funktioniert
- ✅ Failed Chunks werden korrekt markiert
- ✅ Logging aussagekräftig

---

#### 3.4 Batch Processing Optimization
**Datei:** `src/embed/main.py`

**Parallel Chunk Processing:**
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def embed_document_chunked_parallel(
    markdown: str,
    run_id: str,
    max_workers: int = 5
) -> dict:
    """
    Embeddet Document-Chunks parallel.

    Args:
        markdown: Full markdown
        run_id: Run ID
        max_workers: Anzahl paralleler Workers

    Returns:
        Stats dict
    """
    metadata, markdown_content = parse_markdown(markdown)
    highlights = extract_highlights_from_markdown(markdown_content)

    chunks = [
        create_highlight_chunk(metadata, highlight, i+1)
        for i, highlight in enumerate(highlights)
    ]

    # Parallel embedding
    chunks_embedded = 0
    chunks_failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(embed_chunk_with_retry, chunk, run_id): chunk
            for chunk in chunks
        }

        for future in as_completed(futures):
            chunk = futures[future]
            try:
                success = future.result()
                if success:
                    chunks_embedded += 1
                else:
                    chunks_failed += 1
            except Exception as e:
                logger.error(f"Exception for chunk {chunk['chunk_id']}: {e}")
                chunks_failed += 1

    # Update document metadata
    chunk_ids = [c['chunk_id'] for c in chunks]
    update_document_with_chunks(metadata['id'], len(chunks), chunk_ids)

    return {
        'document_id': metadata['id'],
        'chunk_count': len(chunks),
        'chunks_embedded': chunks_embedded,
        'chunks_failed': chunks_failed
    }
```

**Acceptance Criteria:**
- ✅ Parallel Processing funktioniert
- ✅ Rate Limiting wird nicht überschritten
- ✅ Performance-Verbesserung messbar

---

#### 3.5 Integration Tests
**Datei:** `tests/integration/test_embed_chunked.py`

**Tests:**
```python
def test_embed_document_chunked_end_to_end(sample_markdown):
    """
    End-to-End Test: Markdown → Chunks → Embeddings → Firestore → Vector Search
    """
    run_id = f'test-{uuid.uuid4()}'

    # Embed
    stats = embed_document_chunked(sample_markdown, run_id=run_id)

    # Assertions
    assert stats['chunks_embedded'] > 0
    assert stats['chunks_failed'] == 0

    # Verify Firestore
    chunks = get_chunks_by_document(stats['document_id'])
    assert len(chunks) == stats['chunk_count']
    for chunk in chunks:
        assert chunk['embedding_status'] == 'complete'
        assert chunk['content_hash'] is not None

    # Verify Vector Search (optional: Query Test)
    # ...


def test_delta_processing_skips_unchanged(sample_markdown):
    """
    Test: Zweiter Lauf überspringt unveränderte Chunks.
    """
    run_id = 'test-delta'

    # First run
    stats1 = embed_document_chunked(sample_markdown, run_id=run_id)
    embedded_first = stats1['chunks_embedded']

    # Second run (no changes)
    stats2 = embed_document_chunked(sample_markdown, run_id=run_id)
    embedded_second = stats2['chunks_embedded']

    assert embedded_second == 0, "No chunks should be re-embedded"
    assert stats2['chunks_skipped'] == embedded_first
```

**Acceptance Criteria:**
- ✅ Alle Integration Tests erfolgreich
- ✅ End-to-End Flow funktioniert
- ✅ Delta Processing validiert

---

### Deliverables Phase 3
- [ ] Production-ready `embed_document_chunked()` Funktion
- [ ] Firestore Chunk Operations (CRUD)
- [ ] Delta Processing implementiert
- [ ] Error Handling & Retry Logic
- [ ] Batch Processing Optimization
- [ ] Integration Tests (≥90% Coverage)

### Success Criteria Phase 3
- ✅ Pipeline verarbeitet 100% Test-Dokumente korrekt
- ✅ Delta Processing spart >90% redundanter Embeddings
- ✅ Error Rate <5%
- ✅ Code Review approved

---

## Phase 4: Retrieval Implementation (Woche 7-8)

### Ziel
Query Handler mit Chunk-Level Retrieval

### Tasks

#### 4.1 Query Handler Cloud Function
**Datei:** `src/query/main.py` (neu)

**Function:**
```python
import functions_framework
from typing import List, Dict
from google.cloud import aiplatform
from .retrieval import search_chunks, rank_and_deduplicate

@functions_framework.http
def query_handler(request):
    """
    HTTP Cloud Function für Natural Language Queries.

    Request Body:
    {
        "query": "Wie gehe ich mit Aggression um?",
        "top_k": 10,
        "deduplicate": true
    }

    Response:
    {
        "results": [
            {
                "chunk_id": "41094950-h3",
                "document_id": "41094950",
                "document_title": "Geschwister Als Team",
                "document_author": "Nicola Schmidt",
                "highlight_text": "Strafen helfen nachweislich nicht...",
                "score": 0.87
            },
            ...
        ],
        "query_time_ms": 125
    }
    """
    import time
    start_time = time.time()

    # Parse request
    request_json = request.get_json(silent=True)
    query = request_json.get('query')
    top_k = request_json.get('top_k', 10)
    deduplicate = request_json.get('deduplicate', True)

    if not query:
        return {'error': 'Missing query parameter'}, 400

    try:
        # Search
        results = search_chunks(query, top_k=top_k)

        # Deduplicate (optional)
        if deduplicate:
            results = rank_and_deduplicate(results)

        # Response
        query_time_ms = int((time.time() - start_time) * 1000)

        return {
            'results': results,
            'query_time_ms': query_time_ms,
            'result_count': len(results)
        }, 200

    except Exception as e:
        logger.error(f"Query failed: {e}")
        return {'error': str(e)}, 500
```

**Acceptance Criteria:**
- ✅ Cloud Function deployed
- ✅ HTTP Request/Response funktioniert
- ✅ Error Handling korrekt

---

#### 4.2 Vector Search Retrieval
**Datei:** `src/query/retrieval.py` (neu)

**Funktionen:**
```python
def search_chunks(query: str, top_k: int = 10) -> List[Dict]:
    """
    Sucht relevante Chunks via Vector Search.

    Args:
        query: Natural Language Query
        top_k: Anzahl Ergebnisse

    Returns:
        Liste von Chunk-Dicts mit Scores
    """
    # 1. Embed Query
    model = get_vertex_ai_client()
    query_embedding = model.get_embeddings([query])[0].values

    # 2. Vector Search
    index_endpoint = get_vector_search_client()
    response = index_endpoint.find_neighbors(
        deployed_index_id=VECTOR_SEARCH_DEPLOYED_INDEX_ID,
        queries=[query_embedding],
        num_neighbors=top_k
    )

    # 3. Extract Chunk IDs + Scores
    chunk_ids = []
    scores = {}
    for neighbor in response[0]:
        chunk_id = neighbor.id
        score = neighbor.distance  # Cosine distance
        chunk_ids.append(chunk_id)
        scores[chunk_id] = 1 - score  # Convert distance to similarity

    # 4. Fetch Chunk Details from Firestore
    db = get_firestore_client()
    results = []
    for chunk_id in chunk_ids:
        chunk = db.collection('kb_chunks').document(chunk_id).get()
        if chunk.exists:
            chunk_data = chunk.to_dict()
            chunk_data['score'] = scores[chunk_id]
            results.append(chunk_data)

    return results
```

**Acceptance Criteria:**
- ✅ Vector Search funktioniert
- ✅ Firestore Lookup korrekt
- ✅ Scores richtig berechnet

---

#### 4.3 Deduplizierung & Ranking
**Datei:** `src/query/retrieval.py`

**Funktion:**
```python
def rank_and_deduplicate(results: List[Dict], max_per_document: int = 3) -> List[Dict]:
    """
    Dedupliziert Ergebnisse und limitiert pro Dokument.

    Args:
        results: Liste von Chunk-Dicts mit Scores
        max_per_document: Max Chunks pro Dokument in Ergebnissen

    Returns:
        Deduplizierte und ranked Liste
    """
    # Gruppiere nach document_id
    by_document = {}
    for chunk in results:
        doc_id = chunk['document_id']
        if doc_id not in by_document:
            by_document[doc_id] = []
        by_document[doc_id].append(chunk)

    # Sortiere Chunks pro Dokument nach Score
    for doc_id in by_document:
        by_document[doc_id].sort(key=lambda c: c['score'], reverse=True)

    # Interleave: Nehme abwechselnd von verschiedenen Dokumenten
    deduplicated = []
    while len(deduplicated) < len(results):
        added = False
        for doc_id in by_document:
            chunks = by_document[doc_id]
            # Count wie viele Chunks dieses Dokuments schon in Ergebnis
            count = sum(1 for c in deduplicated if c['document_id'] == doc_id)
            if count < max_per_document and chunks:
                deduplicated.append(chunks.pop(0))
                added = True
        if not added:
            break

    return deduplicated
```

**Acceptance Criteria:**
- ✅ Deduplizierung funktioniert
- ✅ Interleaving korrekt
- ✅ Tests erfolgreich

---

#### 4.4 API Documentation
**Datei:** `docs/api/query-handler.md`

**Content:**
```markdown
# Query Handler API

## Endpoint
POST https://europe-west4-kx-hub.cloudfunctions.net/query-handler

## Authentication
(TBD: API Key oder IAM)

## Request
{
    "query": "string (required)",
    "top_k": "integer (optional, default: 10)",
    "deduplicate": "boolean (optional, default: true)"
}

## Response
{
    "results": [
        {
            "chunk_id": "string",
            "document_id": "string",
            "document_title": "string",
            "document_author": "string",
            "highlight_text": "string",
            "highlight_location": "integer",
            "score": "float"
        }
    ],
    "query_time_ms": "integer",
    "result_count": "integer"
}

## Examples
...
```

**Acceptance Criteria:**
- ✅ API dokumentiert
- ✅ Beispiele vorhanden

---

### Deliverables Phase 4
- [ ] Cloud Function `query_handler` deployed
- [ ] Vector Search Retrieval implementiert
- [ ] Deduplizierung & Ranking
- [ ] API Documentation
- [ ] Integration Tests

### Success Criteria Phase 4
- ✅ Query Response Time: <1s (P95)
- ✅ Relevance: ≥80% Top-10 als relevant bewertet
- ✅ Deduplizierung funktioniert korrekt

---

## Phase 5: Backfill & Migration (Woche 9-10)

### Ziel
Alle existierenden Dokumente auf Chunk-Level migrieren

### Tasks

#### 5.1 Migration Script
**Datei:** `scripts/migrate_to_chunks.py`

**Script:**
```python
#!/usr/bin/env python3
"""
Migration Script: Document-Level → Chunk-Level Embeddings

Usage:
    python scripts/migrate_to_chunks.py --batch-size 100 --dry-run
    python scripts/migrate_to_chunks.py --batch-size 100
"""
import argparse
from google.cloud import firestore, storage
from src.embed.main import embed_document_chunked

def migrate_to_chunks(batch_size: int = 100, dry_run: bool = False):
    """
    Migriert alle kb_items zu Chunk-Level Embeddings.
    """
    db = firestore.Client()
    storage_client = storage.Client()

    # Fetch all documents with embedding_status = 'complete'
    docs = db.collection('kb_items').where('embedding_status', '==', 'complete').stream()

    total = 0
    success = 0
    failed = 0

    for doc in docs:
        doc_data = doc.to_dict()
        doc_id = doc.id

        # Check if already migrated
        if doc_data.get('chunk_count', 0) > 0:
            print(f"[SKIP] {doc_id} already migrated")
            continue

        total += 1

        # Fetch markdown from GCS
        markdown_uri = f"gs://{MARKDOWN_BUCKET}/notes/{doc_id}.md"
        try:
            bucket = storage_client.bucket(MARKDOWN_BUCKET)
            blob = bucket.blob(f"notes/{doc_id}.md")
            markdown = blob.download_as_text()
        except Exception as e:
            print(f"[ERROR] Failed to fetch markdown for {doc_id}: {e}")
            failed += 1
            continue

        # Embed with chunking
        try:
            if dry_run:
                print(f"[DRY RUN] Would migrate {doc_id}")
            else:
                run_id = f"migration-{uuid.uuid4()}"
                stats = embed_document_chunked(markdown, run_id=run_id)
                print(f"[SUCCESS] Migrated {doc_id}: {stats}")
                success += 1
        except Exception as e:
            print(f"[ERROR] Failed to embed {doc_id}: {e}")
            failed += 1

        # Batch limit
        if total >= batch_size:
            break

    print(f"\nMigration complete: {success} success, {failed} failed, {total} total")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate documents to chunk-level embeddings')
    parser.add_argument('--batch-size', type=int, default=100, help='Max documents to process')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    args = parser.parse_args()

    migrate_to_chunks(batch_size=args.batch_size, dry_run=args.dry_run)
```

**Acceptance Criteria:**
- ✅ Script läuft fehlerfrei
- ✅ Dry-Run funktioniert
- ✅ Progress Tracking vorhanden

---

#### 5.2 Validation Script
**Datei:** `scripts/validate_migration.py`

**Script:**
```python
def validate_migration():
    """
    Validiert, dass alle Dokumente korrekt migriert wurden.
    """
    db = firestore.Client()

    # Fetch all kb_items
    docs = db.collection('kb_items').stream()

    total = 0
    valid = 0
    invalid = []

    for doc in docs:
        doc_data = doc.to_dict()
        doc_id = doc.id
        total += 1

        chunk_count = doc_data.get('chunk_count', 0)
        chunk_ids = doc_data.get('chunk_ids', [])

        if chunk_count == 0:
            print(f"[WARN] {doc_id} not migrated (chunk_count=0)")
            continue

        # Validate chunk count matches chunk_ids length
        if chunk_count != len(chunk_ids):
            print(f"[ERROR] {doc_id} mismatch: chunk_count={chunk_count}, len(chunk_ids)={len(chunk_ids)}")
            invalid.append(doc_id)
            continue

        # Validate all chunks exist in kb_chunks
        for chunk_id in chunk_ids:
            chunk_doc = db.collection('kb_chunks').document(chunk_id).get()
            if not chunk_doc.exists:
                print(f"[ERROR] Chunk {chunk_id} missing for {doc_id}")
                invalid.append(doc_id)
                break
        else:
            valid += 1

    print(f"\nValidation: {valid}/{total} valid, {len(invalid)} invalid")
    if invalid:
        print(f"Invalid docs: {invalid}")
```

**Acceptance Criteria:**
- ✅ Validation zeigt keine Fehler
- ✅ Alle Chunks vorhanden

---

### Deliverables Phase 5
- [ ] Migration Script `migrate_to_chunks.py`
- [ ] Validation Script `validate_migration.py`
- [ ] Migration Runbook (Anleitung)
- [ ] Post-Migration Report

### Success Criteria Phase 5
- ✅ 100% Dokumente migriert
- ✅ Validation erfolgreich
- ✅ Keine Datenverluste

---

## Phase 6: Monitoring & Optimization (Woche 11-12)

### Ziel
Production Stability & Performance Tuning

### Tasks

#### 6.1 Cloud Monitoring Dashboards
**Setup:**
- **Embedding Pipeline Metrics:**
  - Chunks embedded per minute
  - Embedding latency (P50, P95, P99)
  - Error rate
  - Token usage

- **Retrieval Metrics:**
  - Query latency (P50, P95, P99)
  - Query success rate
  - Results per query
  - Deduplicate rate

- **Storage Metrics:**
  - Firestore reads/writes per day
  - Vector Search query count
  - GCS storage size

**Acceptance Criteria:**
- ✅ Dashboards erstellt
- ✅ Metriken sichtbar

---

#### 6.2 Alerting Rules
**Alerts:**
- Embedding failure rate >5% (15 min window)
- Query latency P95 >1s (15 min window)
- Storage cost >Budget

**Acceptance Criteria:**
- ✅ Alerts konfiguriert
- ✅ Test-Alerts funktionieren

---

#### 6.3 Performance Optimization
**Tasks:**
- Firestore Index Tuning (Query Performance)
- Vector Search Hyperparameter Tuning (Accuracy vs Speed)
- Caching Strategy (Frequent Queries)

**Acceptance Criteria:**
- ✅ Performance-Ziele erreicht

---

### Deliverables Phase 6
- [ ] Cloud Monitoring Dashboards
- [ ] Alerting Rules
- [ ] Performance Optimization Report
- [ ] Documentation & Runbook

### Success Criteria Phase 6
- ✅ Monitoring aktiv
- ✅ Performance-Ziele erreicht
- ✅ Runbook vollständig

---

## Rollout Plan

### Rollout Strategy: Gradual Migration

**Week 1-2:** Prototype (Phase 1)
**Week 3-4:** Infrastructure (Phase 2)
**Week 5-6:** Implementation (Phase 3)
**Week 7-8:** Retrieval (Phase 4)

**Week 9:** Soft Launch
- Migrate 100 Dokumente (Beta)
- Test Retrieval mit Beta-Daten
- User Feedback Collection

**Week 10:** Full Migration
- Migrate alle Dokumente (Batches à 500)
- Monitor Performance
- Rollback Plan bereit

**Week 11-12:** Stabilization
- Monitoring & Optimization
- Bug Fixes
- Documentation

---

## Risiko-Management

### High-Priority Risiken

| Risiko | Mitigation | Owner |
|--------|------------|-------|
| Migration schlägt fehl | Rollback Plan + Staging Environment | Dev Team |
| Performance schlechter als erwartet | Pre-Migration Performance Tests | Dev Team |
| Cost Overrun | Budget Alerts + Gradual Rollout | Product Owner |
| User-Reported Bugs | Beta Testing + Feedback Loop | QA Team |

---

## Success Metrics

### Quantitative Metriken
- Query Response Time P95: <1s ✅
- Retrieval Precision: ≥80% ✅
- Token Coverage: 100% (vs 33%) ✅
- Error Rate: <5% ✅

### Qualitative Metriken
- User Feedback: Positive
- Code Quality: >90% Coverage
- Documentation: Vollständig

---

## Nächste Schritte

1. **Review dieses Dokuments** mit Team
2. **Approval einholen** von Stakeholdern
3. **Phase 1 starten** (Prototype)
4. **Weekly Status Updates** an Team

---

**Bereit für die Implementierung!** 🚀
