#!/bin/bash
# TalkType Build Script using appimage-builder
# This uses the appimage-builder tool which handles dependency resolution automatically

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Building TalkType with appimage-builder"
echo "==========================================="
echo ""

# Use podman if available, otherwise docker
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
else
    CONTAINER_CMD="docker"
fi

echo "📦 Building in Ubuntu 22.04 container using appimage-builder..."
echo ""

# Run build inside Ubuntu 22.04 container
$CONTAINER_CMD run --rm \
    -v "$PROJECT_DIR:/build:Z" \
    -w /build \
    -e HOME=/tmp \
    -e BUILD_USER=$(id -u) \
    -e BUILD_GROUP=$(id -g) \
    ubuntu:22.04 \
    bash -c '
        set -e

        echo "📍 Inside Ubuntu 22.04 container"
        echo "🔧 Installing appimage-builder and dependencies..."

        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq \
            python3 \
            python3-pip \
            python3-venv \
            wget \
            git \
            > /dev/null 2>&1

        # Install appimage-builder and poetry
        pip3 install -q appimage-builder poetry

        # Verify installation
        appimage-builder --version
        poetry --version

        echo "✅ appimage-builder and poetry installed"
        echo ""

        # Get version from pyproject.toml
        VERSION=$(grep -E "^version" /build/pyproject.toml | sed "s/version = \"\(.*\)\"/\1/")
        echo "✅ TalkType version: $VERSION"
        echo ""

        # Run appimage-builder
        echo "🏗️  Running appimage-builder..."
        cd /build
        appimage-builder --recipe AppImageBuilder.yml

        # Fix ownership of output files
        if [ -n "$BUILD_USER" ]; then
            chown $BUILD_USER:$BUILD_GROUP /build/*.AppImage* 2>/dev/null || true
        fi

        echo ""
        echo "✅ Build complete!"
    '

echo ""
echo "📦 AppImage Details:"
ls -lh TalkType-*.AppImage 2>/dev/null || echo "❌ No AppImage found - build failed"
echo ""
echo "🚀 To test: ./TalkType-*-x86_64.AppImage"
