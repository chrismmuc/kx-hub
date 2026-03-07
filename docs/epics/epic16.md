# Epic 16: Agent-Driven Reading Suggestions im Newsletter

**Goal:** Der Newsletter-Curation-Agent analysiert die persönliche Wissensbasis (KB, letzte 30 Tage) und aktive Probleme, führt gezielte Google-Suchen durch, und liefert ~10 kuratierte Lesevorschläge für die kommende Woche — gefiltert und gerankt mit der bewährten Scoring-Pipeline aus dem Recommendations Flow.

**Business Value:**
- Leser bekommen proaktive, personalisierte Leseempfehlungen basierend auf echtem KB-Kontext
- Agent-getriebene Queries sind kontextbewusster als die statischen Tavily-Templates
- Bestehende Filter-Logik (Scoring, Sampling, Slots) wird wiederverwendet — kein zweites Scoring-System
- Langfristig kann der Agent Tavily im Recommendations Flow komplett ablösen

**Status:** Planned

**Abhängigkeiten:** Epic 15 (Newsletter Pipeline), Epic 11 (Problem-Based Recommendations)

---

## Design-Entscheidungen

### 1. Agent vs. separate Pipeline

Der bestehende Recommendations Flow nutzt:
- `recommendation_problems.py` → Query-Generierung aus aktiven Problemen
- Tavily → Web-Suche (4 parallele Queries, max 5 Results/Query)
- `recommendation_filter.py` → Multi-Factor Scoring + Stochastic Sampling + Slot Assignment

**Entscheidung:** Der Newsletter-Agent übernimmt Query-Generierung UND Web-Suche (Steps 1+2), die bestehende Filter-Pipeline übernimmt Scoring/Ranking (Step 3). Gleiche Architektur, aber Agent statt Tavily.

**Vorteile des Agent-Ansatzes:**
- Agent kann iterativ suchen und Ergebnisse bewerten (statt One-Shot-Queries)
- Agent versteht KB-Kontext semantisch (nicht nur Keywords)
- Agent bewertet depth/authority direkt beim Durchsehen der Ergebnisse (spart separate Gemini-Calls)
- Agent kann Reasoning über Wissenslücken (Problems) und Themenkontinuität

### 2. Scoring: Agent vs. separate Bewertung

**Entscheidung:** Agent liefert `depth_score` (1-5) und `authority_score` (1-5) direkt mit. Spart die separaten Gemini-Calls die der bestehende Flow macht. Die mechanischen Scores (recency, domain diversity, combined) werden weiterhin von der Filter-Pipeline berechnet.

### 3. Filter-Code: Shared vs. eigenes Modul

**Entscheidung:** Eigenes `src/newsletter/newsletter_filter.py` mit den 5 benötigten Scoring-Funktionen (kopiert aus `recommendation_filter.py`, ohne externe Dependencies wie `embeddings`/`firestore_client`). Kein Import aus `src/mcp_server/` — Cloud Function flat-build inkompatibel.

### 4. Datenquellen

**Entscheidung:** Rein Agent-getrieben. Kein Fallback auf den bestehenden Recommendations Flow. Agent bekommt KB-Themes + aktive Problems als Kontext und sucht eigenständig.

### 5. Source-Curation

Die bestehende Newsletter-Curation (Step 1+2 im Agent) bleibt unverändert. Die 5-7 Guidance ist keine harte Restriktion — die Timeline (7 Tage) ist der eigentliche Filter. Reading Suggestions sind ein neuer Step 3.

---

## Technische Architektur

