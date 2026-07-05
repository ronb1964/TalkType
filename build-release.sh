#!/bin/bash
# TalkType Release Build Script
# Builds AppImage in Ubuntu 22.04 container for maximum compatibility
# This is the ONLY build script you need for releases

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Building TalkType AppImage (Release)"
echo "========================================"
echo ""

# Version consistency check — the AppImage filename comes from pyproject.toml
# while the running app reports src/talktype/__init__.py's __version__.
# Drift between them makes the update checker offer the app an "update" to
# itself forever (happened once before). Fail the build instead.
PYPROJECT_VERSION=$(grep -E "^version = " "$PROJECT_DIR/pyproject.toml" | sed 's/version = "\(.*\)"/\1/')
INIT_VERSION=$(grep -E "^__version__ = " "$PROJECT_DIR/src/talktype/__init__.py" | sed 's/__version__ = "\(.*\)"/\1/')
if [ -z "$PYPROJECT_VERSION" ] || [ -z "$INIT_VERSION" ]; then
    echo "❌ Could not read version from pyproject.toml ('$PYPROJECT_VERSION') or"
    echo "   src/talktype/__init__.py ('$INIT_VERSION'). Check the 'version =' lines."
    exit 1
fi
if [ "$PYPROJECT_VERSION" != "$INIT_VERSION" ]; then
    echo "❌ VERSION MISMATCH: pyproject.toml says $PYPROJECT_VERSION but"
    echo "   src/talktype/__init__.py says $INIT_VERSION"
    echo "   Bump BOTH files to the same version, then rebuild."
    exit 1
fi
echo "✅ Version check: $PYPROJECT_VERSION (pyproject.toml and __init__.py match)"
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

# Generate release checksums. The update checker downloads SHA256SUMS.txt
# from the GitHub release and verifies the AppImage against it before
# installing — include this file in every release (gh release create ...).
APPIMAGE_FILE="TalkType-v${PYPROJECT_VERSION}-x86_64.AppImage"
cd "$PROJECT_DIR"
# Remove any stale checksums from a previous release so a build failure
# can't leave a wrong SHA256SUMS.txt lying around to be published.
rm -f SHA256SUMS.txt
if [ -f "$PROJECT_DIR/$APPIMAGE_FILE" ]; then
    sha256sum "$APPIMAGE_FILE" > SHA256SUMS.txt
    # Include the extension zip when it has been packaged already
    # (package-extension.sh also refreshes this entry when run afterwards)
    if [ -f "talktype-gnome-extension.zip" ]; then
        sha256sum "talktype-gnome-extension.zip" >> SHA256SUMS.txt
    fi
    echo "🔐 Checksums written to SHA256SUMS.txt:"
    cat SHA256SUMS.txt
    echo ""
else
    echo "⚠️  Expected AppImage '$APPIMAGE_FILE' not found — SHA256SUMS.txt NOT generated."
    echo "   The build likely failed; do not publish a release without it."
    echo ""
fi

echo "🚀 To test: ./TalkType-v${PYPROJECT_VERSION}-x86_64.AppImage"
