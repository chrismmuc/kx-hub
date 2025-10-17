# Brainstorming Session

## Warm-up: What If Scenarios

- Prompt: What if Readwise/Reader volume is 10× for a week?
  - Response: Brute-force cosine similarity likely becomes bottleneck; other serverless components should remain stable.
- Prompt: What if OpenAI throttles embeddings/summaries during spike?
  - Response: Need retries/chunking; throughput slows but pipeline should complete eventually.
- Prompt: What if GitHub export fails repeatedly?
  - Response: Ensure backups stay in AWS (S3/DynamoDB) so data isn’t lost; GitHub acts as downstream sync.

## First Principles Thinking

- Core daily job: surface weekly additions and highlight novel connections.
- Essential inputs: Readwise/Reader delta payloads normalized to Markdown with frontmatter + embeddings.
- Mandatory outputs: weekly delta list, curated strongest connections, stretch goal for counterintuitive insights.

## Morphological Analysis

### Dimension 1 – Retrieve & Preprocess
- Option A: Direct API delta pull → immediate Markdown normalization.
- Option B: API pull → EventBridge/SQS buffer → Markdown (selected).
- Option C: Scheduled backfill job to re-request missed days.

### Dimension 2 – Generate Summaries
- Option A: Single-pass TL;DR prompt.
- Option B: Multi-pass bullets → TL;DR.
- Option C: Source-aware prompts per note type (selected).

### Dimension 3 – Detect Similarities
- Option A: Brute-force cosine.
- Option B: Nightly FAISS ANN.
- Option C: Hybrid cosine + tag/author heuristics (selected).

### Dimension 4 – Surface Creative Connections
- Option A: Top-N edges by score.
- Option B: Contrastive pairs low tag overlap/high cosine (selected).
- Option C: LLM-generated analogies.
- Option D: Cross-cluster novelty alerts.

### Selected Combination (Focus Track)
- Retrieve & Preprocess: EventBridge/SQS buffering before Markdown normalization.
- Summaries: Source-aware prompts tailored to Reader vs. Readwise content.
- Similarity Detection: Hybrid scoring blending cosine embeddings with tag/author heuristics.
- Creative Connections: Contrastive pairing of low-overlap yet high-similarity notes.

## Executive Summary
- Topic: Focused ideation on the Personal KI Knowledge Base pipeline to ensure reliable weekly insights and creative connections.
- Techniques used: What If Scenarios, First Principles Thinking, Morphological Analysis (~30 min total).
- Ideas captured: Warm-up resilience insights, clarified essentials, selected reliability-focused configuration.
- Key themes: Resilience to ingestion spikes, minimal viable transformations, hybrid similarity scoring, contrastive link surfacing.

## Technique Sections

### Technique: What If Scenarios (≈10 min)
- Ideas:
  - Volume spike mainly threatens brute-force similarity; serverless pieces stay stable.
  - OpenAI throttling needs retries/chunking; throughput slows but completes.
  - GitHub failures shouldn’t block knowledge—keep canonical state in AWS.
- Insights: Resilience hinges on similarity scaling and external service throttling.
- Reflections: Stress-testing assumptions up front sharpened focus.

### Technique: First Principles Thinking (≈10 min)
- Ideas:
  - Core job: weekly additions + compelling connections.
  - Inputs: normalized Markdown + embeddings.
  - Outputs: delta list, curated connections, optional counterintuitive links.
- Insights: Embedding-first flow anchors summaries and connection detection.
- Reflections: Clarifying must-haves avoids drift.

### Technique: Morphological Analysis (≈10 min)
- Ideas:
  - Mapped four dimensions with option sets.
  - Selected reliable combo emphasizing buffering, context-aware prompts, hybrid scoring, contrastive pairing.
- Insights: Structured option matrix clarified trade-offs quickly.
- Reflections: Option grids enable confident focused decisions.

## Idea Categorization
- Immediate Opportunities:
  - Implement EventBridge/SQS buffering.
  - Design source-aware summary prompts.
  - Prototype hybrid similarity scoring.
  - Configure contrastive pairing logic.
- Future Innovations:
  - Automate cluster-level novelty detection.
  - Add resilience analytics for spike monitoring.
- Moonshots:
  - Generate LLM analogies for narrative storytelling.
- Insights & Learnings:
  - Similarity scaling is primary risk under spikes.
  - Embedding-first supports both summaries and creative connections.

## Action Planning
1. Buffer ingestion via EventBridge/SQS and update Step Function consumer.
2. Craft tailored summary prompts leveraging metadata.
3. Implement hybrid similarity scorer and evaluate on sample notes.
4. Build weekly contrastive pairing report.
- Next Steps: Define acceptance criteria, integrate via CDK.
- Resources: Prompt tuning time, historical notes, monitoring setup.
- Timeline: Prioritize buffering for reliability, then scoring/links.

## Reflection & Follow-up
- What worked: Progressive techniques maintained focus and uncovered hidden risks.
- Further exploration: Evaluate FAISS upgrade when volumes grow.
- Recommended follow-up: Revisit after hybrid scoring prototype to tune thresholds.
- Open questions: Metric for measuring cross-cluster “novelty”.
