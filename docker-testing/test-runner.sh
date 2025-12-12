#!/bin/bash
#
# Test Runner Script for Container Environments
# Starts virtual display, launches TalkType, takes screenshots
#

set -e

echo "🚀 Starting TalkType test environment..."

# Start D-Bus
mkdir -p /run/dbus
dbus-daemon --system --fork || true
dbus-daemon --session --fork --address=unix:path=/tmp/dbus.sock || true
export DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/dbus.sock

# Start Xvfb virtual display
echo "📺 Starting virtual display..."
Xvfb :99 -screen 0 1920x1080x24 &
XVFB_PID=$!
sleep 2

# Wait for X server to be ready
for i in {1..10}; do
    if xdpyinfo -display :99 >/dev/null 2>&1; then
        echo "✅ X server ready"
        break
    fi
    echo "⏳ Waiting for X server... ($i/10)"
    sleep 1
done

# Set up environment variables for TalkType
export PYTHONPATH=/app/src
export HOME=/tmp/home
mkdir -p $HOME

# Check if we're just running tests or need to launch GUI
if [ "$1" = "screenshot" ]; then
    echo "📸 Taking screenshot mode..."

    # Launch TalkType preferences window
    cd /app
    python3 -m talktype.prefs &
    APP_PID=$!

    # Wait for window to appear
    sleep 3

    # Take screenshot
    SCREENSHOT_PATH="/screenshots/talktype-${DE_NAME:-unknown}-$(date +%Y%m%d_%H%M%S).png"
    gnome-screenshot -f "$SCREENSHOT_PATH" 2>/dev/null || \
        spectacle -b -o "$SCREENSHOT_PATH" 2>/dev/null || \
        xfce4-screenshooter -w -s "$SCREENSHOT_PATH" 2>/dev/null || \
        import -window root "$SCREENSHOT_PATH"

    echo "✅ Screenshot saved: $SCREENSHOT_PATH"

    # Clean up
    kill $APP_PID 2>/dev/null || true

elif [ "$1" = "test" ]; then
    echo "🧪 Running automated tests..."
    cd /app
    python3 -m pytest tests/ || echo "⚠️  Some tests failed"

else
    echo "📋 No command specified. Available commands:"
    echo "  screenshot - Launch GUI and take screenshot"
    echo "  test      - Run automated tests"
    echo ""
    echo "Example: docker run ... screenshot"
fi

# Cleanup
kill $XVFB_PID 2>/dev/null || true

echo "✅ Test environment completed"
