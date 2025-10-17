# Project Brief: Personal AI Knowledge Base

## Executive Summary

**Personal AI Knowledge Base** is an automated knowledge management system that transforms daily reading highlights and articles from Readwise/Reader into actionable insights. The system uses Google Cloud's Vertex AI for embeddings and semantic analysis to surface novel connections between notes, generate knowledge cards with summaries, deliver weekly digests, and provide on-demand query-driven retrieval to surface relevant content.

**Primary Problem:** Knowledge workers collect vast amounts of information but lack automated tools to discover non-obvious connections, synthesize insights, and quickly retrieve relevant knowledge when facing specific challenges.

**Target Market:** Individual knowledge workers and researchers using Readwise/Reader who want to leverage a unified AI platform for automated insight generation and intelligent knowledge retrieval.

**Key Value Proposition:** A fully automated, serverless pipeline on Google Cloud that transforms raw reading data into a queryable knowledge system, requiring zero manual curation while maintaining a low, predictable, pay-per-use cost model.

---

## Problem Statement

Knowledge workers face a critical challenge: their collected knowledge remains siloed and underutilized. Despite capturing countless highlights and articles, they struggle to see the bigger picture, discover hidden connections, and retrieve the right information when they need it most. This leads to forgotten insights and wasted time.

---

## Proposed Solution

**Personal AI Knowledge Base** is a fully automated, serverless Google Cloud pipeline that addresses this challenge with two core capabilities:

**1. Automated Insight Generation (Push Model)**
- Daily ingestion of new Readwise/Reader content.
- Vertex AI Embeddings enable a deep semantic understanding of all content.
- Automated clustering identifies thematic groupings.
- Weekly email digests surface new additions and synthesized insights.

**2. On-Demand Knowledge Retrieval (Pull Model)**
- A natural language query interface (CLI/API).
- Vertex AI Vector Search provides fast, accurate, and scalable semantic search.
- Returns a ranked list of the most relevant articles, highlights, and book sections.

**Core Differentiators:**
- **Zero Manual Curation**: A fully automated pipeline from ingestion to insight.
- **Unified & Scalable**: Built entirely on Google Cloud and Vertex AI for simplicity and scalability.
- **Cost-Effective**: A serverless, pay-per-use architecture keeps costs low.
- **Integrated**: Exports to familiar PKM tools like Obsidian via GitHub.

---

## Target Users

Our target users are tech-savvy knowledge workers, researchers, writers, and product managers who are already using tools like Readwise/Reader and are comfortable with a CLI/API-first approach. They are looking for a powerful, low-cost way to activate their captured knowledge.

---

## Goals & Success Metrics

### Business Objectives
- **Deliver Automated Value**: Transform a passive collection into an active knowledge system.
- **Maintain Cost Sustainability**: Keep monthly operational costs under ~$5 for typical usage.
- **Technical Validation**: Prove the serverless Google Cloud architecture is efficient and scalable.

### User Success Metrics
- **Effective Knowledge Retrieval**: Users find relevant content in under 2 seconds.
- **Valuable Insight Discovery**: Users report discovering useful connections in their weekly digest.
- **Seamless Workflow Integration**: Obsidian sync via GitHub works reliably.

---

## MVP Scope

### Core Features (Must Have)

- **Automated Ingestion**: Daily, scheduled pulls from Readwise/Reader APIs.
- **Semantic Processing**: Embedding generation and indexing using Vertex AI.
- **Knowledge Generation**: Summaries and synthesis using Vertex AI generative models.
- **Query-Driven Retrieval (CLI/API)**: An endpoint to submit natural language queries.
- **GitHub Export**: Automated export of markdown files to a GitHub repository.
- **Weekly Email Digest**: Automated email of new and synthesized content.

### Out of Scope for MVP

- Multi-user support or team features.
- A web-based UI (Phase 2).
- Real-time processing.

---

## Technical Considerations

- **Platform**: Google Cloud (Serverless)
  - Cloud Functions for all compute.
  - API Gateway for the query endpoint.
  - Pub/Sub and Cloud Workflows for orchestration.
- **AI**: Google Vertex AI
  - `text-embedding-004` for embeddings.
  - `Gemini 1.5 Flash` for generative tasks.
  - `Vertex AI Vector Search` for similarity search.
- **Backend**: Python 3.11+
- **Database**: Firestore for metadata, Cloud Storage for files.
- **Hosting**: Google Cloud Serverless, Pay-Per-Use model.
- **Estimated Cost**: ~$5/month.

---

## Risks & Open Questions

- **API Rate Limiting**: Readwise/Reader API limits could impact ingestion speed. **Mitigation**: Implement exponential backoff and robust error handling.
- **Cost Overruns**: Unexpectedly high usage could increase costs. **Mitigation**: Set up Cloud Billing alerts.
- **AI Model Quality**: The quality of generated summaries and insights needs to be validated. **Mitigation**: Iterative prompt engineering and testing.

---