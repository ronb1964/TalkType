#!/bin/bash
# TalkType Fresh Start Script - Run this before EVERY test
# This ensures a true first-run experience

set -e

echo "🧹 TalkType Fresh Start Cleanup"
echo "================================"
echo ""

# 1. Kill all TalkType processes (CRITICAL: Must stop dev version before testing AppImage!)
echo "1. Stopping all TalkType processes..."
echo "   (This includes the dev version - dev and AppImage cannot run together)"
pkill -f "TalkType.*AppImage" 2>/dev/null || true
pkill -f "talktype.tray" 2>/dev/null || true
pkill -f "talktype.app" 2>/dev/null || true
pkill -f "python.*talktype" 2>/dev/null || true
sleep 2
if pgrep -f "talktype" > /dev/null; then
    echo "   ⚠️  Some processes still running, force killing..."
    pkill -9 -f "talktype" 2>/dev/null || true
    sleep 1
fi
echo "   ✓ All processes stopped"

# 2. Remove config directory
echo "2. Removing config directory..."
rm -rf ~/.config/talktype
echo "   ✓ Config removed: ~/.config/talktype"

# 3. Remove data directory (including CUDA libs and models)
echo "3. Removing data directory..."
rm -rf ~/.local/share/talktype
rm -rf ~/.local/share/TalkType
echo "   ✓ Data removed: ~/.local/share/talktype"
echo "   ✓ CUDA libraries removed (will be re-downloaded on first GPU use)"
echo "   ✓ All models removed (small, medium, large - will be re-downloaded)"

# 4. Uninstall GNOME extension
echo "4. Uninstalling GNOME extension..."
gnome-extensions uninstall talktype@ronb1964.github.io 2>/dev/null && echo "   ✓ Extension uninstalled" || echo "   ✓ Extension not installed"

# 5. Remove autostart entry
echo "5. Removing autostart entry..."
rm -f ~/.config/autostart/talktype.desktop
echo "   ✓ Autostart removed"

# 6. Verify cleanup
echo ""
echo "🔍 Verification:"
[ ! -d ~/.config/talktype ] && echo "   ✓ Config dir removed" || echo "   ❌ Config dir still exists!"
[ ! -d ~/.local/share/talktype ] && echo "   ✓ Data dir removed" || echo "   ❌ Data dir still exists!"
! pgrep -f "talktype" > /dev/null && echo "   ✓ No processes running" || echo "   ❌ Processes still running!"

echo ""
echo "✅ Fresh start complete! Ready for first-run testing."
echo ""
echo "To test: ./TalkType-v0.3.8-x86_64.AppImage"
