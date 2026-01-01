# Knowledge Management: State-of-the-Art (2024/2025)

> **Ziel dieses Dokuments:** Umfassende Übersicht über moderne Ansätze im Wissensmanagement – von Knowledge Graphs über Ontologien bis hin zu Clustering und RAG – mit Fokus auf AI-gestützte Automatisierung und Self-Maintenance.

**Letzte Aktualisierung:** 2026-01-01

---

## Inhaltsverzeichnis

1. [Übersicht der Ansätze](#übersicht-der-ansätze)
2. [Knowledge Graphs + AI-generierte Relationships](#knowledge-graphs--ai-generierte-relationships)
3. [Ontologien](#ontologien)
4. [Clustering-Ansätze](#clustering-ansätze)
5. [Vector Search & RAG](#vector-search--rag)
6. [GraphRAG & LightRAG](#graphrag--lightrag)
7. [AI Memory Systeme](#ai-memory-systeme)
8. [Personal Knowledge Management (PKM)](#personal-knowledge-management-pkm)
9. [Vergleich: Was eignet sich wofür?](#vergleich-was-eignet-sich-wofür)
10. [AI Self-Maintenance: Was funktioniert?](#ai-self-maintenance-was-funktioniert)
11. [Empfehlung für kx-hub](#empfehlung-für-kx-hub)
12. [Referenzen](#referenzen)

---

## Übersicht der Ansätze

| Ansatz | Stärke | Schwäche | AI-Maintenance |
|--------|--------|----------|----------------|
| **Knowledge Graph** | Explizite Beziehungen, Multi-Hop Reasoning | Setup-Aufwand, Schema-Design | ✅ LLM-Extraktion möglich |
| **Ontologie** | Formale Semantik, Konsistenz | Rigid, manuelle Pflege | ⚠️ LLM-assisted Schema-Induktion |
| **Clustering (UMAP/HDBSCAN)** | Unsupervised, schnell | Keine semantische Bedeutung | ✅ Vollautomatisch |
| **Vector Search (RAG)** | Einfach, schnell, flexibel | Keine Relationen, flach | ✅ Vollautomatisch |
| **GraphRAG** | Beste Qualität, Global Queries | Teuer, langsam, kein Inkrement | ⚠️ Rebuild erforderlich |
| **LightRAG** | Schnell, günstig, inkrementell | Weniger relational | ✅ Inkrementelle Updates |
| **AI Memory (Cognee/Mem0)** | Agent-Integration, persistent | Komplexität | ✅ Selbst-lernend |

---

## Knowledge Graphs + AI-generierte Relationships

### Was sind Knowledge Graphs?

Knowledge Graphs repräsentieren Wissen als Netzwerk von **Entitäten** (Nodes) und **Beziehungen** (Edges). Anders als bei reinem Vector Search sind die Verbindungen **explizit und typisiert**.

```
[Tiago Forte] --wrote--> [Building a Second Brain]
                              |
                         --extends-->
                              |
[David Allen] --wrote--> [Getting Things Done]
```

### LLM-gestützte Konstruktion

Die Landschaft hat sich 2024/2025 dramatisch verändert:

> "What once required specialized NLP expertise, months of manual annotation, and expensive infrastructure can now be accomplished in days using large language models."
> — [Medium: From LLMs to Knowledge Graphs](https://medium.com/@claudiubranzan/from-llms-to-knowledge-graphs-building-production-ready-graph-systems-in-2025-2b4aff1ec99a)

**State-of-the-Art Tools:**

| Tool | Beschreibung | Link |
|------|--------------|------|
| **Neo4j LLM Graph Builder** | Automatische Extraktion aus PDFs, Docs, YouTube | [neo4j.com/labs](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/) |
| **AutoSchemaKG** | Schema-freie KG-Konstruktion mit LLMs (HKUST) | [arxiv.org](https://arxiv.org/html/2510.20345v1) |
| **AutoKG** | Multi-Agent KG-Konstruktion | [github.com/zjunlp/AutoKG](https://github.com/zjunlp/AutoKG) |
| **LangChain Graph Transformer** | Integration in LangChain-Pipelines | [docs.langchain.com](https://python.langchain.com/docs/how_to/graph_constructing/) |

### Relationship Types

Die gängigsten AI-extrahierten Relationship Types:

- `relates_to` – Allgemeine thematische Verbindung
- `extends` – Baut auf, entwickelt weiter
- `supports` – Liefert Evidenz, bestätigt
- `contradicts` – Widerspricht, hinterfragt
- `applies_to` – Praktische Anwendung
- `causes` / `influences` – Kausale Beziehungen
- `is_part_of` / `has_component` – Hierarchische Strukturen

### Herausforderungen

1. **Schema vs. Schema-frei**: Schema-freie Extraktion generiert tausende Entity-Typen; Schema-basiert ist präziser aber weniger flexibel
2. **Qualitätskontrolle**: LLMs können halluzinieren; Confidence Scores und Validierung wichtig
3. **Skalierung**: Pairwise-Vergleiche explodieren bei großen Dokumentmengen

**Referenzen:**
- [IBM Research: State of the Art LLMs for KG Construction](https://research.ibm.com/publications/the-state-of-the-art-large-language-models-for-knowledge-graph-construction-from-text-techniques-tools-and-challenges)
- [Neo4j LLM Knowledge Graph Builder - 2025 Release](https://neo4j.com/blog/developer/llm-knowledge-graph-builder-release/)
- [GitHub: KG-LLM-Papers (curated list)](https://github.com/zjukg/KG-LLM-Papers)

---

## Ontologien

### Definition & Abgrenzung

> "An ontology is like a blueprint for a house, defining structure and rules, but it's not the house itself. If ontologies are the blueprint, knowledge graphs are the actual house."
> — [Enterprise Knowledge](https://enterprise-knowledge.com/whats-the-difference-between-an-ontology-and-a-knowledge-graph/)

| Ontologie | Knowledge Graph |
|-----------|-----------------|
| Generalisiertes Schema (Klassen, Properties) | Instanzdaten (konkrete Entitäten) |
| Hand-kuratiert, klein | Kann Milliarden Assertions enthalten |
| Formale Logik (OWL, RDF) | Flexiblere Strukturen |
| Definiert *was möglich ist* | Enthält *was existiert* |

### Ontologie + LLM

Moderne Ansätze kombinieren beides:

> "Knowledge graphs that actually follow an ontology will have an LLM perform better than just a KG that is unharmonized."
> — [Cognee Blog](https://www.cognee.ai/blog/deep-dives/ontology-ai-memory)

**Vorteile der Kombination:**
- **Konsistenz**: Ontologie definiert erlaubte Relationship-Types
- **Interoperabilität**: Standard-Vocabularies (Wikidata, Schema.org)
- **Reasoning**: Inferenz-Regeln können angewendet werden

**AI-Automatisierung:**
- Schema-Induktion aus Text (95% Alignment mit manuellen Schemas möglich)
- Automatisches Mapping auf Standard-Ontologien via Embedding-Similarity

**Referenzen:**
- [Medium: Semantic Model vs Ontology vs Knowledge Graph](https://medium.com/@cassihunt/semantic-model-vs-ontology-vs-knowledge-graph-untangling-the-latest-data-modeling-terminology-12ce7506b455)
- [Hedden: Ontologies vs Knowledge Graphs](https://www.hedden-information.com/ontologies-vs-knowledge-graphs/)
- [Neo4j: Ontologies in Neo4j](https://neo4j.com/blog/ontologies-in-neo4j-semantics-and-knowledge-graphs/)

---

## Clustering-Ansätze

### UMAP + HDBSCAN Pipeline

Der klassische Ansatz für unsupervised Wissensorganisation:

```
Dokumente → Embeddings → UMAP → HDBSCAN → Cluster/Topics
              (768-dim)   (5-10 dim)    (density-based)
```

**Warum UMAP?**
> "The goal is to use UMAP to perform non-linear manifold aware dimension reduction so you can get the dataset down to a number of dimensions small enough for a density-based clustering algorithm to make progress."
> — [UMAP Documentation](https://umap-learn.readthedocs.io/en/latest/clustering.html)

**Warum HDBSCAN?**
- Erkennt Cluster unterschiedlicher Dichte
- Keine Vorab-Definition der Cluster-Anzahl
- Identifiziert Outlier explizit (vs. K-Means das alles zuweist)

**Performance-Verbesserungen:**
- Bis zu 60% Accuracy-Verbesserung durch UMAP Pre-Processing
- Laufzeit von 26 Minuten auf 5 Sekunden reduziert (MNIST)

### BERTopic

BERTopic ist der State-of-the-Art für semantisches Topic Modeling:

```python
from bertopic import BERTopic
model = BERTopic()
topics, probs = model.fit_transform(documents)
```

**Architektur:**
1. **Embedding**: Sentence-Transformers (default: all-MiniLM-L6-v2)
2. **Dimensionsreduktion**: UMAP (n_neighbors=15, n_components=5)
3. **Clustering**: HDBSCAN (min_cluster_size=10)
4. **Topic-Repräsentation**: c-TF-IDF

**Best Practices:**
- `n_neighbors`: 10-30 für Balance zwischen lokal/global
- `min_dist`: Niedrig setzen für dichtere Cluster
- `min_cluster_size`: Haupthebel für Anzahl Topics
- `random_state` setzen für Reproduzierbarkeit

**Referenzen:**
- [BERTopic Documentation](https://maartengr.github.io/BERTopic/)
- [Pinecone: Advanced Topic Modeling with BERTopic](https://www.pinecone.io/learn/bertopic/)
- [IEEE: Improving HDBSCAN with Word Embedding and UMAP](https://ieeexplore.ieee.org/document/9640285/)

---

## Vector Search & RAG

### Grundprinzip

```
Query → Embedding → Similarity Search → Top-K Chunks → LLM → Answer
```

**Vorteile:**
- Einfach zu implementieren
- Semantische Suche (nicht nur Keywords)
- Gut skalierbar

**Limitationen:**
> "In the process of vectorization there is a risk in losing deep relational understanding; it can't easily link cause-and-effect, nor follow chains of related facts."
> — [Paragon Blog](https://www.useparagon.com/blog/vector-database-vs-knowledge-graphs-for-rag)

### Wann Vector RAG?

| ✅ Gut für | ❌ Schlecht für |
|-----------|----------------|
| Semantic Search | Multi-Entity Queries |
| Getting Started | Relationale Fragen |
| Dynamische Daten | "Wie hängt X mit Y zusammen?" |
| Customer Service | Aggregations-Fragen |

**Benchmark-Ergebnisse:**
- Vector RAG: 0% Accuracy bei Schema-bound Queries (KPIs, Forecasts)
- Accuracy degradiert bei >5 Entities pro Query ohne KG-Support

**Referenzen:**
- [Neo4j: Knowledge Graph vs Vector RAG](https://neo4j.com/blog/developer/knowledge-graph-vs-vector-rag/)
- [Meilisearch: GraphRAG vs Vector RAG](https://www.meilisearch.com/blog/graph-rag-vs-vector-rag)
- [Weaviate: Exploring RAG and GraphRAG](https://weaviate.io/blog/graph-rag)

---

## GraphRAG & LightRAG

### Microsoft GraphRAG

> "GraphRAG is a structured, hierarchical approach to RAG, as opposed to naive semantic-search approaches using plain text snippets."
> — [Microsoft Research](https://www.microsoft.com/en-us/research/project/graphrag/)

**Prozess:**
1. **Extraktion**: LLM extrahiert Entities + Relationships aus Text
2. **Community Detection**: Graph wird in Communities aufgeteilt
3. **Summarization**: Jede Community erhält LLM-Summary
4. **Hierarchie**: Bottom-up Zusammenfassung für Global Queries

**Query Modes:**
- **Global Search**: Nutzt Community-Summaries für holistische Fragen
- **Local Search**: Fan-out zu Nachbar-Nodes
- **DRIFT Search**: Kombiniert Community-Context
- **Basic Search**: Standard Top-K Vector Search

**Stärken:**
- Beantwortet Fragen, die über gesamten Datensatz aggregieren
- 3.4x besser als Vector RAG (Diffbot Benchmark)
- Explainable: Pfade sind nachvollziehbar

**Schwächen:**
- **Teuer**: ~$6-7 für ein 32k-Wort-Buch (GPT-4o)
- **Langsam**: Viele LLM-Calls
- **Kein Inkrement**: Rebuild bei neuen Dokumenten

### LightRAG

> "LightRAG combines the speed of VectorRAG with the deeper reasoning of GraphRAG using a dual-level retrieval framework."
> — [LearnOpenCV](https://learnopencv.com/lightrag/)

**Architektur:**
1. **Dual-Level Retrieval**: Vector-Search + Graph-Reasoning
2. **Incremental Updates**: Neue Docs werden in bestehenden Graph gemerged
3. **Lightweight Graph**: Weniger dichte KG-Struktur

**Performance vs GraphRAG:**

| Metrik | GraphRAG | LightRAG |
|--------|----------|----------|
| Tokens pro Query | 610,000 | ~100 |
| Response Time | Seconds | ~200ms |
| Cost Factor | 1x | 1/6000x |
| Incremental Update | Full Rebuild | ~50% weniger Overhead |

**Einschränkung:** Unabhängige Evaluation zeigt kleinere Vorteile als behauptet (Win Rate 39% statt 67% vs NaiveRAG)

**Referenzen:**
- [Microsoft GraphRAG GitHub](https://github.com/microsoft/graphrag)
- [Microsoft Research: GraphRAG Project](https://www.microsoft.com/en-us/research/project/graphrag/)
- [LightRAG Paper (arXiv)](https://arxiv.org/pdf/2410.05779)
- [LightRAG Official Site](https://lightrag.github.io/)

---

## AI Memory Systeme

### Cognee

> "Instead of just embedding documents and fetching them, cognee combines vector search with a semantic knowledge graph."
> — [Cognee GitHub](https://github.com/topoteretes/cognee)

**Key Features:**
- Vector + Graph kombiniert
- On-the-fly Knowledge Graph Konstruktion
- LangGraph/LangChain Integration
- Multi-Session Memory für Agents

**ECL Pipeline (Extract, Cognify, Load):**
```python
import cognee
await cognee.add("Your data")
await cognee.cognify()  # Builds KG + embeddings
results = await cognee.search("Your query")
```

**Use Case:** AI Agents mit persistentem, relationalem Gedächtnis

**Referenzen:**
- [Cognee GitHub](https://github.com/topoteretes/cognee)
- [Cognee: LangGraph Integration](https://www.cognee.ai/blog/integrations/langgraph-cognee-integration-build-langgraph-agents-with-persistent-cognee-memory)
- [Cognee: Graph-Based Retrieval](https://www.cognee.ai/blog/deep-dives/enhancing-llm-responses-with-graph-based-retrieval-and-advanced-chunking-techniques)

### Mem0

> "Mem0 is a scalable memory-centric architecture that dynamically extracts, consolidates, and retrieves salient information from ongoing conversations."
> — [Mem0 Paper (arXiv)](https://arxiv.org/abs/2504.19413)

**Architektur:**
- **Vector Memory**: Embeddings für semantische Suche
- **Graph Memory**: Entities + Relationships für relationale Queries
- **Dynamic Operations**: ADD, UPDATE, DELETE, NOOP basierend auf LLM-Entscheidung

**Benchmark-Ergebnisse:**
- 26% Verbesserung über OpenAI im LLM-as-a-Judge Metric
- 91% niedrigere P95 Latency
- >90% Token-Cost-Ersparnis

**Mem0 vs Mem0 mit Graph:**
- Base Mem0: Besser für einfache Retrieval-Tasks
- Mem0 + Graph: Besser für temporales und relationales Reasoning

**Referenzen:**
- [Mem0 GitHub](https://github.com/mem0ai/mem0)
- [Mem0 Paper](https://arxiv.org/abs/2504.19413)
- [Mem0 Research: 26% Accuracy Boost](https://mem0.ai/research)
- [AWS: Mem0 with Neptune Analytics](https://aws.amazon.com/blogs/database/build-persistent-memory-for-agentic-ai-applications-with-mem0-open-source-amazon-elasticache-for-valkey-and-amazon-neptune-analytics/)

---

## Personal Knowledge Management (PKM)

### Second Brain Methodik

> "A second brain is a digital system designed to store all your notes, to-dos, projects, and ideas. It's a comprehensive PKM approach that helps keep track of thoughts and knowledge in a centralized way."
> — [Taskade Blog](https://www.taskade.com/blog/how-ai-can-help-you-build-a-second-brain)

**PARA Framework:**
- **P**rojects: Aktive, zeitgebundene Vorhaben
- **A**reas: Langfristige Verantwortungsbereiche
- **R**esources: Referenzmaterial nach Themen
- **A**rchives: Inaktive Items aus den anderen drei

### AI-Integration in PKM

**AI-Capabilities:**
- Automatische Kategorisierung und Tagging
- Semantic Search über alle Notes
- Content-Generierung aus bestehenden Notes
- Automatische Backlinks und Verbindungen

**Tools mit AI-Features:**

| Tool | AI Features | Besonderheit |
|------|-------------|--------------|
| **Obsidian** + Plugins | Embedding Search, AI Chat | Lokal, Plain-Text, extensible |
| **Reflect Notes** | AI Summaries, Insights | Networked Thought + AI |
| **Mem.ai** | Automatische Organisation | Sprachsuche, Timeline |
| **Heptabase** | Visual Knowledge Maps | Infinite Canvas + Graph |
| **Anytype** | Graph-basierte Organisation | Offline-first, Open Source |

**Referenzen:**
- [ToolFinder: Best PKM Apps 2025](https://toolfinder.co/lists/best-pkm-apps)
- [ACM: From PKM to Personal AI Companion](https://dl.acm.org/doi/10.1145/3688828.3699647)
- [Glukhov: Personal Knowledge Management 2025](https://www.glukhov.org/post/2025/07/personal-knowledge-management/)

---

## Vergleich: Was eignet sich wofür?

### Decision Matrix

| Use Case | Empfohlener Ansatz | Begründung |
|----------|-------------------|------------|
| **Schneller Start** | Vector RAG | Einfach, funktioniert sofort |
| **Beziehungen verstehen** | Knowledge Graph | Explizite Relationen |
| **Domain-spezifisch** (Medizin, Recht) | KG + Ontologie | Formale Semantik wichtig |
| **Große Dokumentmengen** | LightRAG | Balance Qualität/Kosten |
| **Global Queries** ("Was sind die Hauptthemen?") | GraphRAG | Community Summaries |
| **AI Agent Memory** | Cognee / Mem0 | Persistent, relational |
| **Topic Discovery** | BERTopic | Unsupervised, schnell |
| **Personal Notes** | Obsidian + AI | Flexibel, erweiterbar |

### Cost-Quality Tradeoff

```
                    High Quality
                         ↑
                         |     GraphRAG
                         |        ●
                         |
              Mem0+Graph |    ●
                         |          LightRAG
                 Cognee  |  ●    ●
                         |
              Vector RAG | ●
                         |
                         +------------------------→ Low Cost

                         Clustering/BERTopic
                              ●  (sehr günstig, andere Dimension)
```

---

## AI Self-Maintenance: Was funktioniert?

### Automatisierungsgrad nach Ansatz

| Ansatz | Initial Setup | Laufende Pflege | Self-Healing |
|--------|--------------|-----------------|--------------|
| **Vector RAG** | ✅ Vollautomatisch | ✅ Vollautomatisch | ✅ N/A |
| **Clustering** | ✅ Vollautomatisch | ⚠️ Re-Clustering bei neuen Daten | ✅ |
| **Knowledge Graph** | ⚠️ Schema-Design | ✅ LLM-Extraktion | ⚠️ Konfliktauflösung |
| **Ontologie** | ❌ Manuell | ⚠️ LLM-assisted Updates | ❌ |
| **GraphRAG** | ⚠️ Compute-intensiv | ❌ Rebuild erforderlich | ❌ |
| **LightRAG** | ✅ Automatisch | ✅ Inkrementell | ⚠️ |
| **Cognee/Mem0** | ✅ Automatisch | ✅ Self-learning | ✅ Dynamic Ops |

### Was sich durch AI selbst maintainen lässt

**✅ Vollständig automatisierbar:**
1. **Embedding-Generierung**: Standardtask, zuverlässig
2. **Entity Extraction**: LLMs extrahieren Entities mit 95%+ Präzision
3. **Relationship Extraction**: Funktioniert gut mit Confidence-Filtering
4. **Schema-Induktion**: AutoSchemaKG zeigt 95% Alignment mit manuellen Schemas
5. **Incremental Updates**: LightRAG, Mem0 unterstützen dies nativ

**⚠️ Teilweise automatisierbar (Human-in-the-Loop empfohlen):**
1. **Schema-Konsolidierung**: LLMs generieren zu viele Types ohne Guidance
2. **Konflikt-Auflösung**: Widersprüchliche Informationen brauchen Review
3. **Qualitätskontrolle**: Stichproben-Validierung wichtig
4. **Ontologie-Evolution**: Strukturelle Änderungen riskant

**❌ Nicht vollständig automatisierbar:**
1. **Domain-spezifische Ontologien**: Fachwissen erforderlich
2. **Business Rules**: Unternehmenskontext muss eingebracht werden
3. **Strategische Entscheidungen**: Welche Relationship-Types relevant sind

### Empfohlene Automatisierungsstrategie

```
                    ┌─────────────────────────┐
                    │   Ingest (Readwise)     │  ← Vollautomatisch
                    └───────────┬─────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   Embed + Store         │  ← Vollautomatisch
                    └───────────┬─────────────┘
                                ↓
         ┌──────────────────────┼──────────────────────┐
         ↓                      ↓                      ↓
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ Knowledge Cards │   │  Relationships  │   │   Clustering    │
│  (Summaries)    │   │  (Cross-Source) │   │   (Optional)    │
└─────────────────┘   └─────────────────┘   └─────────────────┘
         ↓                      ↓                      ↓
         └──────────────────────┼──────────────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   Periodic Review       │  ← Quarterly Manual
                    │   (Schema, Quality)     │
                    └─────────────────────────┘
```

---

## Empfehlung für kx-hub

### Aktueller Stand (Epic 4)

kx-hub nutzt bereits:
- ✅ **Vector Search** (Firestore FIND_NEAREST)
- ✅ **Knowledge Cards** (Gemini-generierte Summaries)
- ✅ **Cross-Source Relationships** (LLM-extrahiert)
- ✅ **Source-Based Organisation** (statt Cluster)

### Bewertung der Entscheidung

| Aspekt | Cluster (alt) | Sources + Relationships (neu) |
|--------|--------------|-------------------------------|
| Semantik | ❌ Keine | ✅ Explizit typisiert |
| Cross-Source | ❌ Trivial (same-source) | ✅ Valuable Connections |
| Maintenance | ⚠️ Re-Clustering | ✅ Inkrementelle Extraktion |
| Query Types | ❌ Nur Similarity | ✅ Multi-Hop möglich |

**Fazit:** Die Umstellung auf Sources + Relationships war die richtige Entscheidung.

### Potentielle Erweiterungen

1. **LightRAG Integration**: Für schnellere, günstigere Relationship-Extraktion
2. **Schema-Guidance**: Begrenzte Relationship-Types statt Open Extraction
3. **Mem0/Cognee für MCP**: Persistente Memory für Claude-Conversations
4. **BERTopic für Discovery**: Automatische Topic-Gruppierung als Overlay

### Nicht empfohlen für kx-hub

- **Full GraphRAG**: Zu teuer und compute-intensiv für Personal KB
- **Formale Ontologie**: Overhead für PKM-Use-Case zu hoch
- **Clustering als primäre Struktur**: Bereits korrekt durch Sources ersetzt

---

## Referenzen

### Research Papers

- [LLMs for KG Construction and Reasoning (2023)](https://arxiv.org/abs/2305.13168) - Foundational survey
- [Mem0: Building Production-Ready AI Agents (2025)](https://arxiv.org/abs/2504.19413) - Memory architecture
- [LightRAG Paper (2024)](https://arxiv.org/pdf/2410.05779) - Efficient Graph-RAG
- [Knowledge Graph Construction Survey (2025)](https://arxiv.org/html/2510.20345v1) - Comprehensive review

### Tools & Frameworks

| Tool | Link | Category |
|------|------|----------|
| **Neo4j LLM Graph Builder** | [neo4j.com/labs](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/) | KG Construction |
| **Microsoft GraphRAG** | [github.com/microsoft/graphrag](https://github.com/microsoft/graphrag) | GraphRAG |
| **LightRAG** | [lightrag.github.io](https://lightrag.github.io/) | GraphRAG |
| **Cognee** | [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee) | AI Memory |
| **Mem0** | [github.com/mem0ai/mem0](https://github.com/mem0ai/mem0) | AI Memory |
| **BERTopic** | [maartengr.github.io/BERTopic](https://maartengr.github.io/BERTopic/) | Topic Modeling |
| **AutoKG** | [github.com/zjunlp/AutoKG](https://github.com/zjunlp/AutoKG) | KG Construction |

### Comparison Articles

- [Neo4j: Knowledge Graph vs Vector RAG](https://neo4j.com/blog/developer/knowledge-graph-vs-vector-rag/)
- [Meilisearch: GraphRAG vs Vector RAG](https://www.meilisearch.com/blog/graph-rag-vs-vector-rag)
- [Enterprise Knowledge: Ontology vs Knowledge Graph](https://enterprise-knowledge.com/whats-the-difference-between-an-ontology-and-a-knowledge-graph/)
- [Medium: Semantic Model vs Ontology vs KG](https://medium.com/@cassihunt/semantic-model-vs-ontology-vs-knowledge-graph-untangling-the-latest-data-modeling-terminology-12ce7506b455)

### PKM Resources

- [ToolFinder: Best PKM Apps 2025](https://toolfinder.co/lists/best-pkm-apps)
- [Taskade: AI for Second Brain](https://www.taskade.com/blog/how-ai-can-help-you-build-a-second-brain)
- [ACM: From PKM to AI Companion (2025)](https://dl.acm.org/doi/10.1145/3688828.3699647)

### GitHub Curated Lists

- [KG-LLM-Papers](https://github.com/zjukg/KG-LLM-Papers) - Papers on KG + LLM Integration
- [Awesome Knowledge Graph](https://github.com/totogo/awesome-knowledge-graph) - General KG Resources

---

*Dieses Dokument wird als Teil der kx-hub Dokumentation gepflegt und sollte bei wesentlichen Änderungen im Knowledge-Management-Bereich aktualisiert werden.*
