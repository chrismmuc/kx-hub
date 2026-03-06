# Epic 15: External Tech Newsletter

**Goal:** Automatischer wöchentlicher Newsletter für externe Leser — gefiltert auf Tech/AI/Management-Themen aus dem KX Hub, ergänzt durch KI-recherchierte Hot News der Woche. Delivery via verwalteter Mailing-Liste.

**Business Value:**
- Eigene externe Stimme aufbauen: Kuratierte Tech-Insights aus dem persönlichen Lesen
- Kein manueller Aufwand: vollständig automatisiert aus bestehender Pipeline
- Wachstumspfad: Basis-Infrastruktur für eine spätere echte Newsletter-Audience
- Klare Trennung: Private Summary (alles) vs. externer Newsletter (nur Tech/AI/Management)

**Status:** Planned

**Abhängigkeiten:** Epic 9 (Weekly Knowledge Summary, Firestore `summaries` Collection)

---

## Design-Entscheidungen

### 1. Filter-Ansatz: Source-Level vs. Post-Processing

**Option A: Source-Level-Klassifizierung** ← **Gewählt**
- Sources werden vor dem Generator gefiltert, nicht aus der privaten Summary destilliert
- Vorteil: kein Themen-Blending im Generator; sauberer Input
- Nachteil: ~2x Compute-Schritte

**Option B: Post-Processing der privaten Summary**
- Bestehende private Summary als Input, LLM soll "nur Tech-Teil" extrahieren
- Nachteil: LLM-Kontext wird durch persönliche Themen beeinflusst, Resultate unzuverlässig

**Entscheidung:** Option A.

### 2. Filter + Research: Explizite Logik vs. ADK Agent

**Option A: Explizite LLM-Calls** (ursprünglicher Entwurf)
- Gemini Flash: jede Source mit Allowlist/Denylist + Konfidenz-Schwellwert klassifizieren
- Festes Query-Template für News-Recherche
- Problem: du musst selbst Grenzfälle pflegen — "Ist Decision-Making-Psychologie Tech oder Personal?", "Ist dieser VC-Artikel Management oder Lifestyle?" — als Regeln hinschreiben

**Option B: Vertex AI ADK Agent** ← **Gewählt**
- Ein Agent erhält alle Sources + aktuelles Datum als Kontext
- Goal: *"Select which of these sources are relevant for an external tech audience, and research what was hot in AI/software this week"*
- Der Agent reasoning über Grenzfälle autonom — keine Allowlist, kein Schwellwert
- Tools: `google_search` (built-in ADK Tool) für Hot News
- Deployment: Vertex AI Agent Engine (managed, kein eigenes Infra)
- **Kern-Vorteil:** Die Bewertungslogik steckt im LLM-Reasoning, nicht in Code — wartungsärmer, robuster bei Grenzfällen

**Warum ADK besser passt als direktes Grounding:**
- Grounding = ein einzelner LLM-Call mit passiver Search-Nutzung
- ADK Agent = multi-step: plant Suchanfragen, evaluiert Ergebnisse, entscheidet selbstständig was "hot" ist
- Kein Hardcode von "3-5 Items", "sortiert nach Relevanz" — das entscheidet der Agent
- Kein Hardcode von Relevanz-Kriterien für den Filter — der Agent argumentiert kontextuell

**Kosten-Vergleich:**
| Ansatz | Kosten/Woche |
|--------|-------------|
| Gemini Flash (Classifier) + Gemini Pro (Grounding) | ~$0.03 |
| ADK Agent (Gemini Pro, multi-turn) | ~$0.06–0.10 |

Delta ~$0.03–0.07/Woche = ~$0.15–0.30/Monat. Akzeptabel für deutlich weniger Code-Komplexität.

**Deployment:** Vertex AI Agent Engine (managed). Kein Cloud Run Container nötig,
kein Session-Management — der Agent ist stateless (wöchentlicher Batch-Job).

### 3. Newsletter-Delivery: E-Mail-Dienst

**Anforderungen:** GCP-nah, kostenlos zu Beginn, erweiterbar, einfache API

