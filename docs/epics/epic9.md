# Epic 9: Weekly Knowledge Summary

**Goal:** Automatische wöchentliche Zusammenfassung neuer KB-Inhalte als narrative Synthese mit Cross-Source-Verbindungen. Output: Obsidian Markdown (via Headless Sync) und/oder Readwise Reader.

**Business Value:**
- Passive Wissensvernetzung: "Was ich diese Woche gelernt habe und wie es sich verbindet"
- Redaktionelle Qualität statt Rohdaten — thematische Gruppierung, Fließtext, Takeaways
- Verbindungen aus der Relationships-DB als Hauptmehrwert sichtbar machen
- Podcasts (Snipd) automatisch erkennen und mit 🎙️ markieren

**Status:** Planned

**Prototype:** `/Users/christian/Obsidian/ResearchVault/ResearchVault/Summaries/2026-03-02-knowledge-summary.md`

---

## Modell: `gemini-3.1-pro-preview`

**Qualität über Preis, im Google-Stack** — die Summary erfordert:
1. Thematische Gruppierung von 20-50 Chunks in kohärente Abschnitte
2. Narrative deutsche Texte mit redaktionellem Stil
3. Sinnvolle Integration von DB-Relationships in den Kontext
4. Korrekte Source-Attribution mit externen Links (Readwise, Snipd, Web)

Alle Modelle via Vertex AI (registriert in `src/llm/config.py`):

| Modell (config key) | Vertex AI ID | Kosten/Summary | Bewertung |
|--------|--------------|----------------|-----------|
| **`gemini-3.1-pro-preview`** | `gemini-3.1-pro-preview` | ~$0.06 | **Gewählt** — bestes Gemini, 1M Context, GPQA 94.3% |
| `gemini-3-flash-preview` | `gemini-3-flash-preview` | ~$0.02 | Guter Fallback, etwas schwächer bei Nuancen |
| `gemini-2.5-flash` | `gemini-2.5-flash` | ~$0.01 | Ultimate Fallback, Textqualität niedriger |

**Warum Gemini 3.1 Pro:**
- Bleibt im Google-Stack (kein Cross-Cloud-Call zu Anthropic)
- 1M Context Window — problemlos 50+ Chunks + Relationships in einem Call
- GPQA 94.3% — stärkstes Reasoning aller verfügbaren Modelle
- $2/$12 pro 1M Tokens — 33% günstiger als Claude Sonnet
- ~$0.25/Monat bei wöchentlicher Ausführung
- Region: Global (bereits konfiguriert für Preview-Modelle)

**Kein Fallback** — wenn Vertex AI down ist, hilft ein anderes Modell nicht.

---

## Delivery: Obsidian vs. Reader

### Option A: Obsidian (empfohlen)

**Pro:**
- Reiches Markdown-Rendering: Callouts (`> [!tip]`, `> [!example]`), Frontmatter, Wikilinks
- Integriert in Vault — durchsuchbar, verlinkbar, Teil des Second Brain
- Prototype sieht exzellent aus

**Contra:**
- Erfordert Obsidian Headless Sync für serverlose Ausführung
- Zusätzliche Infrastruktur: Cloud Run + GCS FUSE + Obsidian Sync Token

**Architektur (Headless Sync):**
```
Cloud Scheduler (wöchentlich)
  → Cloud Function: Summary generieren (Gemini 3.1 Pro)
  → Cloud Run Container:
      1. GCS FUSE mountet Vault-Bucket
      2. obsidian-sync --once (pull)
      3. Summary als .md schreiben
      4. obsidian-sync --once (push)
  → Obsidian App (iOS/Desktop) zeigt Summary
```

Kritische Config:
- Concurrency: 1 (keine parallelen Syncs)
- GCS Bucket als Vault-Speicher
- `OBSIDIAN_AUTH_TOKEN` via Secret Manager
- Timeout: 5-10 Min für initialen Sync

