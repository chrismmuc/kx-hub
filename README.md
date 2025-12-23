# kx-hub: Personal AI Knowledge Base

A serverless knowledge base system that automatically transforms your daily reading highlights and articles into a searchable, semantically indexed personal knowledge base. Built on Google Cloud with Firestore and Vertex AI.

## 🎯 What It Does

**Daily Pipeline (Automated):**
1. 📥 **Ingest**: Fetches new reading highlights from Readwise/Reader APIs
2. 📝 **Normalize**: Converts raw JSON to Markdown with YAML metadata
3. 🧮 **Embed**: Generates vector embeddings using Vertex AI and stores in Firestore
4. 🔍 **Query**: Semantic search across your knowledge base (coming soon)

**Current Status:** Stories 1.1-1.7 fully implemented and production-ready.

## 🤖 MCP Server for Claude Desktop

Query your knowledge base conversationally through Claude Desktop using natural language - no context switching required!

**Features:**
- 🔍 **Unified search**: Semantic + metadata + time filters in one tool
- 📊 **Smart clusters**: Auto-organized topics with related cluster discovery
- 🎯 **Reading recommendations**: AI-powered suggestions from quality sources
- 💡 **Knowledge cards**: AI-generated summaries and key takeaways
- ⚡ **Optimized**: 9 consolidated tools (down from 25), 64% reduction
- 💰 **Cost-effective**: ~$0.15/month additional cost

**Quick Start:**
```bash
# See setup guide
cat docs/guides/mcp-setup.md
```

**Example Queries:**
- "Search my knowledge base for articles about decision making from last month"
- "Show me my AI/ML cluster with related topics"
- "Give me reading recommendations based on what I've been reading"
- "What did I read yesterday with activity summary?"

→ [Setup Guide](docs/guides/mcp-setup.md) | [MCP Tools API](docs/reference/mcp-tools-api.md) | [User Guide](docs/guides/mcp-usage.md)

## 💰 Cost

- **Monthly Operating Cost**: ~$0.90/month
- **Previous Approach**: $100+/month (Vertex AI Vector Search)
- **Savings**: 99% cost reduction

Breakdown:
- Vertex AI Embeddings: $0.10
- Firestore Vector Search: $0.10
- Cloud Functions: $0.50
- Cloud Storage & Firestore: $0.20

## 🏗️ Architecture

### Core Components

| Component | Purpose | Technology |
|-----------|---------|-----------|
| **Ingest** | Fetch from Readwise/Reader | Cloud Function (Python 3.11) |
| **Normalize** | JSON → Markdown | Cloud Function (Python 3.11) |
| **Embed** | Generate & store vectors | Cloud Function (Python 3.11) |
| **Orchestration** | Pipeline coordination | Cloud Workflows |
| **Trigger** | Daily scheduling | Cloud Scheduler (2 AM UTC) |
| **Vector Storage** | Search & retrieval | Firestore native vectors |
| **Embedding Model** | Generate vectors | Vertex AI `gemini-embedding-001` |

### Data Flow

```
Cloud Scheduler (daily 2am)
    ↓
Cloud Function: Ingest
    ├→ Readwise API + Reader API
    └→ Cloud Storage (raw-json bucket)
        ↓
Cloud Workflows orchestration
    ├→ Normalize Function
    │   └→ Cloud Storage (markdown-normalized bucket)
    │       ↓
    ├→ Embed Function
    │   ├→ Vertex AI Embeddings (gemini-embedding-001)
    │   └→ Firestore kb_items collection + vector index
    │
    └→ Pipeline state tracking (Firestore pipeline_items)
```

## 📁 Project Structure

```
kx-hub/
├── src/
│   ├── ingest/           # Cloud Function: Fetch highlights from APIs
│   ├── normalize/        # Cloud Function: JSON → Markdown
│   └── embed/            # Cloud Function: Generate embeddings & store
├── tests/
│   ├── test_ingest.py
│   ├── test_normalize.py
│   ├── test_embed.py
│   └── fixtures/         # Test data
├── terraform/
│   ├── main.tf          # Infrastructure definitions
│   ├── variables.tf
│   ├── providers.tf
│   └── workflows/       # Cloud Workflows YAML
├── docs/
│   ├── architecture/    # Technical architecture
│   ├── prd/            # Product requirements
│   └── stories/        # User story implementations
└── README.md (this file)
```

## 🚀 Quick Start

### Prerequisites

- GCP project with Vertex AI, Cloud Functions, Firestore enabled
- Readwise and/or Reader API credentials
- Terraform installed
- Python 3.11+

