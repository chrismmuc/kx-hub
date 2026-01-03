# Kommerzialisierung kx-hub

**Stand:** 2026-01-02

## Zusammenfassung

kx-hub als SaaS-Produkt für Knowledge Worker – Machbarkeitsanalyse und rechtliche Rahmenbedingungen für den deutschen Markt.

---

## 1. Produkt-Idee

**Value Proposition:** Persönliches "Second Brain" mit:
- Automatische Verarbeitung von Readwise/Reader Highlights
- KI-Zusammenfassungen (Knowledge Cards)
- Semantische Suche über alle Inhalte
- Claude Desktop Integration (MCP)
- AI-powered Reading Recommendations

**Zielgruppe:** Knowledge Worker, Researcher, Consultants, Power-Reader

**Pricing:** €15-25/Monat

---

## 2. Stärken & Schwächen

### Pro

| Aspekt | Details |
|--------|---------|
| Echter Pain Point | Information Overload ist Massenproblem |
| Technisch differenziert | MCP + Semantic Search + KI-Summaries |
| Niedrige Kosten | ~€3/User/Monat Infrastruktur |
| Proof of Market | Readwise hat 100k+ zahlende Kunden |

### Contra

| Aspekt | Details |
|--------|---------|
| Wettbewerb | Readwise, Mem, Notion AI, Reflect, Tana |
| Readwise-Abhängigkeit | Aktuell einzige Datenquelle |
| MCP ist Nische | Web UI für Mainstream nötig |
| Multi-Tenancy fehlt | Signifikanter Umbau für SaaS |

---

## 3. Einkommensszenarien (Nebenerwerb)

Alle Zahlen sind **netto nach Steuern** – das landet auf dem Konto.

### Kalkulation

| Kunden | Brutto | - Kosten | - Steuern (~38%) | **Netto verfügbar** |
|--------|--------|----------|------------------|---------------------|
| 50 | €750 | €200 | €210 | **~€340** |
| 100 | €1.500 | €400 | €420 | **~€680** |
| 200 | €3.000 | €700 | €875 | **~€1.425** |
| 300 | €4.500 | €1.000 | €1.330 | **~€2.170** |
| 500 | €7.500 | €1.600 | €2.240 | **~€3.660** |

### Kostenaufschlüsselung

- Infrastruktur: ~€3/User/Monat (Google Cloud, Vertex AI)
- Payment Fees: ~3% (Stripe)
- Tools & Marketing: €100-300/Monat
- Steuerberater: €50-100/Monat

### Nebenerwerb-Vorteile

- Keine zusätzliche Krankenversicherung (läuft über Hauptjob)
- Keine Rentenversicherungspflicht
- Kleinunternehmerregelung möglich (bis €22k/Jahr keine USt)
- Verluste absetzbar gegen Haupteinkommen
- Kein finanzielles Risiko

---

## 4. Rechtliche Anforderungen

### ⚠️ KRITISCH: Readwise API

