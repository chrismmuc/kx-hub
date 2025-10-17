# Cost Optimization & Scaling

## Strategy

The use of Vertex AI and Google Cloud Serverless components significantly simplifies the cost structure and scaling.

- **No Manual Scaling**: Vertex AI Vector Search and Cloud Functions scale automatically.
- **Pay-per-Use**: Costs are only incurred for actual usage.
- **Simplified MLOps**: No need to manage custom models or indexes.

## Estimated Monthly Costs

| Component | Service | Monthly (estimated) |
|-----------|-------|-----------|
| Embeddings | Vertex AI Embeddings API | $0.10 |
| Vector Search | Vertex AI Vector Search | $3.00 (base index) |
| Generative | Vertex AI (Gemini 2.5 Flash) | $1.50 |
| Functions/Storage | Google Cloud | $0.50 |
| **Total** | | **~$5.10** |

✅ **Goal achieved: ~$5/month. The cost is comparable, but the complexity is drastically reduced.**

---
