#!/bin/bash
#
# Install xdotool for window title detection
# This is needed to detect terminal windows for proper paste shortcut selection
#

echo "Installing xdotool for terminal detection..."
echo ""
echo "xdotool allows TalkType to detect which window is active"
echo "so it can choose the correct paste shortcut:"
echo "  - Ctrl+V for regular apps (chat, editors)"  
echo "  - Shift+Ctrl+V for terminals"
echo ""

sudo dnf5 install -y xdotool

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ xdotool installed successfully!"
    echo ""
    echo "Now TalkType can detect terminal windows properly."
else
    echo ""
    echo "❌ Installation failed."
    echo "You can install manually: sudo dnf5 install xdotool"
fi


