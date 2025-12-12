#!/bin/bash
#
# Run TalkType tests across all desktop environments
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SCREENSHOTS_DIR="$PROJECT_DIR/test-screenshots"

# Create screenshots directory
mkdir -p "$SCREENSHOTS_DIR"

MODE="${1:-screenshot}"
echo "🧪 Running TalkType tests in mode: $MODE"
echo "📁 Project directory: $PROJECT_DIR"
echo "📸 Screenshots will be saved to: $SCREENSHOTS_DIR"
echo ""

# Test in GNOME
echo "🔵 Testing in GNOME environment..."
podman run --rm \
    -v "$PROJECT_DIR:/app:ro" \
    -v "$SCREENSHOTS_DIR:/screenshots:rw" \
    -e DE_NAME=gnome \
    talktype-test:gnome /usr/local/bin/test-runner.sh "$MODE"
echo ""

# Test in KDE
echo "🔷 Testing in KDE environment..."
podman run --rm \
    -v "$PROJECT_DIR:/app:ro" \
    -v "$SCREENSHOTS_DIR:/screenshots:rw" \
    -e DE_NAME=kde \
    talktype-test:kde /usr/local/bin/test-runner.sh "$MODE"
echo ""

# Test in XFCE
echo "🟦 Testing in XFCE environment..."
podman run --rm \
    -v "$PROJECT_DIR:/app:ro" \
    -v "$SCREENSHOTS_DIR:/screenshots:rw" \
    -e DE_NAME=xfce \
    talktype-test:xfce /usr/local/bin/test-runner.sh "$MODE"
echo ""

if [ "$MODE" = "screenshot" ]; then
    echo "✅ All screenshots captured!"
    echo "📸 View screenshots in: $SCREENSHOTS_DIR"
    echo ""
    echo "To generate comparison report:"
    echo "  ./generate-comparison-report.sh"
fi