```
Cloud Function: generate_newsletter_cf
  │
  ├── 1. _fetch_recent_sources(days=7)          → sources (bestehend)
  ├── 1b. _fetch_kb_themes(days=30)             → {topics, active_problems}  ← NEU
  ├── 1c. _fetch_reader_inbox()                 → inbox_items (Reader API)   ← NEU
  ├── 1d. _fetch_previous_inbox_urls()          → set of URLs from last week ← NEU
  │
  ├── 2. run_curation(sources, kb_themes, inbox_items)
  │       └── ADK Agent (Vertex AI Agent Engine)
  │             ├── Step 1: Curate sources (bestehend)
  │             ├── Step 2: Hot news search (bestehend)
  │             ├── Step 3: Reading suggestions search  ← NEU
  │             │     Agent liefert ~15-20 rohe Ergebnisse mit:
  │             │     {title, url, snippet, depth_score, authority_score,
  │             │      relevance_rationale, published_date, topic}
  │             └── Step 4: Inbox curation  ← NEU
  │                   Agent filtert Inbox auf tech-relevante Items (~5-7)
  │
  ├── 3. _filter_reading_suggestions(raw)       ← NEU
  │       newsletter_filter.py:
  │       ├── parse_published_date()
  │       ├── calculate_recency_score()          (exponential decay, half-life 90d)
  │       ├── Domain-Cap (max 2/domain)
  │       ├── calculate_combined_score()         (relevance 0.45, authority 0.25, ...)
  │       ├── diversified_sample(temp=0.3)       (stochastic selection)
  │       └── assign_slots()                     (RELEVANCE, SERENDIPITY, TRENDING, ...)
  │       → ~10 gefilterte + gerankte Suggestions
  │
  ├── 4. generate_newsletter(curation, suggestions, inbox_picks, ...)
  │       ├── "## What's in my Inbox"            ← NEU
  │       └── "## What AI Suggests to Read"      ← NEU (ex "Next Week's Reading List")
  │
  └── 5. Upload + Delivery (bestehend)
```

---

## Stories

### Story 16.1: KB-Theme-Extraktion für Agent-Kontext

**Ziel:** KB-Kontext (letzte 30 Tage) aufbereiten, damit der Agent gezielt suchen kann.

**Tasks:**
1. `_fetch_kb_themes(days=30)` in `src/newsletter/main.py`:
   - Query `kb_items` mit `last_highlighted_at >= now - 30 days`
   - Extrahiere Top-Themen aus Knowledge Card Summaries/Takeaways
   - Lade aktive Probleme aus Firestore `problems` Collection (status == "active")
   - Return: `{"topics": ["LLM Fine-tuning", "Team Topologies", ...], "active_problems": [{"problem": "...", "description": "...", "evidence_count": N}, ...]}`
2. Non-fatal: Bei Fehler leeres Dict zurückgeben, Agent sucht ohne KB-Kontext

**Acceptance Criteria:**
- Topics werden aus Knowledge Cards extrahiert (nicht raw Highlights)
- Aktive Probleme werden mit evidence_count geladen
- Fehler in Theme-Extraktion stoppt Newsletter nicht

---

### Story 16.2: Agent-Instruction erweitern (Step 3)

**Ziel:** Der ADK Agent bekommt einen dritten Auftrag — Reading Suggestions basierend auf KB-Kontext.

**Tasks:**
1. `AGENT_INSTRUCTION` in `src/newsletter/curation_agent.py` erweitern um Step 3:
   ```
   3. SUGGEST NEXT WEEK'S READING (target: 15-20 raw items)
      You are given KB_THEMES and ACTIVE_PROBLEMS as additional context.

      Issue 4-6 google_search queries covering:
      a) Deeper dives into KB_THEMES topics not yet well covered
      b) Practical solutions/perspectives on ACTIVE_PROBLEMS
      c) Follow-ups on HOT_NEWS threads from step 2

      For each result, evaluate:
      - depth_score (1-5): How substantive is this content?
      - authority_score (1-5): How credible is the author/source?

      Return "reading_suggestions": list of 15-20 items:
      {title, url, snippet, topic, relevance_rationale,
       depth_score, authority_score, published_date, source_type}

      Rules:
      - Only include items with real, accessible URLs
      - Prefer: tutorials, long-form articles, papers, conference talks
      - Vary topics — don't cluster on one theme
      - Include published_date if visible (ISO format)
   ```
2. Prompt erweitern um KB-Context:
   ```python
   prompt = f"""
   === KB_THEMES (last 30 days) ===
   {json.dumps(kb_themes.get("topics", []))}

   === ACTIVE_PROBLEMS ===
   {json.dumps(kb_themes.get("active_problems", []))}

   === SOURCES TO CURATE ===
   {json.dumps(formatted_sources)}
   """
   ```
