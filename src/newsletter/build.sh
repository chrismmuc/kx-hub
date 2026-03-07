#!/bin/bash
# Build script for newsletter Cloud Function.
# Copies shared LLM modules into build/ for deployment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
SRC_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/src"

echo "Building newsletter Cloud Function..."
echo "Source: $SRC_DIR"
echo "Build:  $BUILD_DIR"

# Clean and create build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
mkdir -p "$BUILD_DIR/llm"

# Copy newsletter module files (flat)
cp "$SCRIPT_DIR/main.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/curation_agent.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/generator.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/models.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$BUILD_DIR/"

# Copy shared modules from summary
cp "$SRC_DIR/summary/cover_image.py" "$BUILD_DIR/"
cp "$SRC_DIR/summary/delivery.py" "$BUILD_DIR/"
cp "$SRC_DIR/summary/data_pipeline.py" "$BUILD_DIR/"

# Copy LLM abstraction layer
cp "$SRC_DIR/llm/__init__.py" "$BUILD_DIR/llm/"
cp "$SRC_DIR/llm/base.py" "$BUILD_DIR/llm/"
cp "$SRC_DIR/llm/config.py" "$BUILD_DIR/llm/"
cp "$SRC_DIR/llm/gemini.py" "$BUILD_DIR/llm/"
cp "$SRC_DIR/llm/claude.py" "$BUILD_DIR/llm/"

echo "Build complete. Contents:"
find "$BUILD_DIR" -type f | sort
