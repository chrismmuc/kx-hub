# CLAUDE.md - Project Guidelines for kx-hub

## Project Overview

Personal knowledge hub that ingests highlights from Readwise, generates AI-powered knowledge cards, and provides semantic search via MCP server. Single developer, private project.

## Core Principles

### 1. Security First
- Never expose API keys, tokens, or credentials in code or logs
- Use Google Secret Manager for all secrets
- Validate all inputs, especially from external sources
- Review dependencies for known vulnerabilities before updating

### 2. Cost Awareness
- Prefer Gemini Flash / Claude Haiku for routine tasks
- Use batch operations where possible (Firestore, embeddings)
- Monitor API usage and set budget alerts in GCP
- Avoid unnecessary API calls - cache where appropriate

### 3. Test-Driven Development
- Write tests before implementing features
- Run `python3 -m pytest tests/` before committing
- Aim for meaningful test coverage, not 100% coverage
- Mock external services (Firestore, Vertex AI, etc.)

### 4. Infrastructure as Code
- Use Terraform for all infrastructure changes
- Avoid manual changes in GCP Console - codify everything
- Keep Terraform state in GCS bucket
- Review `terraform plan` before applying

### 5. Current Libraries
- Always use Context7 (`mcp__context7__*`) to look up current library documentation
- Use WebSearch for latest best practices when uncertain
- Check PyPI versions periodically: `pip3 index versions <package>`
- Keep dependencies updated (run dependency audit monthly)

## Development Workflow

### Commits
- Commit frequently with meaningful messages
- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`
- **Ask before pushing** - confirm with user before `git push`

### Code Style
- Python 3.12+
- Type hints where practical
- Docstrings for public functions
- Keep functions focused and small

## Project Structure

```
kx-hub/
├── src/                    # Main source code
│   ├── mcp_server/         # MCP server (tools, resources, prompts)
│   ├── embed/              # Embedding generation Cloud Function
│   ├── ingest/             # Readwise ingestion Cloud Function
│   ├── normalize/          # Markdown normalization
│   ├── clustering/         # Semantic clustering
│   ├── knowledge_cards/    # AI-powered knowledge card generation
│   └── llm/                # LLM abstraction layer (Gemini/Claude)
├── functions/              # Cloud Function deployments
├── tests/                  # Unit and integration tests
├── docs/                   # Documentation (BMAD-lite style)
│   ├── prd.md              # Product requirements
│   ├── architecture.md     # System architecture
│   ├── epics.md            # Epic overview and status
│   └── backlog.md          # Feature backlog
├── terraform/              # Infrastructure as Code
└── scripts/                # Utility scripts
```

## Documentation (BMAD-Lite)

Keep documentation lightweight and actionable:
- **prd.md**: What we're building and why (high-level)
- **architecture.md**: System design, key decisions
- **epics.md**: Current work, acceptance criteria
- **backlog.md**: Future ideas, prioritized

Avoid: Excessive detail, duplicated information, outdated specs.

## Key Commands

```bash
# Run tests
python3 -m pytest tests/ -v

# Check specific test file
python3 -m pytest tests/test_<name>.py -v

# Check dependency versions
pip3 index versions <package>

# Deploy Cloud Function
gcloud functions deploy <function> --gen2 --region=europe-west1

# Start MCP server locally
cd src/mcp_server && python3 server.py
```

## Tech Stack

- **Runtime**: Python 3.12, Cloud Functions Gen2
- **Database**: Firestore (with vector search)
- **AI/ML**: Vertex AI (Gemini), Anthropic Claude
- **Infrastructure**: Terraform, Cloud Run, Cloud Storage
- **MCP**: Model Context Protocol for AI assistant integration

## Current Focus

Check `docs/epics.md` and `docs/sprint-status.yaml` for active work.
