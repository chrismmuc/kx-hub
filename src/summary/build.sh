#!/bin/bash
# Build script for summary Cloud Function.
# Copies shared LLM modules into build/ for deployment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
SRC_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/src"

echo "Building summary Cloud Function..."
echo "Source: $SRC_DIR"
echo "Build:  $BUILD_DIR"

# Clean and create build directory
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
mkdir -p "$BUILD_DIR/llm"

# Copy summary module files (flat)
cp "$SCRIPT_DIR/main.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/data_pipeline.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/generator.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/delivery.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/cover_image.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$BUILD_DIR/"

# Copy LLM abstraction layer (as package — generator imports from llm)
cp "$SRC_DIR/llm/__init__.py" "$BUILD_DIR/llm/"
cp "$SRC_DIR/llm/base.py" "$BUILD_DIR/llm/"
cp "$SRC_DIR/llm/config.py" "$BUILD_DIR/llm/"
cp "$SRC_DIR/llm/gemini.py" "$BUILD_DIR/llm/"
cp "$SRC_DIR/llm/claude.py" "$BUILD_DIR/llm/"

echo "Build complete. Contents:"
find "$BUILD_DIR" -type f | sort
