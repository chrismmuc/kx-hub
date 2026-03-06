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
- Gemini Flash klassifiziert jede Source beim Einstieg in die Newsletter-Pipeline
- Nur als extern-relevant eingestufte Sources werden an den Generator übergeben
- Vorteil: Präzise Kontrolle, keine Themen-Blending durch den Generator
- Nachteil: ~2x LLM-Aufrufe (classify + generate)

**Option B: Post-Processing der privaten Summary**
- Bestehende private Summary als Input, LLM soll "nur Tech-Teil" extrahieren
- Nachteil: LLM neigt dazu, Themen zu vermischen; Kontext aus Nicht-Tech-Quellen beeinflusst Formulierungen

**Entscheidung:** Option A — mehr Compute, aber deutlich zuverlässiger. Bei 10-20 Sources/Woche
kosten die Classifier-Calls ~$0.001 (Gemini Flash).

### 2. Agent-Ansatz für Hot News: ADK vs. direktes Gemini Grounding

**Option A: Vertex AI ADK Agent** mit Google Search Tool
- Volle Kontrolle: Agent kann mehrere Suchanfragen planen und kombinieren
- Deployment auf Vertex AI Agent Engine (managed) oder Cloud Run
- Komplexer zu deployen, aber flexibler

**Option B: Gemini direkt mit Google Search Grounding** ← **Gewählt für MVP**
- Ein einziger Gemini-API-Call mit `google_search` Grounding aktiviert
- Deutlich simpler: kein Agent-Framework, kein separates Deployment
- Vertex AI unterstützt Grounding nativ in `GenerationConfig`
- Einschränkung: Keine multi-step reasoning; Gemini entscheidet selbst welche Searches nötig sind

**Migration-Pfad:** Beginne mit Gemini Grounding (MVP, Story 15.2). Falls die Qualität nicht ausreicht
oder komplexere Recherche-Logik benötigt wird, migriere auf Vertex AI ADK Agent (Story 15.2b).

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

## Topic Allowlist / Denylist

### Extern-relevante Themen (Allowlist)
```
technology, software engineering, artificial intelligence, machine learning,
large language models, developer tools, cloud computing, system design,
engineering management, technical leadership, product management,
innovation, startup, venture capital, business strategy, organizational design,
data science, security, open source, API design, architecture
```

### Nicht für externen Newsletter (Denylist)
```
parenting, family, marriage, relationships, religion, spirituality,
sports, fitness, nutrition, cooking, self-help, personal finance,
psychology (personal), mindfulness, meditation, personal productivity
(non-tech), travel, fashion, real estate
```

**Classifier-Prompt:** Gemini Flash bekommt Titel + Author + Knowledge Card Summary und
klassifiziert in: `tech` | `management` | `mixed` | `personal`. Nur `tech` und `management`
kommen in den Newsletter; `mixed` nur wenn der Tech-Anteil > 60%.

---

## Technische Architektur

```
Cloud Scheduler (wöchentlich, Sa 08:00 UTC)
  │
  ▼
Cloud Function: newsletter_generator
  │
  ├─ 1. Fetch recent chunks (last 7 days) ← reuse from Epic 9 data_pipeline
  │
  ├─ 2. Topic Classifier (Story 15.1)
  │      └─ Gemini Flash: classify each source
  │      └─ Filter: keep tech + management sources only
  │
  ├─ 3. Hot News Research (Story 15.2)
  │      └─ Gemini Pro + Google Search Grounding
  │      └─ Query: "Top AI and software engineering news this week [date]"
  │      └─ Output: 3-5 structured news items
  │
  ├─ 4. Newsletter Generator (Story 15.3)
  │      └─ Gemini Pro: compose external newsletter
  │      └─ Input: filtered sources + hot news
  │      └─ Output: HTML + plain text
  │
  └─ 5. Delivery (Story 15.4)
         └─ Brevo API: send to subscriber list
         └─ Firestore: log delivery metadata
         └─ Save newsletter to Firestore `newsletters` collection
```

---

## Stories

### Story 15.1: Topic Classifier

**Ziel:** LLM-basierte Klassifizierung jeder Source in Themenbereiche; Filterung auf extern-relevante Topics.

**Tasks:**
1. `classify_sources(sources: List[Source]) -> List[ClassifiedSource]`
   - Input: Source-Liste aus Epic 9 data_pipeline
   - LLM: Gemini Flash (`gemini-2.5-flash`)
   - Batch-Verarbeitung: alle Sources in einem Call (Kosten-Optimierung)
   - Output: jede Source mit `topic_category` (`tech` | `management` | `mixed` | `personal`) und `topic_confidence` (0.0-1.0)
2. `filter_external_sources(classified: List[ClassifiedSource]) -> List[Source]`
   - Behalte: `tech`, `management`, `mixed` (wenn confidence > 0.6)
   - Verwerfe: `personal`
3. Classifier-Prompt: Titel + Author + Knowledge Card Summary → Kategorie
4. Tests: Mock LLM, Filter-Logik, Edge Cases (leere Liste, alle personal)

**Acceptance Criteria:**
- Sources korrekt klassifiziert (manuell verifiziert an 10-Beispiel-Set)
- Personal-Themen zuverlässig herausgefiltert
- Batch-Call: alle Sources in ≤ 2 LLM-Calls (unabhängig von Source-Anzahl)
- Performance: < 5s für 20 Sources

**Kosten:** ~$0.001/Batch (Gemini Flash)

---

### Story 15.2: Hot News Research Agent

**Ziel:** Gemini mit Google Search Grounding recherchiert wöchentlich die wichtigsten AI & Software-Neuigkeiten.

**MVP-Ansatz:** Gemini Pro mit `google_search` Grounding (kein ADK Agent nötig)

**Tasks:**
1. `research_hot_news(week_end_date: str) -> List[NewsItem]`
   - Model: `gemini-3.1-pro-preview` mit Google Search Grounding aktiviert
   - Query: `"Top AI, machine learning and software engineering news week of {date}"`
   - Output-Schema: `List[NewsItem]` mit `title`, `summary` (2-3 Sätze), `source_url`, `why_relevant`
   - Max 5 Items, sortiert nach Relevanz
2. Structured output via Gemini JSON mode
3. Fallback: wenn Search Grounding fehlschlägt, 0 Hot News (Newsletter geht trotzdem raus)
4. Tests: Mock Gemini response, Schema-Validierung

**Vertex AI ADK Migration (Story 15.2b, Optional):**
Wenn Qualität nicht ausreichend oder multi-step Research gewünscht:
- ADK Agent mit `google_search` Tool + `KXHub search` Tool
- Agent plant eigenständig mehrere Suchanfragen
- Deployment auf Vertex AI Agent Engine oder Cloud Run
- Aufwand: ~1-2 Tage zusätzlich

**Acceptance Criteria:**
- 3-5 relevante News-Items pro Woche
- Kein Crash bei Search-Grounding-Fehler (graceful fallback)
- Structured output ist schema-konform
- Keine Halluzinationen: alle URLs sind echte, verlinkte Quellen aus Search-Ergebnissen

**Kosten:** ~$0.02/Batch (Gemini Pro + Search Grounding calls)

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