3. JSON-Parsing erweitern: `reading_suggestions` Feld aus Agent-Response extrahieren
4. Fallback: Leere Liste bei fehlendem Feld oder Parse-Fehler (non-fatal)
5. Agent re-deploy: `python src/newsletter/deploy_agent.py`

**Acceptance Criteria:**
- Agent generiert 15-20 rohe Suggestions mit Scores
- KB-Themes und Problems werden als Kontext übergeben
- Parsing tolerant gegenüber fehlenden/unvollständigen Feldern
- Fallback: Newsletter erscheint auch ohne Suggestions

---

### Story 16.3: Newsletter Filter-Pipeline

**Ziel:** Rohe Agent-Ergebnisse durch bewährte Scoring-Pipeline filtern.

**Tasks:**
1. Neues `src/newsletter/newsletter_filter.py` mit 5 Funktionen (kopiert aus `recommendation_filter.py`, ohne `embeddings`/`firestore_client` Dependencies):
   - `parse_published_date(date_str)` → datetime
   - `calculate_recency_score(published_date, half_life_days=90)` → 0.0-1.0
   - `calculate_combined_score(result, weights, novelty_bonus, domain_penalty)` → scored dict
   - `diversified_sample(results, n, temperature=0.3)` → stochastic selection
   - `assign_slots(recommendations, slot_config)` → RELEVANCE/SERENDIPITY/STALE_REFRESH/TRENDING
   - Nur stdlib: `math`, `logging`, `collections`, `datetime`. Optional `numpy` für Sampling.

2. `_filter_reading_suggestions(raw_suggestions)` in `src/newsletter/main.py`:
   ```python
   def _filter_reading_suggestions(raw: list[dict], limit: int = 10) -> list[dict]:
       # 1. Parse dates + calculate recency scores
       # 2. Filter: recency_score > 0 (not too old)
       # 3. Domain cap: max 2 per domain
       # 4. Map agent scores to filter format:
       #    - relevance_score: 0.8 default (agent pre-selected for relevance)
       #    - depth_score: from agent (1-5)
       #    - credibility_score: authority_score / 5.0 (normalize to 0-1)
       #    - recency_score: from calculate_recency_score()
       # 5. calculate_combined_score() per item
       # 6. diversified_sample(n=limit*2, temperature=0.3)
       # 7. assign_slots(slot_config for ~10 items)
       return filtered
   ```

3. `build.sh` erweitern: `cp newsletter_filter.py build/`

**Acceptance Criteria:**
- Scoring-Ergebnisse konsistent mit bestehender Recommendations-Pipeline
- Domain-Diversität gewährleistet (max 2/domain)
- Stochastic Sampling verhindert deterministische Ergebnisse
- Slot Assignment sorgt für thematische Vielfalt

---

### Story 16.4: Newsletter-Sektion + Datenmodell

**Ziel:** Reading Suggestions als neue Sektion im Newsletter darstellen.

**Tasks:**
1. Models erweitern in `src/newsletter/models.py`:
   ```python
   class ReadingSuggestionRaw(BaseModel):
       title: str
       url: str
       snippet: str
       topic: str
       relevance_rationale: str
       depth_score: float = 3.0
       authority_score: float = 3.0
       published_date: str = ""
       source_type: str = "article"

   class ReadingSuggestion(BaseModel):
       title: str
       url: str
       topic: str
       rationale: str
       source_type: str = "article"
       slot: str = ""
       slot_reason: str = ""
       final_score: float = 0.0
   ```
   - `CurationResult` erweitern: `reading_suggestions_raw: list[ReadingSuggestionRaw] = []`
   - `NewsletterDraft` erweitern: `reading_suggestions: list[ReadingSuggestion] = []`