Siehe: `Obsidian Headless Sync.md` im ResearchVault

### Option B: Readwise Reader

**Pro:**
- API bereits integriert (Epic 12, `readwise_writer.py`)
- Kein zusätzlicher Infra-Aufwand
- Mobil sofort verfügbar
- Tag `ai-weekly-summary` für Organisation

**Contra:**
- Kein Callout-Support (Reader zeigt Markdown einfacher)
- Nicht im Obsidian Vault integriert
- Weniger reiches Rendering

**Architektur:**
```
Cloud Scheduler (wöchentlich)
  → Cloud Function:
      1. Summary generieren (Gemini 3.1 Pro)
      2. POST /api/v3/save/ → Reader Inbox
      3. Tag: ai-weekly-summary
```

### Empfehlung

**Beide parallel** — Obsidian als primäres Archiv (reiches Format), Reader als mobiler Zugang.
Obsidian-Delivery ist komplexer und kann als separater Story nachgezogen werden.

---

## Output-Format (Prototype)

```markdown
---
tags:
  - ai-weekly-summary
date: 2026-03-02
period: 2026-02-28 to 2026-03-02
sources: 7
highlights: 27
connections: 12
---

# Knowledge Summary: 28. Feb – 2. Mar 2026

**27 neue Highlights** aus 7 Quellen (1 Buch, 4 Artikel, 2 🎙️ Podcasts) · **12 Verbindungen**

---

## [Thematischer Abschnitt]

[Narrative Zusammenfassung der Quellen zum Thema]

> [!tip] Takeaway
> [Kernaussage / So-What]

> [!example] Verbindungen aus der KB
> - **Extends** [Source Title](readwise/snipd URL) (Author) — Erklärung
> - 🎙️ **Contradicts** [Podcast Title](snipd URL) — Erklärung

**Quellen:**
- [Title](readwise URL) · [Original](original URL)
- 🎙️ [Podcast](snipd URL)

---

*Generiert aus N Quellen via kx-hub · M Cross-Source-Verbindungen (K 🎙️ Podcasts)*
```

**Format-Regeln:**
- Frontmatter: tags, date, period, sources, highlights, connections
- Thematische Abschnitte (2-5 je nach Inhalt), nicht pro Source
- Callouts: `[!tip]` für Takeaways, `[!example]` für Verbindungen
- Links: Readwise URLs für Artikel/Bücher, Snipd URLs für Podcasts, Original-URLs wo verfügbar
- 🎙️ Icon für Podcast-Quellen (erkannt via `source_url` containing `share.snipd.com`)
- 📖 Icon für Bücher (erkannt via Readwise `category == "books"`)
- Sprache: Deutsch

---

## Stories

### Story 9.1: Summary Data Pipeline

**Beschreibung:** Cloud Function die KB-Daten für die Summary sammelt und aufbereitet.

**Tasks:**
1. [ ] Firestore-Query: Chunks der letzten N Tage (konfigurierbar, default 7)
2. [ ] Unique Sources extrahieren mit Typ-Erkennung (Artikel, Buch, Podcast)
3. [ ] Podcast-Erkennung: `source_url` contains `share.snipd.com`
4. [ ] Für jede Source: Relationships aus `relationships` Collection laden (batch IN-Query)
5. [ ] Relationship-URLs auflösen: Readwise URL, Snipd URL, oder Original-URL
6. [ ] Daten als strukturiertes Dict für LLM-Prompt aufbereiten

**Acceptance Criteria:**
- [ ] Alle Chunks der Periode gesammelt
- [ ] Source-Typen korrekt erkannt (Artikel, Buch, Podcast)
- [ ] Relationships mit korrekten externen URLs aufgelöst
- [ ] Performance: < 10s für typische Woche (50 Chunks, 10 Sources)

---

### Story 9.2: LLM Summary Generation

**Beschreibung:** Gemini 3.1 Pro generiert die narrative Summary aus den aufbereiteten Daten.

