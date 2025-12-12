#!/bin/bash
# TalkType Dev Environment Fresh Start Script
# Cleans ONLY dev environment for testing welcome dialog and first-run experience

set -e

echo "🧹 TalkType Dev Environment Fresh Start"
echo "========================================"
echo ""
echo "NOTE: This ONLY cleans dev environment."
echo "AppImage environment stays intact!"
echo ""

# 1. Kill all TalkType processes (dev and AppImage)
echo "1. Stopping all TalkType processes..."
# Kill any running TalkType processes
pkill -f "TalkType.*AppImage" 2>/dev/null || true
pkill -f "talktype.tray" 2>/dev/null || true
pkill -f "talktype.app" 2>/dev/null || true
pkill -f "python.*talktype" 2>/dev/null || true
pkill -f "dictate" 2>/dev/null || true
sleep 2

# Force kill if anything is still running
if pgrep -f "talktype" > /dev/null; then
    echo "   ⚠️  Some processes still running, force killing..."
    pkill -9 -f "talktype" 2>/dev/null || true
    pkill -9 -f "dictate" 2>/dev/null || true
    sleep 1
fi

# Remove lock file if it exists
rm -f /run/user/$(id -u)/talktype-tray.lock 2>/dev/null || true

echo "   ✓ All processes stopped"

# 2. Remove dev config directory
echo "2. Removing dev config directory..."
rm -rf ~/.config/talktype-dev
echo "   ✓ Dev config removed: ~/.config/talktype-dev/"
echo "   ℹ️  AppImage config preserved: ~/.config/talktype/"

# 3. Remove dev data directory
echo "3. Removing dev data directory..."
rm -rf ~/.local/share/TalkType-dev
echo "   ✓ Dev data removed: ~/.local/share/TalkType-dev/"
echo "   ℹ️  AppImage data preserved: ~/.local/share/TalkType/"
echo "   ✓ Dev CUDA libraries removed"
echo "   ℹ️  AppImage CUDA libraries preserved (if you had them)"

# 4. Remove Hugging Face model cache
echo "4. Removing Hugging Face model cache..."
if [ -d ~/.cache/huggingface/hub ]; then
    rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-* 2>/dev/null || true
    echo "   ✓ All whisper models removed (small, medium, large - will be re-downloaded)"
else
    echo "   ✓ No model cache found"
fi

# 5. Uninstall GNOME extension
echo "5. Uninstalling GNOME extension..."
gnome-extensions uninstall talktype@ronb1964.github.io 2>/dev/null && echo "   ✓ Extension uninstalled" || echo "   ✓ Extension not installed"

# 6. Remove autostart entry
echo "6. Removing autostart entry..."
rm -f ~/.config/autostart/talktype.desktop
echo "   ✓ Autostart removed"

# 7. Verify cleanup
echo ""
echo "🔍 Verification:"
[ ! -d ~/.config/talktype-dev ] && echo "   ✓ Dev config dir removed" || echo "   ❌ Dev config dir still exists!"
[ ! -d ~/.local/share/TalkType-dev ] && echo "   ✓ Dev data dir removed" || echo "   ❌ Dev data dir still exists!"
! pgrep -f "talktype" > /dev/null && echo "   ✓ No processes running" || echo "   ❌ Processes still running!"

echo ""
echo "✅ Fresh start complete! Ready for dev testing."
echo ""
echo "To test: ./run-dev.sh"
echo "   or:   gtk-launch talktype-dev"
