#!/bin/bash
# Simple Ubuntu 22.04 build using Docker/Podman
# This script runs the build inside Ubuntu 22.04 to ensure glibc 2.35 compatibility

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🏗️  Building TalkType AppImage in Ubuntu 22.04..."
echo ""

# Use podman if available, otherwise docker
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
else
    CONTAINER_CMD="docker"
fi

# Run build in Ubuntu 22.04 container with minimal overhead
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
        echo "🔧 Installing minimal build dependencies..."

        # Install only what we absolutely need (as root)
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq \
            python3.10 \
            python3.10-venv \
            python3-pip \
            git \
            cmake \
            build-essential \
            wget \
            rsync \
            libgirepository1.0-dev \
            pkg-config \
            > /dev/null 2>&1

        echo "🐍 Python version: $(python3 --version)"
        echo "📚 Installing dependencies..."

        # Remove existing venv - it is from host Python 3.13
        rm -rf .venv

        # Create venv with COPIES not symlinks
        python3 -m venv --copies .venv
        .venv/bin/pip install -q --upgrade pip
        .venv/bin/pip install -q poetry

        # Install Python dependencies
        .venv/bin/poetry install --only main -q

        echo "🔍 Verifying glibc compatibility..."
        readelf -V /usr/bin/python3 2>/dev/null | grep "GLIBC_" | sort -u | tail -3

        echo "🏗️  Running build script..."
        bash build-appimage-cpu.sh

        # Fix ownership of built files
        if [ -n "$BUILD_USER" ]; then
            chown -R $BUILD_USER:$BUILD_GROUP /build/.venv /build/AppDir /build/TalkType-*.AppImage 2>/dev/null || true
        fi
    '

echo ""
echo "✅ Build complete!"
ls -lh TalkType-*.AppImage 2>/dev/null || echo "No AppImage found - build may have failed"