**Tasks:**
1. [ ] Summary-Modell konfigurierbar: Default `gemini-3.1-pro-preview`, Override via `SUMMARY_MODEL` env var
2. [ ] LLM-Aufruf über bestehende `src/llm/` Abstraktion (`get_client()` + `generate()`)
3. [ ] Summary-Prompt entwickeln:
   - Input: Chunks (Knowledge Cards), Sources, Relationships mit URLs
   - Output: Obsidian Markdown im definierten Format
   - Anweisungen: Thematisch gruppieren, Fließtext, Callouts, korrekte Links
4. [ ] Frontmatter automatisch generieren (date, period, counts)
5. [ ] Podcast/Buch-Icons im Text korrekt setzen
6. [ ] Validierung: Alle Source-Links sind externe URLs (keine Wikilinks)
7. [x] ~~Fallback auf `gemini-2.5-flash` bei API-Fehler~~ — Removed: unlikely that 2.5 works when 3.1 doesn't

**Acceptance Criteria:**
- [ ] Thematische Gruppierung (nicht 1:1 pro Source)
- [ ] Deutsche Fließtexte mit redaktionellem Stil
- [ ] Callouts korrekt formatiert
- [ ] Alle Links sind externe URLs (readwise.io, share.snipd.com, oder original)
- [ ] Frontmatter-Statistiken stimmen mit Inhalt überein

---

### Story 9.3: Reader Delivery

**Beschreibung:** Summary als Artikel in Readwise Reader speichern.

**Tasks:**
1. [ ] Readwise Reader API: `POST /api/v3/save/` (bereits in `readwise_writer.py`)
2. [ ] Tag: `ai-weekly-summary`
3. [ ] Titel: `Knowledge Summary: [Datumsbereich]`
4. [ ] Duplikat-Check: Kein erneutes Speichern bei Re-Run
5. [ ] Cloud Scheduler: Wöchentlich (z.B. Sonntag 20:00 UTC)

**Acceptance Criteria:**
- [ ] Summary erscheint in Reader Inbox mit Tag
- [ ] Kein Duplikat bei wiederholter Ausführung
- [ ] Links im Reader klickbar

---

### Story 9.4: Obsidian Delivery (Headless Sync)

**Beschreibung:** Summary direkt in Obsidian Vault schreiben via Headless Sync.

**Abhängigkeit:** Obsidian Sync Abo, Headless Client Setup

**Tasks:**
1. [ ] GCS Bucket für Vault-Storage einrichten
2. [ ] Cloud Run Container mit Obsidian Headless Client + GCS FUSE
3. [ ] `OBSIDIAN_AUTH_TOKEN` in Secret Manager
4. [ ] Sync-Workflow: Pull → Write → Push
5. [ ] Dateiname: `Summaries/YYYY-MM-DD-knowledge-summary.md`
6. [ ] Concurrency=1 erzwingen
7. [ ] Terraform für Cloud Run + GCS Bucket

**Acceptance Criteria:**
- [ ] Summary erscheint in Obsidian Vault unter `Summaries/`
- [ ] Frontmatter korrekt (durchsuchbar via Obsidian Properties)
- [ ] Sync < 2 Min (Write + Push)
- [ ] Kein Datenverlust bei gleichzeitigem mobilem Editing

**Aufwand:** Deutlich höher als Reader-Delivery. Kann als Phase 2 nachgezogen werden.

---

### Story 9.5: get_recent mit Connections (Optional)

**Beschreibung:** `get_recent()` um `include_connections` Parameter erweitern, damit das MCP-Tool direkt Verbindungen mitliefert. Nützlich für On-Demand-Summaries via Claude Chat.

**Tasks:**
1. [ ] Parameter `include_connections: bool = False`
2. [ ] Source-IDs aus Chunks sammeln
3. [ ] Batch-Relationships-Query (IN-Query, max 30 pro Batch)
4. [ ] `connections_summary` in Response
5. [ ] MCP Tool-Schema aktualisieren
6. [ ] Tests

