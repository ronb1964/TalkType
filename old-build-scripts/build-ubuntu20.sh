#!/bin/bash
# Build TalkType AppImage using Ubuntu 20.04 for maximum compatibility
# Ubuntu 20.04 has GLIBC 2.31 without DT_RELR

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🏗️  Building TalkType AppImage in Ubuntu 20.04 for maximum compatibility..."
echo "   Target: GLIBC 2.31 (Ubuntu 20.04+)"
echo ""

# Use podman if available, otherwise docker
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
else
    CONTAINER_CMD="docker"
fi

# Run build in Ubuntu 20.04 container
$CONTAINER_CMD run --rm \
    -v "$PROJECT_DIR:/build:Z" \
    -w /build \
    -e HOME=/tmp \
    ubuntu:20.04 \
    bash -c '
        set -e

        echo "📍 Inside Ubuntu 20.04 container (GLIBC 2.31)"
        echo "🔧 Installing build dependencies..."

        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq \
            python3.9 \
            python3.9-venv \
            python3-pip \
            git \
            cmake \
            build-essential \
            wget \
            rsync \
            libgirepository1.0-dev \
            pkg-config \
            file \
            patchelf \
            > /dev/null 2>&1

        echo "🐍 Python version: $(python3.9 --version)"
        echo "🔍 Verifying GLIBC compatibility..."

        # Check Python GLIBC requirements
        echo "   Python GLIBC requirements:"
        readelf -V /usr/bin/python3.9 2>/dev/null | grep "GLIBC_" | sort -u | tail -5 || true

        # Verify no DT_RELR
        if readelf -V /usr/bin/python3.9 2>/dev/null | grep -q "GLIBC_ABI_DT_RELR"; then
            echo "❌ ERROR: Python has DT_RELR requirement!"
            exit 1
        else
            echo "   ✅ No DT_RELR requirement (good!)"
        fi

        echo "📚 Setting up Python environment..."

        # Create venv with COPIES not symlinks
        python3.9 -m venv --copies .venv
        .venv/bin/pip install -q --upgrade pip
        .venv/bin/pip install -q poetry

        # Install Python dependencies
        echo "📦 Installing dependencies..."
        .venv/bin/poetry install --only main -q

        echo "🏗️  Building AppImage..."
        # Override Python version for Ubuntu 20.04
        export PYTHON_VERSION_OVERRIDE="3.9"
        bash build-appimage.sh

        echo ""
        echo "✅ Build complete with Ubuntu 20.04 binaries!"
        echo "   Max GLIBC requirement should be 2.31 or lower"
    '

echo ""
echo "✅ Build complete!"
ls -lh TalkType-*.AppImage 2>/dev/null || echo "No AppImage found"
