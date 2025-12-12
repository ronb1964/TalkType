#!/usr/bin/env bash
#
# GTK Inspector Launcher for TalkType Development
# Launches TalkType with GTK Inspector enabled for UI debugging
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔍 Launching TalkType with GTK Inspector enabled..."
echo ""
echo "GTK Inspector Controls:"
echo "  • Interactive: Ctrl+Shift+I or Ctrl+Shift+D"
echo "  • Use the inspector to:"
echo "    - View widget hierarchy"
echo "    - Inspect CSS styling"
echo "    - Debug layout issues"
echo "    - Test theme changes live"
echo ""
echo "Starting TalkType..."
echo ""

# Enable GTK Inspector
export GTK_DEBUG=interactive

# Set dev mode
export DEV_MODE=1

# Set Python path to include src directory
export PYTHONPATH="${SCRIPT_DIR}/src:/usr/lib64/python3.13/site-packages:/usr/lib/python3.13/site-packages"

# Launch TalkType tray (which can launch other components)
"${SCRIPT_DIR}/.venv/bin/python" -m talktype.tray
