# Cost Optimization & Scaling

## Strategy

The use of Vertex AI and Google Cloud Serverless components significantly simplifies the cost structure and scaling.

- **No Manual Scaling**: Firestore and Cloud Functions scale automatically.
- **Pay-per-Use**: Costs are only incurred for actual usage.
- **Simplified MLOps**: No need to manage custom models or indexes.
- **99% Cost Reduction**: Migrated from Vertex AI Vector Search ($100+/month) to Firestore native vectors ($0.10/month).

## Estimated Monthly Costs

| Component | Service | Monthly (estimated) |
|-----------|-------|-----------|
| Embeddings | Vertex AI Embeddings API (gemini-embedding-001) | $0.10 |
| Vector Search | Firestore native vectors | $0.10 |
| Generative | Vertex AI (Gemini 2.5 Flash) - Future | $0.00 |
| Functions/Storage | Google Cloud | $0.50 |
| Firestore (metadata) | Firestore reads/writes | $0.20 |
| **Total** | | **~$0.90** |

### Previous Costs (Before Migration)
| Component | Service | Monthly (estimated) |
|-----------|-------|-----------|
| Embeddings | Vertex AI Embeddings API | $0.10 |
| Vector Search | Vertex AI Vector Search | $100.00 (index + hosting) |
| Generative | Vertex AI (Gemini 2.5 Flash) | $1.50 |
| Functions/Storage | Google Cloud | $0.50 |
| **Total** | | **~$102.10** |

✅ **99% cost reduction achieved**: From ~$102/month → ~$0.90/month. Complexity drastically reduced while maintaining all functionality.

---
