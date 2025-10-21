# 3. Architectural Guidelines
- Simple & extensible, **Serverless (Google Cloud)**, **Pay-per-Use**.
- **Unified AI Platform**: Use of **Vertex AI** for all AI tasks (Embeddings, Generative Models, Vector Search).
- Configurable via repo (`/config/settings.yml`).
- Delta processing backed by explicit run manifests + pipeline state (`pipeline_items`) so only new/changed items reflow.
- Stage-level resume: each function must be idempotent, update `normalize_status`/`embedding_status`, and skip work already marked `complete`.
- Secure (Google Secret Manager, IAM Least-Privilege, private repo).
