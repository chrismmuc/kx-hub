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
  │      └─ Tool: google_search (built-in ADK)
  │      └─ Input: sources as context + week date
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
Do NOT include personal topics (parenting, sports, self-help, etc.).
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
| Gemini Flash (Classifier, 4x) | ~$0.01 |
| Gemini Pro + Search Grounding (Hot News, 4x) | ~$0.08 |
| Gemini Pro (Newsletter Generator, 4x) | ~$0.06 |
| Brevo Free Tier | $0 |
| Cloud Functions (Signup/Delivery) | $0 |
| Firestore | $0 |
| **Gesamt** | **~$0.15/Monat** |

Bei Wachstum (>300 Subscriber): Brevo Starter $9/Monat für 5.000 Emails.

---

## Reihenfolge (empfohlen)

1. **Phase 1 (MVP):** 15.1 + 15.2 + 15.3 — Generator ohne Delivery (dry-run, Output in Firestore)
2. **Phase 2:** 15.4a + 15.4c — Brevo-Integration + manuell kuratierte Subscriber-Liste
3. **Phase 3:** 15.4b + 15.4d — Self-Service Subscribe/Unsubscribe + Signup Page
4. **Optional:** 15.2b — ADK Agent für komplexere News-Recherche (nur wenn Qualität unzureichend)

---

## Nicht-Ziele (MVP)

- Kein Custom Domain für Newsletter (kann Brevo-Domain verwenden)
- Kein A/B-Testing von Subject Lines
- Kein Segmenting nach Subscriber-Interessen
- Keine Paid-Tier-Funktionalität (Paywall, Premium-Subscriber)
- Keine eigene Unsubscribe-Page (Brevo-Standard reicht)