2. Generator-Prompt in `src/newsletter/generator.py` erweitern:
   ```
   ## Next Week's Reading List

   Brief intro (1-2 sentences connecting to this week's themes).

   For each suggestion:
   - [Title](url) · {topic} — {rationale}
   ```
   - `reading_suggestions` als Parameter zu `generate_newsletter()` hinzufügen
   - HTML-Template erweitern

3. `main.py` Orchestrierung: Nach Curation → Filter → Generator

**Acceptance Criteria:**
- Neue Sektion erscheint im Newsletter nach "What I've Been Reading"
- Suggestions enthalten echte URLs und nachvollziehbare Rationales
- Leere Suggestions-Liste → Sektion wird weggelassen (graceful)
- Firestore Draft enthält `reading_suggestions` Feld

---

### Story 16.5: "What's in my Inbox" — Reader Inbox Highlights

**Ziel:** Neben den Agent-getriebenen Suggestions ("What AI Suggests to Read") eine zweite Sektion: kuratierte Highlights aus der persönlichen Readwise Reader Inbox. Tech-relevant gefiltert, mit Dedup gegen Vorwoche.

**Kontext:** Die Reader Inbox enthält gespeicherte Artikel die noch nicht gelesen wurden. Daraus eine wöchentliche Auswahl zu zeigen hat zwei Vorteile:
1. Leser sehen was der Autor selbst auf der Leseliste hat (persönlicher als AI-Vorschläge)
2. Motivation für den Autor selbst, die Inbox abzuarbeiten

**Zwei Newsletter-Sektionen (final):**
- **"What's in my Inbox"** — Persönliche Reader-Inbox, tech-gefiltert (~5 Items)
- **"What AI Suggests to Read"** — Agent-getriebene Vorschläge basierend auf KB (~10 Items)

**Tasks:**
1. `_fetch_reader_inbox()` in `src/newsletter/main.py`:
   - Reader API `GET /list/` mit `location=new` (Inbox-Filter)
   - Kein HTML-Content nötig — nur Metadaten (title, url, author, category, created_at, tags)
   - Sortiert nach `created_at` DESC (neueste zuerst)
   - Limit: ~50 Items als Rohpool

2. Tech-Relevanz-Filter:
   - Der Curation Agent kann diese Aufgabe übernehmen (neuer Step oder erweiterter Step 1)
   - Agent bekommt Inbox-Items als separaten Block im Prompt
   - Instruction: "Select 5-7 items from INBOX that are relevant for a tech audience"
   - Agent nutzt gleiche Urteilslogik wie für Source-Curation (keine Allowlist)

3. Dedup gegen Vorwoche:
   - Lade letzten `newsletter_drafts` Eintrag aus Firestore
   - Extrahiere `inbox_items[].url` aus der Vorwoche
   - Filtere: Items die letzte Woche schon im Newsletter waren, werden übersprungen
   - Verhindert, dass ein Artikel 4 Wochen lang im Newsletter erscheint
   - Alternativ: Tag-basiert — Agent setzt `kx-newsletter-shown` Tag auf gezeigte Items via Reader API

4. Models in `src/newsletter/models.py`:
   ```python
   class InboxItem(BaseModel):
       title: str
       url: str
       author: str = ""
       category: str = "article"
       reason: str = ""  # Why selected by agent
       added_at: str = ""  # When saved to inbox

   # CurationResult erweitern:
   class CurationResult(BaseModel):
       filtered_sources: list[CuratedSource]
       hot_news: list[HotNewsItem]
       reading_suggestions_raw: list[ReadingSuggestionRaw] = []
       inbox_picks: list[InboxItem] = []  # NEU
       curator_notes: str = ""

   # NewsletterDraft erweitern:
   class NewsletterDraft(BaseModel):
       ...
       inbox_items: list[InboxItem] = []  # NEU
   ```

5. Generator-Sektion in `src/newsletter/generator.py`:
   ```
   ## What's in my Inbox

   Brief intro (1 sentence, e.g. "Here's what caught my eye this week but I haven't read yet").

   For each item:
   - [Title](url) · Author — {reason}
   ```

6. `build.sh`: `reader_client.py` in build/ kopieren (batch_recommendations Version, leichtgewichtig)