| Service | Free Tier | API | GCP-Integration | Empfehlung |
|---------|-----------|-----|-----------------|------------|
| **Brevo** (ehem. Sendinblue) | 300 Emails/Tag | REST API | ✓ Webhook/CF | ✅ Gewählt |
| Mailgun | 100 Emails/Tag | REST API | ✓ | Backup |
| Amazon SES | Pay-per-use | REST API | AWS (Cross-Cloud) | Ausweichoption |
| Listmonk (self-hosted) | Free | REST API | Cloud Run möglich | Wenn volle Kontrolle wichtig |

**Entscheidung:** **Brevo** — 300/Tag Free Tier reicht für den Start (10-50 Subscriber), gute REST API,
List-Management inklusive, einfache Unsubscribe-Links. Bei Wachstum: Brevo Starter ab $9/Monat
für 5.000 Emails/Monat.

### 4. Subscriber-Management: Brevo nativ vs. Firestore

**Option A: Brevo-native List-Management** ← **Gewählt**
- Brevo verwaltet Subscriber-Liste, Double-Opt-In, Unsubscribe direkt
- Deutlich weniger eigener Code (kein Custom Subscribe-Endpoint nötig)
- Unsubscribe-Link wird von Brevo automatisch eingefügt
- Nachteil: Abhängigkeit von Brevo für Subscriber-Daten

**Option B: Eigene Firestore `newsletter_subscribers` Collection**
- Volle Datenkontrolle, einfacher zu migrieren
- Mehr Eigenentwicklung (Subscribe/Unsubscribe Endpoints, Double-Opt-In E-Mails)

**Entscheidung:** **Hybrid** — Subscriber-Liste primär in Brevo verwalten (spart Aufwand),
zusätzlich die Liste in Firestore spiegeln (einfache Migration, eigene Analytics).
Subscribe/Unsubscribe Endpoints in Cloud Functions (leichtgewichtig, beide Systeme synchron halten).

---

## Agent-Ziel (statt Allowlist/Denylist)

Statt expliziter Regellisten wird der Agent mit einem Ziel-Prompt instruiert:

```
You are a newsletter curator for a weekly tech newsletter called "Weekly Reading Notes".

Your audience: software engineers, engineering managers, and tech leaders.

Given the sources read this week, your tasks:
1. Select sources that would be interesting and relevant for this external tech audience.
   Use your judgment — focus on software, AI/ML, engineering, management, leadership,
   product, and related tech topics. Exclude personal topics like parenting, marriage,
   sports, self-help, etc. For borderline cases (e.g. psychology applied to engineering
   teams), include them if the professional angle is dominant.
2. Research the most important AI and software news from this week using the search tool.
   Find 3-5 genuinely significant developments, not just hype.

Return structured output: filtered_sources + hot_news_items.
```

**Bewusste Entscheidung:** Keine harte Allowlist/Denylist — der Agent argumentiert kontextuell.
Ein Artikel über "Stoizismus für Tech-Manager" wäre in einer Regel-basierten Welt "Philosophie → exclude",
mit Agent-Reasoning: "professional context, relevant for management audience → include".

---

## Technische Architektur

```
Cloud Scheduler (wöchentlich, Sa 08:00 UTC)
  │
  ▼
Cloud Function: newsletter_orchestrator
  │
  ├─ 1. Fetch recent sources (last 7 days) ← reuse Epic 9 data_pipeline
  │
  ├─ 2. ADK Curation & Research Agent (Stories 15.1 + 15.2)
  │      └─ Vertex AI Agent Engine (managed, stateless)
  │      └─ Model: Gemini Pro
  │      └─ Tool: google_search (built-in ADK)                ← MVP
  │      └─ Tool: kx_search → MCP Cloud Run (HTTP)            ← nach Dry-Run ergänzen
  │      └─ Input: sources as context + week date [+ recurring themes]
  │      └─ Output: {filtered_sources: [...], hot_news: [...]}
  │      (Agent decides autonomously: what's relevant? what's hot?)
  │
  ├─ 3. Newsletter Generator (Story 15.3)
  │      └─ Gemini Pro: compose external newsletter
  │      └─ Input: filtered_sources + hot_news
  │      └─ Output: HTML + plain text
  │
  └─ 4. Delivery (Story 15.4)
         └─ Brevo API: send to subscriber list
         └─ Firestore: log newsletter + delivery metadata
```

