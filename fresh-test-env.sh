#!/bin/bash
# Fresh Test Environment Setup for TalkType
# This script ensures a completely clean first-run test environment

set -e

echo "🧹 Setting up fresh TalkType test environment..."
echo ""

# 1. Stop any running TalkType processes (including tray icon)
echo "1️⃣  Stopping TalkType processes..."
pkill -f "dictate-tray" 2>/dev/null || true
pkill -f "dictate" 2>/dev/null || true
pkill -f "TalkType.*AppImage" 2>/dev/null || true
pkill -f "talktype.tray" 2>/dev/null || true
pkill -f "talktype.app" 2>/dev/null || true
systemctl --user stop ron-dictation.service 2>/dev/null || true
sleep 2

# Unmount any mounted AppImages
fusermount -u /tmp/.mount_TalkTy* 2>/dev/null || true
sleep 1

# 2. Remove config file
echo "2️⃣  Removing config file..."
rm -f ~/.config/talktype/config.toml

# 3. Remove first-run flag
echo "3️⃣  Removing first-run flag..."
rm -f ~/.local/share/TalkType/.first_run_done

# 4. Remove CUDA libraries
echo "4️⃣  Removing CUDA libraries..."
rm -rf ~/.local/share/TalkType/cuda

# 5. Remove all model caches
echo "5️⃣  Removing model caches..."
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-small
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-medium
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3

# 6. Remove GNOME extension
echo "6️⃣  Removing GNOME extension..."
rm -rf ~/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io
# Restart GNOME Shell if running (Wayland safe - just disables extension)
if pgrep -x "gnome-shell" >/dev/null; then
    gnome-extensions disable talktype@ronb1964.github.io 2>/dev/null || true
fi

# 7. Copy latest AppImage to ~/AppImages if it exists
if [ -f "TalkType-v0.3.8-x86_64.AppImage" ]; then
    echo "7️⃣  Copying latest AppImage to ~/AppImages/..."
    cp TalkType-v0.3.8-x86_64.AppImage ~/AppImages/
elif [ -f "TalkType-v0.3.7-x86_64.AppImage" ]; then
    echo "7️⃣  Copying v0.3.7 AppImage to ~/AppImages/..."
    cp TalkType-v0.3.7-x86_64.AppImage ~/AppImages/
else
    echo "7️⃣  Skipping AppImage copy (not found in current directory)"
fi

echo ""
echo "✅ Fresh environment ready!"
echo ""
echo "Verification:"
echo "  Config file:    $([ -f ~/.config/talktype/config.toml ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo "  First-run flag: $([ -f ~/.local/share/TalkType/.first_run_done ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo "  CUDA libs:      $([ -d ~/.local/share/TalkType/cuda ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo "  GNOME extension: $([ -d ~/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo "  Small model:    $([ -d ~/.cache/huggingface/hub/models--Systran--faster-whisper-small ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo "  Large model:    $([ -d ~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3 ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo ""
LATEST_APPIMAGE=$(ls -t ~/AppImages/TalkType-v*.AppImage 2>/dev/null | head -1)
echo "🚀 Ready to test: ${LATEST_APPIMAGE:-No AppImage found}"
