# Chunking Performance Monitoring

## Key Metrics to Track

### 1. Chunking Distribution (Normalize Stage)
**Purpose**: Ensure chunks are within target size ranges

**Metrics**:
- Average chunks per document: Target ~5 (actual: monitor via logs)
- Chunk size distribution:
  - Min: Should be > 100 tokens (except last chunk)
  - Target: 400-600 tokens (centered on 512)
  - Max: Should never exceed 1024 tokens
- Overlap consistency: Should average ~75 tokens between chunks

**Monitoring**:
```python
# Log in normalize stage after chunking
logger.info(f"Split {user_book_id} into {len(chunks)} chunks")
for i, chunk in enumerate(chunks):
    logger.info(f"Chunk {i}: {chunk.token_count} tokens, "
                f"overlap_start={chunk.overlap_start}, "
                f"overlap_end={chunk.overlap_end}")
```

**Query in GCP Logs Explorer**:
```
resource.type="cloud_function"
resource.labels.function_name="normalize"
"Split" AND "chunks"
```

### 2. Embedding Cost Tracking (Embed Stage)
**Purpose**: Monitor embedding API usage and costs

**Metrics**:
- Total chunks embedded per run
- Embedding API call count (should equal chunk count)
- Token counts sent to Vertex AI (for cost validation)

**Cost Formula**:
- Vertex AI gemini-embedding-001: $0.00001 per 1K tokens
- Expected: ~1,355 chunks × 512 tokens avg = ~693K tokens/month
- Monthly cost: ~$0.007 × 75 = ~$0.50/month

**Monitoring**:
```python
# Log in embed stage
logger.info(f"Storing embedding vector with {len(embedding_vector)} dimensions for {chunk_id}")
logger.info(f"Chunk {chunk_id}: {token_count} tokens processed")
```

### 3. Retrieval Performance (Query Stage)
**Purpose**: Validate that chunking improves search quality

**Metrics**:
- Query latency: Target <100ms (down from ~200ms with GCS fetch)
- Content completeness: Verify `content` field is populated
- Chunk context: Ensure parent metadata is available

**Before/After Comparison**:
| Metric | Before (Document-level) | After (Chunk-level) |
|--------|------------------------|---------------------|
| Retrieval granularity | Full document | Passage-level |
| Average result size | ~2000 tokens | ~512 tokens |
| Query latency | ~200ms (GCS fetch) | ~100ms (direct from Firestore) |
| Embedding cost | ~$0.10/month | ~$0.50/month |
| Storage cost | ~$0.10/month | ~$0.20/month |

### 4. Storage Impact
**Purpose**: Monitor Firestore storage growth

**Metrics**:
- kb_items collection size: 271 books → ~1,355 chunks
- Average document size: ~2KB per chunk (metadata + content + embedding)
- Total storage: ~2.7 MB (negligible cost)

**GCP Console Check**:
- Navigate to Firestore → kb_items
- Check document count (should be ~5× book count)
- Monitor storage metrics in Firestore dashboard

## Cost Breakdown (Monthly)

### Current Implementation (with Chunking)
```
Vertex AI Embeddings:
  - 1,355 chunks × 512 tokens avg = 693K tokens
  - 693K tokens × $0.00001/1K = $0.007 per day
  - $0.007 × 75 days (avg books/month) = ~$0.50/month

Firestore Storage:
  - 1,355 chunks × 2KB = 2.7 MB
  - 2.7 MB × $0.18/GB = ~$0.0005/month (negligible)

Firestore Vector Queries:
  - Estimated ~100 queries/month
  - ~$0.10/month

Cloud Functions (Normalize + Embed):
  - Normalize: ~271 executions × 2s avg × $0.0000004/100ms = ~$0.02
  - Embed: ~1,355 executions × 1s avg × $0.0000004/100ms = ~$0.05
  - Total: ~$0.50/month (includes ingest)

Cloud Storage:
  - 1,355 chunk markdown files × 1KB avg = 1.4 MB
  - Raw JSON: ~10 MB
  - Total: ~$0.10/month

TOTAL: ~$1.40/month
```

