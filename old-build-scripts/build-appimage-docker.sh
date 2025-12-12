#!/bin/bash
# Build TalkType AppImage in Ubuntu 22.04 Docker container
# This ensures glibc 2.35 compatibility for AppImageHub

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="talktype-builder-ubuntu22.04"

echo "🐳 Building TalkType AppImage in Ubuntu 22.04 Docker container..."
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first:"
    echo "   sudo dnf install docker"
    echo "   sudo systemctl start docker"
    echo "   sudo usermod -aG docker $USER"
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker daemon is not running. Please start it:"
    echo "   sudo systemctl start docker"
    exit 1
fi

# Build Docker image if it doesn't exist
if ! docker image inspect "$IMAGE_NAME" &> /dev/null; then
    echo "📦 Building Docker image (first time only, may take a few minutes)..."
    docker build -f "$PROJECT_DIR/Dockerfile.build" -t "$IMAGE_NAME" "$PROJECT_DIR"
    echo "✅ Docker image built successfully"
    echo ""
fi

# Run the build inside Docker container
echo "🔨 Building AppImage inside Ubuntu 22.04 container..."
docker run --rm \
    -v "$PROJECT_DIR:/tmp/build" \
    -w /tmp/build \
    -u $(id -u):$(id -g) \
    -e HOME=/tmp \
    -e APPIMAGE_EXTRACT_AND_RUN=1 \
    "$IMAGE_NAME" \
    bash -c "
        set -e
        echo '📍 Inside Ubuntu 22.04 container'
        echo '🐍 Python version:'
        python3 --version
        echo ''
        echo '📚 Installing Poetry and creating venv...'
        python3 -m pip install --user poetry 2>&1 | grep -v WARNING || true
        export PATH=\"\$HOME/.local/bin:\$PATH\"
        python3 -m venv --copies .venv
        .venv/bin/pip install --upgrade pip 2>&1 | tail -3
        .venv/bin/pip install poetry
        .venv/bin/poetry install --only main
        echo ''
        echo '🔍 Verifying Python binary glibc compatibility...'
        readelf -V /usr/bin/python3 2>/dev/null | grep 'GLIBC_' | sort -u | tail -3
        echo ''
        echo '🏗️  Running build script...'
        bash build-appimage.sh
    "

echo ""
echo "✅ AppImage built successfully in Ubuntu 22.04 environment!"
echo ""
echo "📦 File: TalkType-v0.3.7-x86_64.AppImage"
echo "🎯 Compatible with: Ubuntu 22.04+ (glibc 2.35+)"
echo ""
echo "🧪 To test: ./fresh-test-env.sh"
