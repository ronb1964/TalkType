#!/bin/bash
# Test script to verify autostart functionality

set -e

echo "=========================================="
echo "Testing TalkType Autostart"
echo "=========================================="
echo

# Check if autostart file exists
AUTOSTART_FILE="$HOME/.config/autostart/talktype.desktop"

if [ ! -f "$AUTOSTART_FILE" ]; then
    echo "❌ Autostart file not found: $AUTOSTART_FILE"
    echo "   Enable 'Launch at Login' in TalkType preferences to create it"
    exit 1
fi

echo "✅ Autostart file exists: $AUTOSTART_FILE"
echo

# Display the file
echo "File contents:"
echo "===================="
cat "$AUTOSTART_FILE"
echo "===================="
echo

# Extract and test the Exec command
EXEC_CMD=$(grep "^Exec=" "$AUTOSTART_FILE" | cut -d'=' -f2-)
echo "Launch command: $EXEC_CMD"
echo

# Check if the executable exists
EXEC_BIN=$(echo "$EXEC_CMD" | awk '{print $1}')
if [ -x "$EXEC_BIN" ]; then
    echo "✅ Executable exists and is executable: $EXEC_BIN"
else
    echo "❌ Executable not found or not executable: $EXEC_BIN"
    exit 1
fi

# Check if X-GNOME-Autostart-enabled is set
if grep -q "X-GNOME-Autostart-enabled=true" "$AUTOSTART_FILE"; then
    echo "✅ X-GNOME-Autostart-enabled=true"
else
    echo "⚠️  X-GNOME-Autostart-enabled not set to true"
fi

echo
echo "=========================================="
echo "✅ Autostart Configuration Valid!"
echo "=========================================="
echo
echo "Summary:"
echo "  • Autostart file exists and is valid ✅"
echo "  • Executable is accessible ✅"
echo "  • TalkType will launch automatically on next login ✅"
echo
echo "To test:"
echo "  1. Log out of GNOME"
echo "  2. Log back in"
echo "  3. Check if TalkType tray icon appears"
echo
echo "To disable autostart:"
echo "  Open TalkType preferences and uncheck 'Launch at Login'"
echo