### Cost Optimization Opportunities
1. **Reduce chunk overlap**: 75 → 50 tokens saves ~15% embedding cost (~$0.08/month)
2. **Increase target size**: 512 → 768 tokens reduces chunk count by ~30% (~$0.15/month)
3. **Trade-off**: Both reduce search quality and context preservation

**Recommendation**: Current configuration is optimal for quality/cost balance.

## Alerting Thresholds

### Critical Alerts
- **Chunk count explosion**: If avg chunks/book > 10, investigate
  - Possible cause: Large documents not properly bounded
  - Action: Review chunking algorithm for max_tokens enforcement

- **Embedding failures**: If embedding_status='failed' > 5% of chunks
  - Possible cause: Rate limiting, API errors
  - Action: Check retry logic, increase backoff delays

- **Token count violations**: If any chunk > 1024 tokens
  - Possible cause: Bug in chunking algorithm
  - Action: Emergency fix required (hard limit breach)

### Warning Alerts
- **Small chunks**: If >20% of chunks < 200 tokens
  - Possible cause: Documents with short highlights
  - Action: Review min_tokens configuration

- **Cost overrun**: If monthly embedding cost > $1.00
  - Possible cause: More documents than expected
  - Action: Review ingest frequency, document count

## Dashboard Queries

### Cloud Logging Queries

**1. Chunking Statistics**
```
resource.type="cloud_function"
resource.labels.function_name="normalize"
jsonPayload.message=~"Split .* into .* chunks"
```

**2. Embedding Processing**
```
resource.type="cloud_function"
resource.labels.function_name="embed"
jsonPayload.message=~"Storing embedding vector"
```

**3. Failed Chunks**
```
resource.type="cloud_function"
severity="ERROR"
jsonPayload.embedding_status="failed"
```

### BigQuery Export (Optional)
For detailed cost analysis, export Firestore and Cloud Function logs to BigQuery:

```sql
-- Average chunks per document
SELECT
  DATE(timestamp) as date,
  AVG(CAST(REGEXP_EXTRACT(textPayload, r'into (\d+) chunks') AS INT64)) as avg_chunks_per_doc
FROM `project.logs.cloudaudit_googleapis_com_activity`
WHERE textPayload LIKE '%Split%chunks%'
GROUP BY date
ORDER BY date DESC;

-- Daily embedding costs
SELECT
  DATE(timestamp) as date,
  COUNT(*) as chunks_embedded,
  COUNT(*) * 512 * 0.00001 / 1000 as estimated_cost_usd
FROM `project.logs.cloudaudit_googleapis_com_activity`
WHERE textPayload LIKE '%Storing embedding vector%'
GROUP BY date
ORDER BY date DESC;
```

## Success Criteria Validation

From Story 1.6, validate these criteria weekly:

- ✅ **AC1**: Chunks are 400-600 tokens (monitor via logs)
- ✅ **AC2**: Semantic boundaries respected (test with highlights)
- ✅ **AC3**: Overlaps present (check overlap_start/end fields)
- ✅ **AC4**: Parent metadata preserved (verify frontmatter)
- ✅ **AC5**: Retrieval latency <100ms (query performance logs)
- ✅ **AC6**: Monthly cost <$2 (sum of all components)
- ✅ **AC7**: 63 tests passing (CI/CD validation)

## Performance Baselines

Established from integration testing (large-book.json, 20 highlights):

- **Document**: 20 highlights → 6 chunks
- **Average chunk size**: ~450 tokens
- **Overlap**: 75 tokens between adjacent chunks
- **Processing time**: ~50ms per chunk (normalize + embed)
- **Storage per chunk**: ~2KB (metadata + content + embedding)

Monitor for degradation from these baselines.
