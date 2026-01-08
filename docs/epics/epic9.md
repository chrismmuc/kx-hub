# Epic 9: Recent Knowledge Connections & Daily Digest

**Goal:** Zeige bei neuen Chunks automatisch die Verbindungen zu existierenden Sources an. Ermögliche einen täglichen Email-Digest der neuen Learnings mit ihren Cross-Source-Relationships.

**Business Value:**
- Sofortiger Kontext: "Was ich heute gelernt habe, verbindet sich mit..."
- Wissensvernetzung sichtbar machen ohne manuelles Nachfragen
- Tägliche passive Wissenszusammenfassung per Email

**Dependencies:** Epic 4 (Source-Based Knowledge Graph)

**Status:** Planned

---

## Problem Statement

`get_recent` zeigt neue Chunks, aber **nicht** wie sie sich mit existierendem Wissen verbinden:

```python
# Aktuell:
get_recent(period="last_7_days", limit=10)
# → Liste von Chunks mit Knowledge Cards

# Gewünscht:
get_recent(period="last_7_days", limit=10, include_connections=True)
# → Chunks + Cross-Source Relationships, gruppiert nach Typ
```

Der User muss aktuell für jeden Chunk einzeln `get_chunk()` oder `get_source()` aufrufen um Relationships zu sehen.

---

## Solution: Enhanced get_recent with Connections

### Response-Struktur (erweitert)

```json
{
  "period": "last_7_days",
  "chunk_count": 5,
  "recent_chunks": [...],
  "activity_summary": {...},

  "connections_summary": {
    "total_connections": 12,
    "new_sources": ["Deep Work", "Atomic Habits"],
    "connected_sources": ["Flow", "Peak Performance", "Digital Minimalism"],

    "by_relationship_type": {
      "extends": {
        "count": 5,
        "examples": [
          {
            "new_source": "Deep Work",
            "connected_source": "Flow",
            "explanation": "Deep Work extends Flow's concept of..."
          }
        ]
      },
      "supports": {
        "count": 4,
        "examples": [...]
      },
      "contradicts": {
        "count": 2,
        "examples": [...]
      },
      "applies": {
        "count": 1,
        "examples": [...]
      }
    }
  }
}
```

---

## Story 9.1: Extend get_recent with Cross-Source Connections

### Beschreibung

Erweitere `get_recent()` um einen optionalen Parameter `include_connections` der die Cross-Source Relationships für alle neuen Chunks sammelt und gruppiert zurückgibt.

### Tasks

1. [ ] Neuen Parameter `include_connections: bool = False` hinzufügen
2. [ ] Für jeden neuen Chunk die `source_id` sammeln (unique)
3. [ ] Für jede neue Source `get_source_relationships()` aufrufen
4. [ ] Relationships nach Typ gruppieren (extends, supports, contradicts, applies)
5. [ ] `connections_summary` Struktur aufbauen mit:
   - `total_connections`: Gesamtzahl
   - `new_sources`: Liste der neuen Source-Titel
   - `connected_sources`: Liste der verbundenen Source-Titel
   - `by_relationship_type`: Gruppierung mit Count + Beispielen
6. [ ] Performance: Batch-Queries wo möglich (Source-Lookups)
7. [ ] Tests schreiben

### Technische Details

```python
def get_recent(
    period: str = "last_7_days",
    limit: int = 10,
    include_connections: bool = False  # NEU
) -> Dict[str, Any]:
    # ... bestehende Logik ...

    if include_connections:
        connections = _get_connections_for_chunks(recent_chunks)
        result["connections_summary"] = connections

    return result
```

### Acceptance Criteria

- [ ] `include_connections=True` liefert gruppierte Relationships
- [ ] Relationships nach Typ sortiert (extends, supports, contradicts, applies)
- [ ] Jeder Typ hat Count + max 3 Beispiele mit Explanation
- [ ] Performance: < 5s für typische Abfrage (10 Chunks)
- [ ] Keine Änderung am bestehenden Response wenn `include_connections=False`

---

## Story 9.2: MCP Server Integration

### Beschreibung

MCP Tool Definition erweitern um den neuen Parameter.

### Tasks

1. [ ] Tool-Schema in `server.py` erweitern
2. [ ] Parameter-Handling in Tool-Handler
3. [ ] Tool-Beschreibung aktualisieren

### Tool-Schema Update

