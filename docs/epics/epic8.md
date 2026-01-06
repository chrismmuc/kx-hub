# Epic 8: Smarter Recommendation Queries

**Goal:** Ersetze generische Template-Queries durch LLM-generierte, kontextbezogene Suchanfragen basierend auf den besten Knowledge Card Insights.

**Business Value:** 
- Höhere Relevanz der Empfehlungen (~40% → ~70-80% brauchbar)
- Entdeckung von "adjacent topics" die Template-Queries nicht finden
- Personalisierte Queries basierend auf tatsächlichem Leseverhalten

**Dependencies:** Epic 3 (Recommendations), Epic 7 (Async)

**Status:** Planned

---

## Problem Statement

Aktuelle Query-Generierung ist zu generisch:

```python
# Jetzt (Template-basiert):
"{topic} best practices insights"
"advanced {topic} techniques"

# Ergebnis:
"ai best practices insights"  → generische, beliebige Treffer
```

Die Templates nutzen nur Titel/Tags, nicht den semantischen Inhalt der Highlights. Ein Buch mit 50 Highlights zählt gleich wie eines mit 2.

---

## Solution: LLM-Generated Queries

### Architektur

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. get_top_takeaways(n=10)                                      │
│    - Hole Knowledge Cards mit besten Takeaways                  │
│    - Gewichte nach: Highlight-Anzahl, Recency, Card-Qualität    │
│                         ↓                                       │
│ 2. generate_queries_with_llm(takeaways)                         │
│    - Prompt: "Basierend auf diesen Erkenntnissen..."            │
│    - Gemini Flash generiert 6-8 präzise Queries                 │
│                         ↓                                       │
│ 3. Tavily Search (optimiert)                                    │
│    - auto_parameters=true für intelligente Konfiguration        │
│    - Queries max 400 Zeichen                                    │
│    - search_depth="advanced" für beste Relevanz                 │
└─────────────────────────────────────────────────────────────────┘
```

### Beispiel

**Input (Top Takeaways aus KB):**
```
1. "90min Deep Work blocks outperform fragmented coding sessions"
2. "Platform teams should measure developer cognitive load, not just DORA"
3. "Agentic AI requires explicit planning phases and tool orchestration"
4. "Knowledge Cards compress information 5x while preserving key insights"
```

**LLM Prompt:**
```
Du bist ein Research-Assistent. Basierend auf diesen Erkenntnissen 
aus meiner Wissensdatenbank, generiere 6 Suchanfragen für Tavily.

Erkenntnisse:
{takeaways}

Anforderungen an die Queries:
- Baue auf den Erkenntnissen auf ("was kommt als nächstes?")
- Finde neue Perspektiven oder Gegenargumente
- Suche aktuelle Entwicklungen (2025)
- Max 50 Zeichen pro Query, keine Füllwörter
- Englisch

Format: Eine Query pro Zeile, ohne Nummerierung.
```

**Output (LLM-generierte Queries):**
```
deep work interruption recovery time research 2025
developer cognitive load measurement tools
agentic AI planning patterns production systems
platform engineering team topologies
knowledge compression techniques RAG systems
DORA metrics limitations developer experience
```

---

## Story 8.1: LLM Query Generation

### Tasks

1. [ ] `get_top_takeaways(n=10)` implementieren
   - Query Knowledge Cards mit höchster Qualität
   - Gewichtung: source_highlight_count * recency * card_quality_score
   - Rückgabe: Liste von Takeaway-Strings

2. [ ] `generate_queries_with_llm(takeaways)` implementieren
   - Nutze Gemini Flash (günstig, schnell)
   - Prompt für 6-8 präzise Queries
   - Parse Response, validiere Query-Länge

3. [ ] Integration in `generate_search_queries()`
   - Ersetze Template-Logik komplett
   - Kein Fallback (Fehler = Fix)

4. [ ] Tests
   - Mock LLM Response
   - Validiere Query-Format

### Acceptance Criteria

- [ ] Queries basieren auf echten KB-Inhalten, nicht Templates
- [ ] Queries sind max 50 Zeichen, ohne Füllwörter
- [ ] Gemini Flash Call < 3s
- [ ] Kosten < 0.02€ pro Recommendation-Run

---

## Story 8.2: Tavily Optimization

### Aktuelle Nutzung vs. Best Practices

| Parameter | Aktuell | Optimiert |
|-----------|---------|-----------|
| `search_depth` | `"advanced"` | `"advanced"` (bereits optimal) |
| `auto_parameters` | nicht gesetzt | `true` - intelligente Konfiguration |
| `max_results` | 5 | 5-7 (mehr Kandidaten für Filtering) |
| Query-Länge | variabel | max 400 Zeichen |
| `topic` | nicht gesetzt | `"news"` für Aktualität wenn relevant |

### Tasks

1. [ ] `auto_parameters=true` aktivieren
   - Tavily optimiert automatisch basierend auf Query-Intent
   - Überschreibt nicht explizit gesetzte Parameter

2. [ ] Query-Länge validieren/kürzen
   - Max 400 Zeichen (Tavily Empfehlung)
   - LLM soll kurze Queries generieren

3. [ ] Optional: `topic="news"` für Mode "fresh"
   - Liefert `published_date` für bessere Recency-Scores

4. [ ] Async Batch-Requests
   - Nutze `AsyncTavilyClient` mit `asyncio.gather()`
   - Parallele Ausführung aller Queries

### Acceptance Criteria

- [ ] `auto_parameters=true` in allen Tavily-Calls
- [ ] Queries unter 400 Zeichen
- [ ] Keine Änderung an Kosten (auto_parameters ist kostenlos)

---

## Story 8.3: Engagement-Gewichtung (Optional)

### Konzept

Quellen mit mehr Highlights = höhere Relevanz für Query-Generierung.

```python
# Gewichtungsformel für Takeaway-Auswahl:
score = (
    highlight_count * 0.4 +      # Engagement
    recency_score * 0.3 +        # Aktualität
    card_quality_score * 0.3     # Knowledge Card Qualität
)
```

### Tasks

1. [ ] `highlight_count` aus Source-Metadata nutzen
2. [ ] Gewichtungslogik in `get_top_takeaways()` einbauen
3. [ ] Testen mit echten KB-Daten

---

## Erwartete Ergebnisse

| Metrik | Vorher | Nachher |
|--------|--------|---------|
| Query-Beispiel | `"ai best practices"` | `"agentic AI tool orchestration production 2025"` |
| Relevanz (geschätzt) | ~40% brauchbar | ~70-80% brauchbar |
| Überraschungsfaktor | Niedrig | Höher (adjacent topics) |
| Kosten pro Run | ~0.05€ (Tavily) | ~0.06€ (+0.01€ Gemini Flash) |
| Latenz | ~60-90s | ~65-95s (+2-3s LLM) |

---

## Nicht-Ziele

- Kein Fallback auf Templates (Fehler müssen gefixt werden)
- Keine User-Feedback-Loop (spätere Epic)
- Keine expliziten Interessen-Profile (spätere Epic)

---

## Referenzen

- [Tavily Best Practices](https://docs.tavily.com/documentation/best-practices/best-practices-search)
- [Tavily Auto-Parameters](https://blog.tavily.com/rethinking-tool-calling-introducing-tavily-auto-parameters/)
- Bestehendes: `src/mcp_server/recommendation_queries.py`
