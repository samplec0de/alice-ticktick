#!/usr/bin/env bash
# Package alice-ticktick for Yandex Cloud Functions deployment.
# Output: deploy.zip in project root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/.build"

rm -rf "$BUILD_DIR" "$PROJECT_DIR/deploy.zip"
mkdir -p "$BUILD_DIR"

# Install production dependencies into build dir
pip install --target "$BUILD_DIR" --quiet \
    aliceio aiohttp httpx pydantic pydantic-settings rapidfuzz

# Copy application code
cp -r "$PROJECT_DIR/alice_ticktick" "$BUILD_DIR/"

# Create zip
cd "$BUILD_DIR"
zip -r "$PROJECT_DIR/deploy.zip" . -q

echo "Created deploy.zip ($(du -h "$PROJECT_DIR/deploy.zip" | cut -f1))"