```python
"get_recent": {
    "description": "Get recent reading activity and chunks. "
                   "Optionally include cross-source relationship connections.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "period": {...},
            "limit": {...},
            "include_connections": {
                "type": "boolean",
                "description": "Include cross-source relationships for new chunks, "
                              "grouped by type (extends, supports, contradicts)",
                "default": False
            }
        }
    }
}
```

---

## Story 9.3: Daily Email Digest

### Beschreibung

Täglicher Email-Digest der neuen Learnings mit ihren Verbindungen zu existierendem Wissen.

### Abhängigkeiten

- Story 9.1 (get_recent mit Connections)
- Story 3.6 aus Backlog (Email Digest Infrastruktur)

### Tasks

1. [ ] Cloud Scheduler Job für täglichen Trigger (z.B. 8:00 Uhr)
2. [ ] Cloud Function die `get_recent(period="yesterday", include_connections=True)` aufruft
3. [ ] Email-Template (HTML) mit:
   - Anzahl neue Chunks
   - Liste der neuen Sources mit Snippet
   - **Connections-Sektion**: "Verbindungen zu deinem Wissen"
     - Gruppiert nach Relationship-Typ
     - Pro Typ: Source-Paar + kurze Explanation
4. [ ] SendGrid Integration (Story 3.6)
5. [ ] Firestore Config für Email-Adresse und Einstellungen
6. [ ] MCP Tool: `configure_daily_digest(enabled, email, time)`

### Email-Template Beispiel

```
📚 Dein Daily Knowledge Digest - 7. Januar 2026

═══════════════════════════════════════════════

🆕 NEUE HIGHLIGHTS (3)

• Deep Work - Cal Newport
  "90min focused blocks outperform fragmented sessions..."

• Atomic Habits - James Clear
  "1% daily improvement compounds to 37x yearly..."

═══════════════════════════════════════════════

🔗 VERBINDUNGEN ZU DEINEM WISSEN

EXTENDS (2)
• Deep Work → Flow (Mihaly Csikszentmihalyi)
  "Erweitert das Flow-Konzept um konkrete Zeitblöcke"

• Atomic Habits → The Power of Habit (Charles Duhigg)
  "Baut auf dem Habit Loop auf, fügt Identity-Based Habits hinzu"

SUPPORTS (1)
• Deep Work → Digital Minimalism
  "Bestätigt die Wichtigkeit von Tech-Free Fokuszeit"

CONTRADICTS (1)
• Atomic Habits → The 4-Hour Workweek
  "1% tägliche Verbesserung vs. 80/20 Pareto-Ansatz"

═══════════════════════════════════════════════

Generiert von kx-hub
```

### Acceptance Criteria

- [ ] Tägliche Email um konfigurierte Uhrzeit
- [ ] Email nur wenn neue Chunks vorhanden
- [ ] Connections-Sektion gruppiert nach Typ
- [ ] Unsubscribe-Link funktioniert
- [ ] Kosten < $0.05/Monat (SendGrid Free Tier)

---

## Story 9.4: Natural Language Summary (Optional)

### Beschreibung

Statt nur strukturierter Daten: LLM-generierte Zusammenfassung im Fließtext.

### Beispiel

```
Heute hast du 3 neue Highlights aus "Deep Work" und "Atomic Habits"
hinzugefügt. Diese erweitern dein bestehendes Wissen über Flow-Zustände
und Gewohnheitsbildung. Interessant: Die Atomic Habits-Idee der 1%
täglichen Verbesserung widerspricht leicht dem 80/20-Ansatz aus
"The 4-Hour Workweek" - ein guter Punkt zum Nachdenken.
```

### Tasks

1. [ ] Prompt für Gemini Flash mit Connections-Daten
2. [ ] Max 100 Wörter, conversational tone
3. [ ] Als optionalen Teil des Email-Digests

---

## Nicht-Ziele

- Keine Echtzeit-Notifications (nur Daily Digest)
- Keine interaktive Email (keine Buttons/Actions)
- Keine Zusammenfassung der Chunk-Inhalte (nur Connections)

---

## Metriken

| Metrik | Ziel |
|--------|------|
| `get_recent` mit Connections | < 5s Latenz |
| Email Delivery Rate | > 95% |
| Tägliche Kosten | < $0.01 |

---

## Referenzen

- `get_source_relationships()` in `firestore_client.py:1952`
- Story 3.6 (Email Digest) in `backlog.md`
- Epic 5 (Knowledge Digest) in `backlog.md`
