# kx-llm

LLM abstraction layer for kx-hub - unified interface for Gemini and Claude via Vertex AI.

## Installation

```bash
pip install kx-llm --index-url https://europe-west4-python.pkg.dev/kx-hub/kx-packages/simple/
```

## Usage

```python
from kx_llm import get_client, GenerationConfig

# Simple usage with default model
client = get_client()
response = client.generate("Summarize this text...")
print(response.text)

# JSON generation
data = client.generate_json("Return JSON with keys: summary, tags")

# Custom config (e.g., enable thinking for complex reasoning)
config = GenerationConfig(
    temperature=0.3,
    enable_thinking=True,  # Enables Gemini 2.5+ thinking mode
)
response = client.generate("Complex reasoning task...", config=config)
```

## Environment Variables

- `LLM_MODEL`: Default model (e.g., "gemini-2.5-flash", "claude-haiku")
- `GCP_PROJECT`: GCP project ID
- `GCP_REGION`: GCP region for Gemini
- `CLAUDE_REGION`: GCP region for Claude (default: europe-west1)