---

## Agent: Technische Spezifikation

### A) Input-Format: Wie Sources in den Agent injiziert werden

ADK Agents empfangen einen Text-String als User-Message. Bei 10–20 Sources mit Knowledge Cards
können das 5.000–10.000 Tokens Input sein.

**Gewählter Ansatz: Strukturierte User-Message (JSON serialisiert als Text)**

```python
import json

def build_agent_input(sources: list[dict], week: str) -> str:
    return f"""Week: {week}

Sources read this week:
{json.dumps(sources, ensure_ascii=False, indent=2)}

Task: Curate the above sources for an external tech audience, then research hot AI/software news.
Return JSON: {{"filtered_sources": [...], "hot_news": [...]}}"""
```

- Einfachste Lösung, kein Custom Tool nötig
- Bei sehr vielen Sources (>25): Sources auf Title + 2-Satz-Summary kürzen vor Injektion
- **Alternative (aufwendiger):** Custom Tool `get_sources()` — Agent ruft Firestore selbst ab. Erst relevant wenn Sources zu groß für Context werden.

### B) Output-Parsing: Wie strukturiertes JSON erzwungen wird

ADK Agents geben standardmäßig Freitext zurück.

**Gewählter Ansatz: Pydantic-Schema im Prompt + nachgelagertes Parsing mit Fallback**

```python
from pydantic import BaseModel

class HotNewsItem(BaseModel):
    title: str
    url: str
    summary: str

class CurationResult(BaseModel):
    filtered_sources: list[dict]  # subset der Input-Sources
    hot_news: list[HotNewsItem]

def parse_agent_output(raw: str) -> CurationResult:
    """Extract JSON from agent response, tolerant of surrounding text."""
    import re
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in agent output: {raw[:200]}")
    return CurationResult.model_validate_json(match.group())
```

- Prompt instruiert Agent explizit: "Return ONLY valid JSON, no explanation"
- Regex-Extraktion toleriert Freitext vor/nach dem JSON
- Bei Parse-Fehler → Fallback (alle Sources ungefiltert, leere Hot News)
- **Alternative:** Gemini `response_schema` / JSON Mode direkt im ADK Agent — robuster, aber ADK-Version-abhängig. Als Upgrade evaluieren wenn Parsing-Fehlerrate > 5%.

### C) Deployment-Lifecycle: Einmalig create(), wöchentlich query()

`ReasoningEngine.create()` deployt den Agent auf Vertex AI — das ist ein langsamer, teurer Einmal-Call, nicht Teil des wöchentlichen Flows.

**Korrekter Ablauf:**

```
Einmalig (beim Setup oder nach Agent-Update):
  python src/newsletter/deploy_agent.py
  → ReasoningEngine.create(app, ...)
  → Speichert agent_engine_id in Secret Manager: "newsletter-agent-engine-id"

Wöchentlich (Cloud Function newsletter_orchestrator):
  agent_engine_id = get_secret("newsletter-agent-engine-id")
  engine = ReasoningEngine(agent_engine_id)
  result = engine.query(input=build_agent_input(sources, week))
```

- `deploy_agent.py`: Separates Skript, nicht Teil der Cloud Function
- `agent_engine_id` in Secret Manager → keine Hardcode-IDs im Code
- Agent-Update (Prompt-Änderung) erfordert Redeployment via `deploy_agent.py`

### D) Qualitätssicherung: Dry-Run + Evaluation Loop

**Phase 1: Dry-Run-Modus (erste N Wochen)**
- Orchestrator läuft, aber kein Brevo-Versand
- Output wird in Firestore `newsletter_drafts` gespeichert: `{week, filtered_sources, hot_news, newsletter_html, status: "draft"}`
- Du reviewst manuell: Ist die Kuratierung gut? Werden Grenzfälle korrekt entschieden?
- Prompt-Iteration: `deploy_agent.py` neu ausführen nach Prompt-Anpassung

