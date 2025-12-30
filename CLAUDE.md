# CLAUDE.md - kx-hub

Personal knowledge hub: Readwise highlights → AI knowledge cards → semantic search via MCP.

## Commands

```bash
# Tests (run before every commit)
python3 -m pytest tests/ -v

# Deploy MCP server
gcloud builds submit --config=src/mcp_server/cloudbuild.yaml

# Deploy Cloud Function
gcloud functions deploy <function> --gen2 --region=europe-west1

# Check dependency versions
pip3 index versions <package>
```

## Tech Stack

- Python 3.12, Cloud Functions Gen2, Cloud Run
- Firestore (vector search), Vertex AI (Gemini), Anthropic Claude
- Terraform for infrastructure

## Core Rules

1. **Security** - Use Secret Manager, never expose credentials
2. **Cost** - Prefer Gemini Flash / Haiku, batch operations, cache
3. **Tests** - Run pytest before commits, mock external services
4. **Terraform** - All infra changes via code, review `terraform plan`
5. **Current libs** - Use Context7 for docs, WebSearch for best practices

## Workflow

- Commit frequently, conventional commits (`feat:`, `fix:`, `chore:`)
- **Ask before pushing**
- Update `docs/epics.md` when completing features
- Run tests before commit, all must pass (262+ expected)

## Docs

5 files in `docs/` - keep current:
- `prd.md` - What and why
- `architecture.md` - System design
- `epics.md` - Work status
- `backlog.md` - Future ideas
- `TODO.md` - Immediate tasks

## Project Layout

```
src/
├── mcp_server/      # MCP server (Cloud Run)
├── embed/           # Embedding function
├── ingest/          # Readwise ingestion
├── clustering/      # UMAP + HDBSCAN
├── knowledge_cards/ # AI summaries
└── llm/             # Gemini/Claude abstraction
```

See `docs/epics.md` for current focus.