**Status:** Optional — die Summary-Pipeline nutzt Firestore direkt, dieses Feature ist ein Nice-to-Have für interaktive Nutzung.

---

### Story 9.6: Recurring Themes Analysis

**Beschreibung:** Die Summary um eine longitudinale Perspektive erweitern: Themen, die in ≥ 2 der letzten N Wochen auftauchen, werden als "Recurring Themes"-Abschnitt hervorgehoben. Gibt dem Leser Kontext: Was beschäftigt mich dauerhaft?

**Datenquelle:** Firestore `summaries` Collection (wird bereits von `main.py` via `_save_summary()` befüllt).

**Tasks:**
1. [ ] `fetch_previous_summaries(n_weeks: int = 4) -> List[Dict]` in `data_pipeline.py`
   - Query: `summaries` Collection, sortiert nach `created_at` DESC, limit n_weeks
   - Return: Liste von `{period, markdown, stats}` der letzten Wochen
2. [ ] `extract_themes(summaries: List[Dict]) -> List[str]` — Themen-Extraktion
   - Option A: H2-Überschriften aus dem Markdown der Vorwochen parsen (einfach, keine LLM-Kosten)
   - Option B: Gemini Flash extrahiert Themen aus den Summaries (genauer, ~$0.001)
   - Empfehlung: Option A als Start, Option B als Upgrade
3. [ ] Theme-Matching: Vergleiche aktuelle Wochen-Themen mit extrahierten Vorwochen-Themen
   - Einfaches String-Matching oder Embedding-Similarity (Embeddings sind bereits in der Pipeline)
4. [ ] `_build_prompt()` in `generator.py` erweitern:
   - Neuer Abschnitt `=== RECURRING THEMES ===` im Prompt
   - Format: `"Theme X appeared in weeks: W1, W2, W3"`
   - Instruktion an LLM: "If a theme recurs across multiple weeks, mention this continuity in the summary"
5. [ ] Tests: Mock `summaries` Collection, Theme-Extraktion, Prompt-Erweiterung

**Acceptance Criteria:**
- [ ] Themen die in ≥ 2 der letzten 4 Wochen auftauchen werden erkannt
- [ ] Summary enthält einen "Recurring Themes"-Hinweis wenn zutreffend
- [ ] Kein Fehler wenn `summaries` Collection leer ist (erste Woche)
- [ ] Performance: < 2s für Theme-Extraktion (4 Summaries)

**Kosten:** ~$0/Monat (Option A, Markdown-Parsing) oder ~$0.004/Monat (Option B, Gemini Flash)

**Status:** Planned

---

## Nicht-Ziele

- Keine Echtzeit-Notifications
- Keine interaktive Email (Epic 5 / Story 3.6 gestrichen zugunsten Obsidian/Reader)
- Kein eigener Email-Digest für diese private Summary — Obsidian + Reader sind der Kanal hier (externer Newsletter: → Epic 15)
- Keine Zusammenfassung jedes einzelnen Highlights — thematische Synthese

---

## Kosten

| Komponente | Monatlich |
|------------|-----------|
| Gemini 3.1 Pro (4x/Monat) | ~$0.25 |
| Cloud Function | ~$0 (Free Tier) |
| Cloud Run (Obsidian Sync, 4x/Monat) | ~$0 (Free Tier) |
| GCS Bucket (Vault) | ~$0 (Free Tier, < 5 GB) |
| **Gesamt** | **~$0.25/Monat** |

---

## Reihenfolge

1. **Phase 1:** Story 9.1 + 9.2 + 9.3 (Reader Delivery) — funktionierender MVP
2. **Phase 2:** Story 9.4 (Obsidian Headless Sync) — reicheres Format
3. **Optional:** Story 9.5 (get_recent mit Connections)
