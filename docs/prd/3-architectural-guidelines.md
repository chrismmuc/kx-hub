# 3. Architectural Guidelines
- Simple & extensible, **Serverless (Google Cloud)**, **Pay-per-Use**.
- **Unified AI Platform**: Use of **Vertex AI** for all AI tasks (Embeddings, Generative Models, Vector Search).
- Configurable via repo (`/config/settings.yml`).
- Delta processing (only new/changed items).
- Secure (Google Secret Manager, IAM Least-Privilege, private repo).
