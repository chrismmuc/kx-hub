# Project Brief: Personal AI Knowledge Base

## Executive Summary

**Personal AI Knowledge Base** is an automated knowledge management system that transforms daily reading highlights and articles from Readwise/Reader into actionable insights. The system uses Google Cloud's Vertex AI for embeddings and semantic analysis to surface novel connections, generate knowledge cards, provide AI-powered reading recommendations, and enable conversational knowledge access via Claude Desktop.

**Primary Problem:** Knowledge workers collect vast amounts of information but lack tools to discover connections, synthesize insights, get smart reading recommendations, and retrieve relevant knowledge when needed.

**Target Market:** Individual knowledge workers using Readwise/Reader who want AI-powered insight generation and intelligent knowledge retrieval.

**Key Value Proposition:** A fully automated, serverless pipeline on Google Cloud (~$5/month) that transforms reading data into a queryable, recommendation-enabled knowledge system.

---

## Proposed Solution

A serverless Google Cloud pipeline with three capabilities:

**1. Automated Insight Generation (Push)**
- Daily Readwise/Reader ingestion
- Vertex AI embeddings + semantic clustering
- Knowledge cards with summaries and takeaways

**2. On-Demand Knowledge Retrieval (Pull)**
- Claude Desktop integration via MCP server
- Firestore vector search for semantic queries
- Cluster exploration and relationship discovery

**3. AI-Powered Recommendations (Active)**
- Tavily-powered article discovery
- Multi-factor ranking (relevance, recency, depth, authority)
- KB deduplication and source diversity

---

## Success Metrics

- **Query Response**: <1s semantic search (P95)
- **Recommendation Quality**: ≥80% relevant top-10 results
- **Cost Control**: ~$5/month operational cost
- **Coverage**: 100% items processed within 24h

---

## Technical Stack

- **Platform**: Google Cloud Serverless (Functions, Firestore, Cloud Storage)
- **AI**: Vertex AI (gemini-embedding-001, Gemini 2.5 Flash)
- **Search**: Tavily API for recommendations
- **Interface**: MCP Server for Claude Desktop
- **Estimated Cost**: ~$5/month

---

## Epics Overview

| Epic | Description | Status |
|------|-------------|--------|
| 1 | Core Batch Processing Pipeline | Complete |
| 2 | Enhanced Knowledge Graph & Clustering | Complete |
| 3 | Knowledge Graph Enhancement & Optimization | Active (50%) |
| 4 | Intelligent Reading Synthesis | Planned |

See [prd.md](./prd.md) for full requirements and [epics.md](./epics.md) for story details.