# KX-Hub Architecture Documentation

## Table of Contents

- [KX-Hub Architecture Documentation](#table-of-contents)
  - [Overview](./overview.md)
  - [System Architecture](./system-architecture.md)
    - [Batch Processing Pipeline (Daily)](./system-architecture.md#batch-processing-pipeline-daily)
    - [On-Demand Query Flow (User-Initiated)](./system-architecture.md#on-demand-query-flow-user-initiated)
  - [MCP Integration](./mcp-integration.md) - Model Context Protocol architecture (local stdio)
  - [Remote MCP Server](./remote-mcp.md) - OAuth 2.1 + Streamable HTTP for Claude.ai
  - [Document Chunking](./document-chunking.md)
    - [Chunk Schema](./chunk-schema.md)
    - [Chunking Monitoring](./chunking-monitoring.md)
  - [AI Provider Integration (Vertex AI)](./ai-provider-integration-vertex-ai.md)
    - [Architecture](./ai-provider-integration-vertex-ai.md#architecture)
    - [Secrets Management](./ai-provider-integration-vertex-ai.md#secrets-management)
  - [Data Flow Details](./data-flow-details.md)
    - [Batch Pipeline (Cloud Workflows Orchestration)](./data-flow-details.md#batch-pipeline-cloud-workflows-orchestration)
    - [Query Flow (Synchronous API)](./data-flow-details.md#query-flow-synchronous-api)
  - [Cost Optimization & Scaling](./cost-optimization-scaling.md)
    - [Strategy](./cost-optimization-scaling.md#strategy)
    - [Estimated Monthly Costs](./cost-optimization-scaling.md#estimated-monthly-costs)
  - [Scaling & Upgrade Paths](./scaling-upgrade-paths.md)
  - [Security & Best Practices](./security-best-practices.md)
    - [IAM Least-Privilege](./security-best-practices.md#iam-least-privilege)
    - [Monitoring & Alerting](./security-best-practices.md#monitoring-alerting)
    - [Infrastructure as Code (IaC)](./security-best-practices.md#infrastructure-as-code-iac)
    - [Deployment](./security-best-practices.md#deployment)
