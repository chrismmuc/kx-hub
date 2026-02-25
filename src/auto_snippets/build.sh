#!/bin/bash
# Build script for auto_snippets Cloud Function.
# Copies shared modules into build/ for deployment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
SRC_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/src"

echo "Building auto_snippets Cloud Function..."
echo "Source: $SRC_DIR"
echo "Build:  $BUILD_DIR"

# Clean and create build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Copy entry point and requirements
cp "$SCRIPT_DIR/main.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$BUILD_DIR/"

# Copy shared modules (flat structure for Cloud Functions)
cp "$SRC_DIR/ingest/reader_client.py" "$BUILD_DIR/"
cp "$SRC_DIR/ingest/readwise_writer.py" "$BUILD_DIR/"
cp "$SRC_DIR/knowledge_cards/snippet_extractor.py" "$BUILD_DIR/"
cp "$SRC_DIR/knowledge_cards/generator.py" "$BUILD_DIR/"
cp "$SRC_DIR/knowledge_cards/prompt_manager.py" "$BUILD_DIR/"
cp "$SRC_DIR/knowledge_cards/schema.py" "$BUILD_DIR/"
cp "$SRC_DIR/embed/main.py" "$BUILD_DIR/embed_main.py"  # Renamed to avoid conflict
cp "$SRC_DIR/embed/problem_matcher.py" "$BUILD_DIR/"

# Copy prompt template
mkdir -p "$BUILD_DIR/prompts"
cp "$SRC_DIR/knowledge_cards/prompts/card_generation_prompt.txt" "$BUILD_DIR/prompts/"

# Copy llm module (preserves package structure)
mkdir -p "$BUILD_DIR/llm"
cp "$SRC_DIR/llm/"*.py "$BUILD_DIR/llm/"

echo "Build complete. Contents:"
ls -la "$BUILD_DIR/"
echo ""
echo "LLM module:"
ls -la "$BUILD_DIR/llm/"
