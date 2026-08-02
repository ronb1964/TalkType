#!/bin/bash
# TalkType Fresh Start Script - Cleans ONLY AppImage environment
# Dev environment (~/.config/talktype-dev/ and ~/.local/share/TalkType-dev/) is preserved!

set -e

echo "🧹 TalkType AppImage Fresh Start Cleanup"
echo "========================================"
echo ""
echo "NOTE: This ONLY cleans AppImage environment."
echo "Your dev environment stays intact!"
echo ""

# 1. Kill all TalkType processes
echo "1. Stopping all TalkType processes..."
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

# 2. Remove AppImage config directory (NOT -dev!)
echo "2. Removing AppImage config directory..."
rm -rf ~/.config/talktype
echo "   ✓ AppImage config removed: ~/.config/talktype"
echo "   ℹ️  Dev config preserved: ~/.config/talktype-dev/"

# 3. Remove AppImage data directory (NOT -dev!)
echo "3. Removing AppImage data directory..."
rm -rf ~/.local/share/talktype
rm -rf ~/.local/share/TalkType
echo "   ✓ AppImage data removed: ~/.local/share/TalkType"
echo "   ℹ️  Dev data preserved: ~/.local/share/TalkType-dev/"
echo "   ✓ AppImage CUDA libraries removed"
echo "   ℹ️  Dev CUDA libraries preserved (if you had them)"

# 4. Remove Hugging Face model cache (including xet chunk cache)
echo "4. Removing Hugging Face model cache..."
if [ -d ~/.cache/huggingface/hub ]; then
    rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-* 2>/dev/null || true
    rm -rf ~/.cache/huggingface/hub/.locks/models--Systran--faster-whisper-* 2>/dev/null || true
    echo "   ✓ All whisper models removed (small, medium, large - will be re-downloaded)"
else
    echo "   ✓ No model cache found"
fi
# Also clear xet cache (HuggingFace's chunked storage - can be huge!)
if [ -d ~/.cache/huggingface/xet ]; then
    rm -rf ~/.cache/huggingface/xet
    echo "   ✓ HuggingFace xet chunk cache removed"
fi

# 5. Uninstall GNOME extension (both via gnome-extensions and direct folder removal)
echo "5. Uninstalling GNOME extension..."
gnome-extensions uninstall talktype@ronb1964.github.io 2>/dev/null || true
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io"
if [ -d "$EXT_DIR" ]; then
    rm -rf "$EXT_DIR"
    echo "   ✓ Extension directory removed"
else
    echo "   ✓ Extension not installed"
fi

# 6. Remove AppImage autostart and disable dev autostart
echo "6. Removing AppImage autostart and disabling dev autostart..."
rm -f ~/.config/autostart/talktype.desktop
echo "   ✓ AppImage autostart removed"
# Disable dev autostart so only the AppImage starts on next login during testing
if [ -f ~/.config/autostart/talktype-dev.desktop ]; then
    sed -i 's/X-GNOME-Autostart-enabled=true/X-GNOME-Autostart-enabled=false/' ~/.config/autostart/talktype-dev.desktop
    echo "   ✓ Dev autostart disabled (will be re-enabled after testing)"
else
    echo "   ℹ️  Dev autostart not found, skipping"
fi

# 7. Verify cleanup
echo ""
echo "🔍 Verification:"
[ ! -d ~/.config/talktype ] && echo "   ✓ Config dir removed" || echo "   ❌ Config dir still exists!"
[ ! -d ~/.local/share/talktype ] && echo "   ✓ Data dir removed" || echo "   ❌ Data dir still exists!"
! pgrep -f "talktype" > /dev/null && echo "   ✓ No processes running" || echo "   ❌ Processes still running!"

echo ""
echo "✅ Fresh start complete! Ready for first-run testing."
echo ""
echo "To test: run the latest ./TalkType-v*-x86_64.AppImage build"
