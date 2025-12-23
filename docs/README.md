# KX-Hub Documentation

Welcome to the KX-Hub documentation. This knowledge exchange hub uses AI to help you discover, explore, and connect insights from your reading materials.

## Quick Navigation

### User Guides
Start here if you want to set up or use KX-Hub:
- **[Setup & Usage Guides](guides/)** - Installation, deployment, and usage instructions

### Technical Reference
Looking for API documentation or configuration details:
- **[API & Configuration Reference](reference/)** - MCP tools API and server configuration

### Architecture
Understanding how KX-Hub works internally:
- **[Architecture Documentation](architecture/)** - System design, data flow, and integration patterns

## Key Documents

### Product Planning
- **[Product Brief](brief.md)** - Project vision and goals
- **[Product Requirements](prd.md)** - Feature requirements and specifications
- **[Epics](epics.md)** - Epic-level planning and story breakdown

### Project Status
- **[Sprint Status](sprint-status.yaml)** - Current sprint tracking
- **[BMM Workflow Status](bmm-workflow-status.yaml)** - BMAD workflow tracking
- **[Future Features](future-features.md)** - Planned enhancements

### Historical
- **[Sprint Change Proposals](sprints/)** - Archived sprint planning decisions

## Getting Started

### For End Users
1. Start with [MCP Setup Guide](guides/mcp-setup.md) for local Claude Desktop integration
2. Learn to use the tools with [MCP Usage Guide](guides/mcp-usage.md)

### For Developers
1. Review [System Architecture](architecture/system-architecture.md)
2. Understand [MCP Integration](architecture/mcp-integration.md)
3. Check [API Reference](reference/mcp-tools-api.md) for tool specifications

### For Operators
1. Follow [Remote Deployment Guide](guides/remote-deployment.md)
2. Configure [OAuth Authentication](guides/oauth-setup.md)
3. Review [Configuration Reference](reference/mcp-server-config.md)

## Project Overview

KX-Hub is a knowledge management system that:
- Ingests content from multiple sources (Kindle, Reader, articles)
- Chunks and embeds documents using AI
- Provides semantic search and clustering
- Offers AI-powered reading recommendations
- Integrates with Claude via Model Context Protocol (MCP)

**Technology Stack:**
- Google Cloud Platform (Firestore, Cloud Run, Secret Manager)
- Vertex AI (embeddings, text generation)
- TypeScript + Python hybrid architecture
- OAuth 2.1 authentication
- MCP (Model Context Protocol) for Claude integration
