#!/bin/bash
#
# Build all desktop environment test containers
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🐳 Building TalkType test containers..."
echo ""

# Build GNOME container
echo "📦 Building GNOME container..."
podman build -f Dockerfile.gnome -t talktype-test:gnome .
echo "✅ GNOME container built"
echo ""

# Build KDE container
echo "📦 Building KDE container..."
podman build -f Dockerfile.kde -t talktype-test:kde .
echo "✅ KDE container built"
echo ""

# Build XFCE container
echo "📦 Building XFCE container..."
podman build -f Dockerfile.xfce -t talktype-test:xfce .
echo "✅ XFCE container built"
echo ""

echo "🎉 All containers built successfully!"
echo ""
echo "To test:"
echo "  ./run-tests.sh screenshot  # Take screenshots in all environments"
echo "  ./run-tests.sh test       # Run automated tests"
