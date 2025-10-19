#!/bin/bash
# TalkType Release Build Script
# Builds AppImage in Ubuntu 22.04 container for maximum compatibility
# This is the ONLY build script you need for releases

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Building TalkType AppImage (Release)"
echo "========================================"
echo ""

# Use podman if available, otherwise docker
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
else
    CONTAINER_CMD="docker"
fi

echo "📦 Building in Ubuntu 22.04 container..."
echo ""

# Create pip cache directory if it doesn't exist
mkdir -p "$HOME/.cache/pip-talktype-build"

echo "💾 Using pip cache: $HOME/.cache/pip-talktype-build"
echo ""

# Run the container build script
$CONTAINER_CMD run --rm \
    -v "$PROJECT_DIR:/build:Z" \
    -v "$HOME/.cache/pip-talktype-build:/root/.cache/pip:Z" \
    -w /build \
    -e HOME=/tmp \
    -e BUILD_USER=$(id -u) \
    -e BUILD_GROUP=$(id -g) \
    ubuntu:22.04 \
    bash /build/container-build.sh

echo ""
echo "📦 AppImage Details:"
ls -lh TalkType-*.AppImage 2>/dev/null || echo "❌ No AppImage found - build failed"
echo ""
echo "🚀 To test: ./TalkType-v*-x86_64.AppImage"
