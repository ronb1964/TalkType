#!/bin/bash
# Fast Ubuntu 20.04 build - uses pre-installed dependencies
# This avoids slow poetry install inside the container

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🏗️  Building TalkType AppImage with Ubuntu 20.04 Python..."
echo "   Strategy: Copy host .venv but use Ubuntu 20.04 Python binary"
echo ""

# Ensure we have dependencies installed on host
if [[ ! -d ".venv" ]]; then
    echo "❌ Error: .venv not found. Please run: poetry install"
    exit 1
fi

# Use podman if available, otherwise docker
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
else
    CONTAINER_CMD="docker"
fi

echo "📦 Extracting Python 3.9 binaries from Ubuntu 20.04..."

# Extract Python binaries from Ubuntu 20.04
$CONTAINER_CMD run --rm \
    -v "$PROJECT_DIR:/build:Z" \
    -w /tmp \
    ubuntu:20.04 \
    bash -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq > /dev/null 2>&1
        apt-get install -y -qq python3.9 libpython3.9 > /dev/null 2>&1

        echo "   Copying Python 3.9 binary..."
        cp /usr/bin/python3.9 /build/python3.9-ubuntu20

        echo "   Copying libpython3.9..."
        LIBPYTHON=$(find /usr/lib -name "libpython3.9.so.1.0" 2>/dev/null | head -1)
        if [ -n "$LIBPYTHON" ]; then
            cp "$LIBPYTHON" /build/libpython3.9.so.1.0-ubuntu20
            echo "   Found libpython at: $LIBPYTHON"
        else
            echo "   ERROR: Could not find libpython3.9.so.1.0"
            ls -la /usr/lib/*/libpython* 2>/dev/null || true
            exit 1
        fi

        echo "   Copying Python 3.9 standard library..."
        if [ -d "/usr/lib/python3.9" ]; then
            mkdir -p /build/python3.9-stdlib-ubuntu20
            rsync -a --exclude=site-packages --exclude=__pycache__ --exclude=*.pyc \
                /usr/lib/python3.9/ /build/python3.9-stdlib-ubuntu20/
            echo "   Copied stdlib from /usr/lib/python3.9"
        else
            echo "   ERROR: Could not find Python 3.9 stdlib"
            exit 1
        fi

        echo "   ✅ Extracted Ubuntu 20.04 Python binaries and stdlib"
    '

echo "🔍 Verifying GLIBC compatibility..."
readelf -V python3.9-ubuntu20 2>/dev/null | grep "GLIBC_" | sort -u | tail -3

if readelf -V python3.9-ubuntu20 2>/dev/null | grep -q "GLIBC_ABI_DT_RELR"; then
    echo "❌ ERROR: Python has DT_RELR requirement!"
    rm -f python3.9-ubuntu20 libpython3.9.so.1.0-ubuntu20
    exit 1
else
    echo "   ✅ No DT_RELR requirement (good!)"
fi

echo "🏗️  Building AppImage with Ubuntu 20.04 Python..."
# Set environment variable to use the extracted binaries
export PYTHON_VERSION_OVERRIDE="3.9"
export USE_UBUNTU20_PYTHON="yes"
bash build-appimage.sh

# Clean up extracted binaries
rm -f python3.9-ubuntu20 libpython3.9.so.1.0-ubuntu20
rm -rf python3.9-stdlib-ubuntu20

echo ""
echo "✅ Build complete!"
ls -lh TalkType-*.AppImage 2>/dev/null | tail -1