**Tracing:**
- `enable_tracing=True` in `AdkApp` → Traces in Cloud Trace (GCP Console)
- Zeigt welche Tools der Agent aufgerufen hat und in welcher Reihenfolge

**Übergang zu Live:**
- Status in Firestore von `"draft"` auf `"approved"` setzen → Delivery-Step wird freigeschaltet
- Optional: manuelles `approved`-Flag in Firestore, das Orchestrator prüft (Human-in-the-Loop)

---

## Stories

### Story 15.1 + 15.2: ADK Curation & Research Agent (kombiniert)

**Ziel:** Ein ADK Agent übernimmt Filterung UND News-Recherche — keine expliziten Bewertungsregeln nötig.

**Warum kombiniert:** Filter und Recherche sind zwei Seiten derselben redaktionellen Entscheidung.
Der Agent kann sie in einem Reasoning-Schritt verbinden: "Was aus meinem Lesen ist relevant für
meine Tech-Audience — und was lief in der Tech-Welt, das ich möglicherweise nicht gelesen habe?"

**Tech Setup:**
- Framework: [Google ADK](https://google.github.io/adk-docs/) (Python)
- Deployment: Vertex AI Agent Engine (managed runtime, kein eigener Container)
- Model: `gemini-3.1-pro-preview` (Reasoning-Qualität nötig)
- Tool: `google_search` (ADK built-in Tool, kein API Key nötig)
- Session: stateless (kein Gedächtnis zwischen Runs — jede Woche frisch)

**Tasks:**
1. ADK Agent definieren (`src/newsletter/curation_agent.py`):
   ```python
   from google.adk.agents import Agent
   from google.adk.tools import google_search

   curation_agent = Agent(
       name="newsletter_curator",
       model="gemini-3.1-pro-preview",
       tools=[google_search],
       instruction=CURATOR_SYSTEM_PROMPT,
   )
   ```
2. Agent-Prompt (`CURATOR_SYSTEM_PROMPT`):
   - Beschreibt Audience und Ziel (Tech/Engineering/Management)
   - Instruiert explizit: Grenzfälle mit Urteilsvermögen entscheiden, kein hartes Regelwerk
   - Definiert Output-Schema (JSON): `{filtered_sources, hot_news}`
3. Deployment auf Vertex AI Agent Engine:
   ```python
   from vertexai.preview import reasoning_engines
   app = reasoning_engines.AdkApp(agent=curation_agent, enable_tracing=True)
   agent_engine = reasoning_engines.ReasoningEngine.create(app, ...)
   ```
4. Orchestrator ruft Agent auf: `agent_engine.query(input={"sources": [...], "week": "2026-03-07"})`
5. Output-Schema validieren (Pydantic): `CurationResult(filtered_sources, hot_news)`
6. Fallback: wenn Agent-Call fehlschlägt → alle Sources ungefiltert an Generator übergeben,
   Hot News leer lassen (Newsletter erscheint trotzdem)
7. Tests: Mock Agent Engine response, Schema-Validierung, Fallback-Verhalten

**Acceptance Criteria:**
- Persönliche Themen (Erziehung, Sport, Ehe) werden zuverlässig ausgeschlossen
- Grenzfälle (z.B. Stoa-Artikel für Manager) werden kontextuell korrekt entschieden
- 3-5 Hot News Items pro Woche mit echten, verifizierbaren URLs
- Agent-Call < 30s (Vertex AI Agent Engine Latenz)
- Graceful Fallback bei Agent-Fehler

**Kosten:** ~$0.06–0.10/Woche (Gemini Pro, multi-turn Agent reasoning + Search calls)

---

### Story 15.3: Newsletter Generator

**Ziel:** Externer Newsletter aus gefilterten KX-Insights + Hot News generieren.

**Tasks:**
1. `generate_newsletter(filtered_sources, hot_news, period) -> NewsletterContent`
   - Model: `gemini-3.1-pro-preview`
   - Ton: Englisch, professionell-kuratorisch, external-facing (kein privater Stil)
   - Format: HTML Email + plain text fallback
   - **Sections:**
     - `## What I've Been Reading` — Synthese der gefilterten KX-Highlights (2-4 thematische Blöcke)
     - `## Hot in AI & Software This Week` — 3-5 Items aus Story 15.2
     - `## One Key Takeaway` — ein prägnanter Abschluss-Gedanke
     - Footer: Unsubscribe-Link, "Curated from personal reading via kx-hub"
2. HTML-Template: minimales, mobil-freundliches Design (kein Framework, inline CSS)
3. Subject-Line-Generator: Gemini Flash generiert 3 Optionen, erste wird verwendet
4. Frontmatter/Metadata für Firestore-Persistierung

**System Prompt (Auszug):**
```
You are writing a weekly tech newsletter called "Weekly Reading Notes".
Tone: Thoughtful curator, not academic. Like a smart colleague sharing what they found interesting.
Language: English.
No fluff. Every sentence should add value.
External audience: tech professionals, engineers, managers.
Your input contains only tech-relevant sources, pre-curated for this audience. Focus on synthesis and tone.
```

**Acceptance Criteria:**
- Englischer, professioneller Ton konsistent durch das gesamte Newsletter
- Alle Links sind externe URLs (keine internen kx-hub Links)
- HTML ist valide und mobil-kompatibel
- Subject Line ist konkret und spezifisch (keine generischen Betreff-Zeilen)

**Kosten:** ~$0.04/Batch (Gemini Pro, längerer Output)

---

### Story 15.4: Mailing List & Delivery Infrastructure

**Ziel:** Subscriber-Verwaltung und automatische E-Mail-Delivery via Brevo.

**Teilaufgaben:**

#### 15.4a: Brevo Setup & Subscriber-Verwaltung
1. Brevo Account einrichten (Free Tier: 300 Emails/Tag)
2. Brevo API Key in Secret Manager (`brevo-api-key`)
3. Newsletter-Liste in Brevo anlegen: `kx-weekly-tech`
4. Subscriber-Schema in Firestore `newsletter_subscribers`:
   ```json
   {
     "email": "user@example.com",
     "name": "...",
     "subscribed_at": "2026-03-06T...",
     "status": "active | unsubscribed | bounced",
     "brevo_contact_id": "...",
     "tags": ["tech", "early-adopter"]
   }
   ```

#### 15.4b: Subscribe/Unsubscribe Endpoints (Cloud Functions)
1. `POST /newsletter/subscribe` — Double-Opt-In:
   - E-Mail in Firestore als `pending` speichern
   - Confirmation E-Mail via Brevo senden
   - Confirmation Link: `GET /newsletter/confirm?token=...`
2. `GET /newsletter/confirm?token=...` — Bestätigung:
   - Status auf `active` setzen
   - In Brevo-Liste eintragen
3. `POST /newsletter/unsubscribe` — Abmeldung:
   - Status auf `unsubscribed` setzen
   - Aus Brevo-Liste entfernen
4. Brevo Webhook: Bounce/Spam-Complaint → Firestore Status updaten

#### 15.4c: Delivery Cloud Function
1. `send_newsletter(html, plain_text, subject)` via Brevo Campaigns API
2. Oder: Brevo Transactional API (simpler, pro-Subscriber-Call — OK für kleine Listen)
3. Delivery-Log in Firestore `newsletter_deliveries`:
   ```json
   {
     "sent_at": "...",
     "subject": "...",
     "recipient_count": 42,
     "brevo_campaign_id": "...",
     "period": "2026-03-01/2026-03-07"
   }
   ```
4. Cloud Scheduler: Sa 09:00 UTC (eine Stunde nach Generator-Run)

#### 15.4d: Minimal Signup Page (Optional MVP)
- Statische HTML-Seite auf Firebase Hosting oder Cloud Run
- Simples Formular: Name + E-Mail + Subscribe Button
- Ruft `/newsletter/subscribe` auf
- Mobile-freundlich, kein JS-Framework

**Acceptance Criteria:**
- Double-Opt-In funktioniert End-to-End
- Unsubscribe-Link in jedem Newsletter funktioniert
- Bounce-Handling: bounced Adressen werden nicht mehr kontaktiert
- Delivery-Log in Firestore für jede Woche

**Kosten:**
- Brevo Free Tier: $0 (bis 300 Emails/Tag)
- Cloud Functions (Signup/Unsub/Delivery): $0 (Free Tier)
- Firestore: $0 (Free Tier)
- Firebase Hosting: $0 (Free Tier, 10 GB/Monat)

---

## Output-Format (Newsletter-Prototype)

```
Subject: Weekly Reading Notes: AI Agents, Engineering Management & the Future of Code Review

---

## What I've Been Reading

### AI Agents & Multi-Agent Systems

This week I went deep on how production multi-agent systems actually work...
[2-3 Paragraphen Synthese aus KX-Highlights]

**Key sources:**
- [Building Production AI Agents (Author)](readwise-url)
- [🎙️ Podcast: AI in Production (Author)](snipd-url)

---

### Engineering Management

[Synthese zu Management-Themen]

---

## Hot in AI & Software This Week

1. **[News Title](url)** — 2-Satz Summary. Why it matters: ...
2. **[News Title](url)** — ...
3. **[News Title](url)** — ...

---

## One Key Takeaway

> "..."

---

*Weekly Reading Notes · Curated from personal reading via kx-hub*
*[Unsubscribe](unsubscribe-link) · [View in browser](html-url)*
```

---

## Kosten (Gesamt)

| Komponente | Monatlich |
|------------|-----------|
| ADK Curation & Research Agent (Gemini Pro, multi-turn, 4x/Monat) | ~$0.25–0.40 |
| Newsletter Generator (Gemini Pro, 4x/Monat) | ~$0.16 |
| Brevo Free Tier | $0 |
| Cloud Functions (Signup/Delivery/Orchestrator) | $0 |
| Firestore | $0 |
| Vertex AI Agent Engine (Hosting) | ~$0 (Serverless, pay-per-query) |
| **Gesamt** | **~$0.40–0.55/Monat** |

Bei Wachstum (>300 Subscriber): Brevo Starter $9/Monat für 5.000 Emails.

---

## Reihenfolge (empfohlen)

1. **Phase 1 (MVP):** ADK Agent (15.1+15.2) + Generator (15.3) — Dry-Run, Output in Firestore, kein Versand
   - N Wochen Dry-Run: Agent kuratiert, du reviewst Output manuell
   - Erst bei zufriedenstellender Qualität weiter zu Phase 2
2. **Phase 2:** Delivery (15.4a + 15.4c) — Brevo-Setup + manuelle Subscriber-Liste, automatischer Versand
3. **Phase 3 (bei Traction):** 15.4b + 15.4d — Self-Service Subscribe/Unsubscribe + Signup Page

---

## Architektur-Alternativen & mögliche Erweiterungen

### A) Multi-Agent statt Agent + separater Generator (mittelfristig)

Aktuelle Architektur: `ADK Curation Agent` → Cloud Function → `Gemini Pro Generator`

Elegantere Alternative mit ADK Multi-Agent:
```python
curator = Agent(name="curator", tools=[google_search], instruction=CURATOR_PROMPT)
writer  = Agent(name="writer",  tools=[],              instruction=WRITER_PROMPT)
orchestrator = Agent(
    name="newsletter_pipeline",
    sub_agents=[curator, writer],
    instruction="First curate sources, then write the newsletter."
)
```
- Ein Deployment, ein Invocation, ein Trace-Log
- Kein Glue-Code zwischen Curation und Generator
- **Trade-off:** Prompt-Iteration am Writer erfordert Redeployment des gesamten Orchestrators → weniger modular
- **Empfehlung:** MVP mit getrenntem Generator starten. Zu Multi-Agent migrieren wenn Pipeline stabil ist.

### B) Recurring Themes (Epic 9, Story 9.6) als Kontext für den Newsletter-Agent

Story 9.6 identifiziert wiederkehrende Themen aus den letzten N privaten Summaries.
Diese können dem Agent als Zusatz-Kontext mitgegeben werden:

```python
recurring = "Recurring themes from your last 4 weeks: AI Agents (3 weeks), Engineering Management (4 weeks)"
agent_input = build_agent_input(sources, week, recurring_context=recurring)
```

Der Agent kann dann "Du liest seit 3 Wochen über AI Agents — das ist ein Kern-Thema deines Newsletters."
Verbindet Epic 9 und Epic 15 elegant. Kein zusätzlicher LLM-Call nötig.

### C) kx_search als zweites Agent-Tool

Zusätzlich zu `google_search` kann der Agent auch die eigene Wissensbasis durchsuchen.

**Implementierung:** HTTP-Call auf den bestehenden MCP Cloud Run Server (einzige praktikable Option
auf Vertex AI Agent Engine — lokale Module können nicht importiert werden):

```python
import requests
from google.auth import default
from google.auth.transport.requests import Request
from google.adk.tools import tool

MCP_SERVER_URL = "https://mcp-server-xxx-uc.a.run.app"  # aus Env-Variable

@tool
def kx_search(query: str) -> str:
    """Search the user's personal knowledge base for highlights and summaries
    related to the given topic. Use this to check if the user has already read
    about a news topic and to enrich hot news with personal context."""
    creds, _ = default()
    creds.refresh(Request())
    resp = requests.post(
        MCP_SERVER_URL,
        json={"jsonrpc": "2.0", "method": "tools/call",
              "params": {"name": "search_kb", "arguments": {"query": query, "limit": 5}}},
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=10,
    )
    results = resp.json().get("result", {}).get("results", [])
    if not results:
        return "No relevant results found in knowledge base."
    lines = []
    for r in results:
        kc = r.get("knowledge_card", {})
        lines.append(f"- [{r['title']}] by {r['author']}: {kc.get('summary', '')}")
    return "\n".join(lines)

curation_agent = Agent(tools=[google_search, kx_search], ...)
```

**Infrastruktur-Voraussetzung:** Service Account des Agent Engine benötigt `roles/run.invoker`
auf dem MCP Cloud Run Service (eine Terraform-Zeile).

Der Agent kann dann: "Gibt es in meiner Wissensbasis schon Kontext zu diesem News-Thema?"
→ Hot News wird mit persönlichem Lesehintergrund angereichert. Unterscheidet den Newsletter
fundamental von generischen AI-Aggregatoren.

**Aufwand:** Gering (~20 Zeilen Code + 1 IAM-Zeile Terraform). **Wirkung:** Hoch.

**Sequenz (empfohlen):**
1. MVP: Agent mit nur `google_search` deployen + Dry-Run starten
2. Kuratierungsqualität reviewen (N Wochen)
3. Nach stabilem Dry-Run: `kx_search` als zweites Tool ergänzen (1 Commit)

### D) Brevo Subscriber-Management: MVP vereinfachen

Story 15.4 hat 4 Sub-Stories. Für einen Newsletter mit <10 Subscribern:

**Echter MVP:**
- Subscribers manuell in Brevo anlegen (Brevo UI)
- Cloud Function schickt via Brevo Transactional API direkt an Liste
- Kein Subscribe-Endpoint, keine Signup Page, kein Double-Opt-In-Code

15.4b (Endpoints) und 15.4d (Signup Page) erst implementieren wenn Subscriber-Anzahl das rechtfertigt.

### E) Generator System Prompt: Redundante Filterregel entfernen

Aktuell im Generator-Prompt:
> "Do NOT include personal topics (parenting, sports, self-help, etc.)"

Wenn der Curation Agent korrekt arbeitet, enthält der Generator-Input bereits nur gefilterte
Tech-Sources. Diese Regel veranlasst den Generator zu einem zweiten Filter-Pass — unnötig und
potenziell verwirrend bei bereits gefiltertem Input.

**Fix:** Ersetzen durch:
> "Your input contains only tech-relevant sources, pre-curated for a tech audience. Focus on synthesis and tone."

---

## Nicht-Ziele (MVP)

- Kein Custom Domain für Newsletter (kann Brevo-Domain verwenden)
- Kein A/B-Testing von Subject Lines
- Kein Segmenting nach Subscriber-Interessen
- Keine Paid-Tier-Funktionalität (Paywall, Premium-Subscriber)
- Keine eigene Unsubscribe-Page (Brevo-Standard reicht)
