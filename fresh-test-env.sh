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

# 6. Copy latest AppImage to ~/AppImages if it exists
if [ -f "TalkType-v0.3.7-x86_64.AppImage" ]; then
    echo "6️⃣  Copying latest AppImage to ~/AppImages/..."
    cp TalkType-v0.3.7-x86_64.AppImage ~/AppImages/
else
    echo "6️⃣  Skipping AppImage copy (not found in current directory)"
fi

echo ""
echo "✅ Fresh environment ready!"
echo ""
echo "Verification:"
echo "  Config file:    $([ -f ~/.config/talktype/config.toml ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo "  First-run flag: $([ -f ~/.local/share/TalkType/.first_run_done ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo "  CUDA libs:      $([ -d ~/.local/share/TalkType/cuda ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo "  Small model:    $([ -d ~/.cache/huggingface/hub/models--Systran--faster-whisper-small ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo "  Large model:    $([ -d ~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3 ] && echo '❌ EXISTS' || echo '✓ Removed')"
echo ""
echo "🚀 Ready to test: ~/AppImages/TalkType-v0.3.7-x86_64.AppImage"