### Deployment

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/kx-hub.git
   cd kx-hub
   ```

2. **Configure Terraform variables**
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your GCP project ID and region
   ```

3. **Deploy infrastructure**
   ```bash
   terraform plan
   terraform apply
   ```

4. **Add API credentials to Secret Manager**
   ```bash
   echo -n "your-readwise-api-key" | gcloud secrets create /kx-hub/readwise/api-key --data-file=-
   ```

5. **Trigger the first pipeline**
   ```bash
   gcloud scheduler jobs run daily-ingest-trigger-job --location=europe-west3
   ```

## 📊 Data Model

### Firestore Collections

**`pipeline_items`** - Processing status and retry metadata
- `doc_id`: Document identifier
- `status`: `pending`, `processing`, `complete`, `failed`
- `retry_count`: Number of retry attempts
- `manifest_run_id`: Current pipeline run ID
- `embedding_status`: `pending`, `processing`, `complete`, `failed`

**`kb_items`** - Knowledge base with embeddings
- `title`: Document title
- `url`: Source URL
- `authors`: List of authors
- `tags`: Document tags
- `content_hash`: SHA256 of markdown content
- `embedding`: Vector (768 dimensions) for semantic search
- `embedding_status`: `complete`, `failed`
- `created_at`, `updated_at`: Timestamps
- `last_embedded_at`: When vector was generated
- `last_run_id`: Pipeline run that created the vector

## 🔧 Configuration

### Environment Variables

Set in Cloud Function configuration:
- `GCP_PROJECT`: GCP project ID (auto-set by Terraform)
- `GCP_REGION`: Region for Vertex AI API (default: `europe-west4`)
- `MARKDOWN_BUCKET`: Cloud Storage bucket for normalized markdown
- `PIPELINE_BUCKET`: Cloud Storage bucket for pipeline artifacts
- `PIPELINE_COLLECTION`: Firestore collection name (default: `pipeline_items`)

### Secrets (Google Secret Manager)

- `/kx-hub/readwise/api-key`: Readwise API key
- `/kx-hub/reader/api-key`: Reader API key (optional)
- `/kx-hub/github/token`: GitHub token (for future export feature)

## 🧪 Testing

Run unit tests locally:

```bash
# Test all functions
python3 -m unittest discover tests -v

# Test specific function
python3 -m unittest tests.test_embed -v
```

Tests use mocked GCP services and include:
- API response handling
- Error cases and retries
- Firestore writes
- Embedding generation

## 📚 Documentation

- **[Architecture](docs/architecture/)** - System design, data flows, security
- **[PRD](docs/prd/)** - Product requirements and specifications
- **[Stories](docs/stories/)** - User story implementations
- **[Brief](docs/brief.md)** - Executive summary

## 🔐 Security

- **Least-privilege IAM**: Each service account has minimal required permissions
- **Secret Management**: API keys stored in Google Secret Manager
- **No shared credentials**: Each Cloud Function has its own service account
- **Audit logging**: All operations logged to Cloud Logging
- **Data encryption**: In-transit (TLS) and at-rest (GCP default)

## 📈 Monitoring

Monitor pipeline execution:

```bash
# List recent workflow executions
gcloud workflows executions list batch-pipeline --location=europe-west4 --limit=5

# Get detailed execution info
gcloud workflows executions describe EXECUTION_ID --location=europe-west4

# View function logs
gcloud functions log read embed-function --limit=50
```

## 🛣️ Roadmap

**Completed:**
- ✅ Daily ingest from Readwise/Reader
- ✅ Markdown normalization
- ✅ Embedding generation & Firestore storage
- ✅ Cost optimization (99% reduction)

**In Progress:**
- 🔄 Firestore vector search query function
- 🔄 Unit test updates for Firestore vectors

**Future:**
- 📅 Semantic clustering & topic extraction
- 🔗 Knowledge graph generation
- 📝 AI-generated summaries
- 🔄 Export to GitHub (Obsidian sync)
- 📧 Email digests

## 🤝 Contributing

This is a personal project, but improvements welcome:

1. Create a feature branch
2. Make your changes
3. Run tests: `python3 -m unittest discover tests -v`
4. Submit a PR

## 📝 License

[Add your license here]

## 📧 Support

For issues or questions, check the documentation in `/docs` or open a GitHub issue.

---

**Last Updated:** October 2025
**Current Maintainer:** You
**Architecture Version:** v3 (Firestore Vector Search)