**Dedup-Strategie (Detail):**
```python
def _fetch_reader_inbox(previous_urls: set[str]) -> list[dict]:
    """Fetch inbox items, excluding those shown in previous newsletter."""
    client = ReadwiseReaderClient(api_key=_get_secret("readwise-api-key"))
    # location=new filters to inbox (not archive/feed)
    docs = client.list_documents_filtered(location="new", limit=50)

    # Remove items already shown last week
    fresh = [d for d in docs if d.get("source_url", d.get("url")) not in previous_urls]
    return fresh
```

**Acceptance Criteria:**
- Inbox-Items werden aus Reader API geholt (location=new)
- Tech-Relevanz-Filter über Agent (gleiche Logik wie Source-Curation)
- Items die letzte Woche gezeigt wurden, erscheinen nicht erneut
- Leere Inbox → Sektion wird weggelassen
- 5-7 Items pro Ausgabe

---

## Dateien & Änderungen (Zusammenfassung)

| Datei | Änderung |
|-------|----------|
| `src/newsletter/models.py` | `ReadingSuggestionRaw`, `ReadingSuggestion`, `InboxItem`, `CurationResult` + `NewsletterDraft` erweitern |
| `src/newsletter/main.py` | `_fetch_kb_themes()`, `_fetch_reader_inbox()`, `_filter_reading_suggestions()`, Orchestrierung |
| `src/newsletter/curation_agent.py` | Steps 3+4 in `AGENT_INSTRUCTION`, KB-Themes + Inbox im Prompt, Parsing erweitern |
| `src/newsletter/generator.py` | `reading_suggestions` + `inbox_items` Parameter, zwei neue Sektionen in Prompt + HTML |
| `src/newsletter/newsletter_filter.py` | **NEU** — 5 Scoring-Funktionen (eigenständig, keine mcp_server Deps) |
| `src/newsletter/build.sh` | `newsletter_filter.py` + `reader_client.py` in build/ kopieren |
| `tests/` | Tests für Theme-Extraktion, Inbox-Fetch, Agent-Parsing, Filter-Pipeline, Dedup, Generator-Sektionen |

---

## Verifizierung

1. **Unit Tests**: Mock Agent-Response mit `reading_suggestions` + `inbox_picks` → Filter-Pipeline → assert ~10 Suggestions mit Slots + ~5 Inbox Items
2. **Filter-Tests**: Recency, Combined Scoring, Sampling, Slots — analog zu bestehenden `recommendation_filter` Tests
3. **Inbox-Dedup-Tests**: Mock previous draft mit URLs → assert diese nicht in neuer Inbox-Auswahl erscheinen
4. **Dry-Run**: `curl -X POST <cf-url> -d '{"dry_run": true}'` → JSON enthält `reading_suggestions_count` + `inbox_items_count`
5. **HTML Check**: GCS Newsletter-HTML enthält "What's in my Inbox" + "What AI Suggests to Read" Sektionen
6. **Agent Deploy**: `deploy_agent.py` → Secret Manager Update → CF nutzt neuen Agent

---

## Kosten

| Komponente | Zusätzlich/Woche |
|------------|-----------------|
| Agent Steps 3+4 (google_search + inbox curation) | ~$0.03-0.05 |
| KB-Theme Query (Firestore reads) | ~$0 |
| Reader Inbox API Call (1 req/Woche) | $0 |
| Filter-Pipeline (lokal, kein LLM) | $0 |
| **Gesamt** | **~$0.12-0.20/Monat** |

Kein zusätzlicher Gemini-Call für Scoring (Agent liefert Scores direkt).

---

## Langfrist-Perspektive

Wenn die Agent-getriebenen Suggestions gut funktionieren:
1. Der bestehende Recommendations Flow (`recommendation_problems.py` + Tavily) kann durch den Agent ersetzt werden
2. Tavily-Kosten ($5/Monat API) entfallen
3. Agent hat Zugriff auf `google_search` (kostenlos via ADK) statt Tavily ($)
4. Scoring-Pipeline bleibt identisch — nur die Query+Search-Quelle ändert sich
