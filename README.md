# kx-hub: Personal AI Knowledge Base

A serverless knowledge base that transforms reading highlights into a searchable, AI-enhanced personal knowledge system. Built on Google Cloud with Firestore vector search.

## What It Does

1. **Ingest** - Daily fetch of highlights from Readwise/Reader APIs
2. **Normalize** - Convert to structured Markdown with metadata
3. **Embed** - Generate vector embeddings (Vertex AI) and store in Firestore
4. **Cluster** - Auto-organize into semantic topic clusters (UMAP + HDBSCAN)
5. **Enhance** - Generate AI knowledge cards with summaries and takeaways
6. **Query** - Semantic search via MCP server for Claude Desktop/Mobile

## MCP Server

Query your knowledge base conversationally through Claude:

- **Unified search** - Semantic + metadata + time filters
- **Smart clusters** - 38 auto-discovered topics with relationships
- **Reading recommendations** - AI-powered suggestions from quality sources
- **Knowledge cards** - AI-generated summaries and key takeaways

**Example queries:**
- "Search my knowledge base for decision making articles from last month"
- "Show me my AI/ML cluster with related topics"
- "Give me reading recommendations based on my interests"

## Cost

~$1/month total:
- Vertex AI Embeddings: $0.10
- Firestore: $0.20
- Cloud Functions: $0.50
- Cloud Storage: $0.20

(99% reduction from original $100+/month with Vertex AI Vector Search)

## Project Structure

```
kx-hub/
├── src/
│   ├── mcp_server/      # MCP server (Cloud Run)
│   ├── embed/           # Embedding Cloud Function
│   ├── ingest/          # Readwise ingestion
│   ├── normalize/       # Markdown normalization
│   ├── clustering/      # Semantic clustering
│   ├── knowledge_cards/ # AI card generation
│   └── llm/             # LLM abstraction (Gemini/Claude)
├── functions/           # Cloud Function deployments
├── tests/               # Unit and integration tests
├── docs/                # Documentation
├── terraform/           # Infrastructure as Code
└── scripts/             # Utility scripts
```

## Tech Stack

- **Runtime**: Python 3.12, Cloud Functions Gen2, Cloud Run
- **Database**: Firestore with native vector search
- **AI/ML**: Vertex AI (Gemini), Anthropic Claude
- **Infrastructure**: Terraform
- **Protocol**: Model Context Protocol (MCP)

## Development

```bash
# Run tests
python3 -m pytest tests/ -v

# Deploy MCP server (via Cloud Build)
gcloud builds submit --config=src/mcp_server/cloudbuild.yaml

# Deploy Cloud Function
gcloud functions deploy <function> --gen2 --region=europe-west1
```

## Documentation

See `docs/` for:
- `prd.md` - Product requirements
- `architecture.md` - System design
- `epics.md` - Current work status
- `backlog.md` - Future ideas
- `TODO.md` - Immediate tasks

See `CLAUDE.md` for development guidelines.

## Status

**Complete:**
- Daily Readwise/Reader ingestion
- Embedding & Firestore vector search
- Semantic clustering (38 topics)
- Knowledge card generation
- Remote MCP server with OAuth
- Reading recommendations

**In Progress:**
- Epic 4: Knowledge Graph (entity/relation extraction)

---

*Personal project - Single developer*
