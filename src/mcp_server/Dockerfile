FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY src/mcp_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the consolidated MCP server (OAuth + Tools + Streamable HTTP)
COPY src/mcp_server/ ./src/mcp_server/

# Copy LLM abstraction layer (used by recommendation_filter.py)
COPY src/llm/ ./src/llm/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run the consolidated FastAPI application
CMD ["python", "-m", "uvicorn", "src.mcp_server.server:app", "--host", "0.0.0.0", "--port", "8080"]