**Problem:** Die [Readwise ToS](https://readwise.io/tos) verbieten kommerzielle Nutzung explizit:

> "you agree not to [...] sell, resell, grant access to, transfer, or otherwise use or exploit any portion of the Service for any commercial purposes"

**Lösung erforderlich:**
1. Readwise kontaktieren (hello@readwise.io) für kommerzielle Lizenz
2. Oder: Alternative Datenquellen als Haupteingang entwickeln

### Unternehmensform

| Form | Haftung | Kosten | Empfehlung |
|------|---------|--------|------------|
| Einzelunternehmen | Unbeschränkt | €0 | Start/Test |
| UG (haftungsbeschränkt) | Beschränkt | €500-1.000 | Ab €1k/Monat Gewinn |
| GmbH | Beschränkt | €1.500-3.000 | Ab €5k+/Monat |

### DSGVO/GDPR

| Anforderung | Status |
|-------------|--------|
| Datenschutzerklärung | Erforderlich |
| AV-Vertrag mit Google Cloud | Standard-DPA vorhanden |
| Rechtsgrundlage (Art. 6) | Vertragserfüllung |
| Löschkonzept | Zu implementieren |
| Datenexport für User | Zu implementieren |

### Website-Pflichten (Deutschland)

- **Impressum** (§5 TMG): Name, Adresse, Kontakt, USt-ID
- **AGB**: Nutzungsbedingungen, Haftung, Kündigung
- **Cookie-Banner**: Opt-in für nicht-essentielle Cookies
- **Widerrufsrecht**: 14 Tage für B2C

### Google Cloud / Vertex AI

- ✅ Kommerzielle Nutzung erlaubt
- ✅ Output gehört dir
- ⚠️ Kein "konkurrierendes Produkt" zu Google AI
- Siehe: [Google Cloud Service Terms](https://cloud.google.com/terms/service-terms)

### Steuern

| Pflicht | Details |
|---------|---------|
| Umsatzsteuer | 19% (oder Kleinunternehmerregelung bis €22k) |
| Einkommensteuer | Grenzsteuersatz ~35-42% bei Nebenerwerb |
| Gewerbesteuer | Ab ~€24.500 Gewinn (Freibetrag) |

---

## 5. Startkosten (einmalig)

| Posten | Kosten |
|--------|--------|
| Gewerbeanmeldung | €30 |
| Anwalt (DSGVO + AGB) | €1.000-2.500 |
| UG-Gründung (optional) | €500-1.000 |
| Steuerberater (Setup) | €200-500 |
| **Gesamt** | **€1.700 - €4.000** |

---

## 6. Technische Anforderungen für SaaS

Aktuell fehlt:

| Feature | Aufwand | Priorität |
|---------|---------|-----------|
| Multi-Tenancy | Hoch | Kritisch |
| Web UI | Mittel-Hoch | Hoch |
| User Authentication | Mittel | Kritisch |
| Billing Integration (Stripe) | Mittel | Kritisch |
| Alternative Datenquellen | Mittel | Hoch (wg. Readwise ToS) |
| Account-Löschung (DSGVO) | Niedrig | Kritisch |
| Datenexport (DSGVO) | Niedrig | Erforderlich |

---

## 7. Nächste Schritte

### Phase 1: Validierung (vor jeder Entwicklung)

1. [ ] Readwise kontaktieren für kommerzielle API-Lizenz
2. [ ] 10 potenzielle Beta-User identifizieren
3. [ ] Landing Page + Waitlist erstellen
4. [ ] Zahlungsbereitschaft validieren

### Phase 2: MVP für SaaS

1. [ ] Multi-Tenancy Architektur
2. [ ] Web UI (Option A aus Epic 6)
3. [ ] User Authentication (Firebase Auth / Auth0)
4. [ ] Stripe Integration
5. [ ] Alternative Datenquellen (Web Clipper, PDF Upload)

### Phase 3: Launch

1. [ ] Gewerbeanmeldung
2. [ ] AGB + Datenschutzerklärung (Anwalt)
3. [ ] Impressum
4. [ ] Beta-Launch mit 10-50 Usern
5. [ ] Feedback-Loop + Iteration

---

## 8. Risiken

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Readwise verweigert Lizenz | Mittel | Kritisch | Alternative Datenquellen |
| Zu wenig Nachfrage | Mittel | Hoch | Frühe Validierung |
| Starker Wettbewerb | Hoch | Mittel | Nische fokussieren |
| DSGVO-Verstoß | Niedrig | Kritisch | Anwalt einbeziehen |
| Google Cloud Kosten steigen | Niedrig | Mittel | Multi-Cloud Option |

---

## Quellen

- [Readwise Terms of Service](https://readwise.io/tos)
- [Google Cloud Service Terms](https://cloud.google.com/terms/service-terms)
- [DSGVO & SaaS - Bodle Law](https://www.bodlelaw.com/saas/saas-agreements-gdpr-new-german-data-protection-law-bdsg)
- [AGB für B2B-SaaS - Simpliant](https://simpliant.eu/insights/so-entwerfen-sie-agb-fuer-b2b-saas-business)
- [Website Compliance Germany](https://allaboutberlin.com/guides/website-compliance-germany)
