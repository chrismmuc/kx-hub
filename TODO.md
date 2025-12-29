# TODO List

## Recent Pull Requests

### [#9 - refactor: Replace sys.path.insert with proper Python package structure](https://github.com/chrismmuc/kx-hub/pull/9)
- Add pyproject.toml for proper package installation
- Update all imports to use absolute paths (src.llm, src.clustering, etc.)
- Use relative imports within mcp_server package (from . import)
- Remove all sys.path.insert hacks from src/, tests/, and scripts/
- Update test @patch decorators to use src.* paths
  
  This makes the codebase more robust across different deployment environments (Cloud Functions, Docker, local testing) by following Python packaging best practices.

### [#8 - chore: Change deployment trigger to manual only (workflow_dispatch)](https://github.com/chrismmuc/kx-hub/pull/8)
- Deployment trigger changed to manual only.

### [#7 - feat: Add LLM abstraction layer for multi-provider support (Gemini + Claude)](https://github.com/chrismmuc/kx-hub/pull/7)
Implements a unified LLM interface to enable easy switching between Gemini and Claude models via environment variables. This allows for A/B testing and quick model changes without code modifications.

New components:
- src/llm/base.py: Abstract base class with GenerationConfig and LLMResponse
- src/llm/gemini.py: Gemini implementation via Vertex AI SDK
- src/llm/claude.py: Claude implementation via Anthropic Vertex AI SDK
- src/llm/config.py: Model registry with pricing and regional info
- src/llm/__init__.py: Factory with get_client() for easy access

Refactored modules:
- knowledge_cards/generator.py: Uses LLM abstraction
- clustering/cluster_metadata.py: Uses LLM abstraction
- mcp_server/recommendation_filter.py: Uses LLM abstraction

Configuration via environment variables:
- LLM_MODEL: Model name (e.g., "gemini-2.5-flash", "claude-haiku")
- LLM_PROVIDER: Provider preference ("gemini" or "claude")
- CLAUDE_REGION: Region for Claude (default: us-east5)

Added anthropic[vertex] dependency to requirements.txt files.

### [#6 - fix: Use json.dumps instead of str() for MCP tool results](https://github.com/chrismmuc/kx-hub/pull/6)
- Use json.dumps for consistent serialization
- Fixes "Response content longer than Content-Length" error on list_clusters

### [#5 - Epic 4: MCP Tool Consolidation (25→9 tools, 64% reduction)](https://github.com/chrismmuc/kx-hub/pull/5)
#### Summary of Changes
Completed Epic 4: Reduced MCP tool count from 25 to 9 through consolidation to improve AI tool selection, reducing token overhead by ~60%. Implementation includes: 
- Unified search tools
- Enhanced MCP functions for clusters, metadata, and testing coverage.
- Backward compatibility preserved 100%.

#### Key Metrics
- ✅ Tool reduction: from 25 tools → 9 tools.
- ✅ Comprehensive test cases added.

For additional details, please refer to PR descriptions linked above.