#!/bin/bash
# TuxTalk Fresh Start Script - Cleans ONLY AppImage environment
# Dev environment (~/.config/tuxtalk-dev/ and ~/.local/share/TuxTalk-dev/, plus
# their pre-rename talktype-dev / TalkType-dev links) is preserved!
# Since the 0.15.0 rename it clears both names: TuxTalk and the old TalkType.

set -e

echo "🧹 TuxTalk AppImage Fresh Start Cleanup"
echo "========================================"
echo ""
echo "NOTE: This ONLY cleans AppImage environment."
echo "Your dev environment stays intact!"
echo ""

# 1. Kill all TuxTalk (and old TalkType) processes
echo "1. Stopping all TuxTalk processes..."
pkill -f "TuxTalk.*AppImage" 2>/dev/null || true
pkill -f "TalkType.*AppImage" 2>/dev/null || true
pkill -f "tuxtalk.tray" 2>/dev/null || true
pkill -f "tuxtalk.app" 2>/dev/null || true
pkill -f "python.*talktype" 2>/dev/null || true
sleep 2
if pgrep -f "tuxtalk|talktype" > /dev/null; then
    echo "   ⚠️  Some processes still running, force killing..."
    pkill -9 -f "tuxtalk|talktype" 2>/dev/null || true
    sleep 1
fi
echo "   ✓ All processes stopped"

# 2. Remove AppImage config directory (NOT -dev!)
echo "2. Removing AppImage config directory..."
rm -rf ~/.config/talktype ~/.config/tuxtalk
echo "   ✓ AppImage config removed: ~/.config/tuxtalk (and the old ~/.config/talktype)"
echo "   ℹ️  Dev config preserved: ~/.config/tuxtalk-dev/"

# 3. Remove AppImage data directory (NOT -dev!)
echo "3. Removing AppImage data directory..."
rm -rf ~/.local/share/talktype
rm -rf ~/.local/share/TalkType ~/.local/share/TuxTalk
echo "   ✓ AppImage data removed: ~/.local/share/TuxTalk (and the old TalkType)"
echo "   ℹ️  Dev data preserved: ~/.local/share/TuxTalk-dev/"
echo "   ✓ AppImage CUDA libraries removed"
echo "   ℹ️  Dev CUDA libraries preserved (if you had them)"

# 4. Remove Hugging Face model cache (including xet chunk cache)
echo "4. Removing Hugging Face model cache..."
# Every model TuxTalk downloads, so first run really downloads them again:
# Whisper for the processor and CUDA (Systran), Parakeet for the processor
# (istupakov) and for Vulkan (ggml-org), Whisper for Vulkan (ggerganov), and
# the self-corrections AI (Qwen). Parakeet became the default in 0.14.0 and
# was never removed here, so release tests skipped its download. Other apps'
# models in the same cache are left alone.
TALKTYPE_MODEL_REPOS=(
    "models--Systran--faster-whisper-*"
    "models--istupakov--parakeet-tdt-0.6b-v3-onnx"
    "models--ggml-org--parakeet-GGUF"
    "models--ggerganov--whisper.cpp"
    "models--Qwen--Qwen2.5-1.5B-Instruct-GGUF"
)
if [ -d ~/.cache/huggingface/hub ]; then
    for repo in "${TALKTYPE_MODEL_REPOS[@]}"; do
        rm -rf ~/.cache/huggingface/hub/$repo ~/.cache/huggingface/hub/.locks/$repo 2>/dev/null || true
    done
    echo "   ✓ All TuxTalk models removed (Whisper, Parakeet, Vulkan and AI - will be re-downloaded)"
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
rm -f ~/.config/autostart/talktype.desktop ~/.config/autostart/tuxtalk.desktop
echo "   ✓ AppImage autostart removed"
# Disable dev autostart so only the AppImage starts on next login during testing
dev_found=no
for f in ~/.config/autostart/tuxtalk-dev.desktop ~/.config/autostart/talktype-dev.desktop; do
    if [ -f "$f" ]; then
        sed -i 's/X-GNOME-Autostart-enabled=true/X-GNOME-Autostart-enabled=false/' "$f"
        dev_found=yes
    fi
done
if [ "$dev_found" = yes ]; then
    echo "   ✓ Dev autostart disabled (will be re-enabled after testing)"
else
    echo "   ℹ️  Dev autostart not found, skipping"
fi

# 7. Verify cleanup
echo ""
echo "🔍 Verification:"
[ ! -e ~/.config/tuxtalk ] && [ ! -e ~/.config/talktype ] && echo "   ✓ Config dir removed" || echo "   ❌ Config dir still exists!"
[ ! -e ~/.local/share/TuxTalk ] && [ ! -e ~/.local/share/TalkType ] && echo "   ✓ Data dir removed" || echo "   ❌ Data dir still exists!"
left=$(for repo in "${TALKTYPE_MODEL_REPOS[@]}"; do ls -d ~/.cache/huggingface/hub/$repo 2>/dev/null || true; done)
[ -z "$left" ] && echo "   ✓ TuxTalk models removed" || echo "   ❌ Models still there: $left"
! pgrep -f "tuxtalk|talktype" > /dev/null && echo "   ✓ No processes running" || echo "   ❌ Processes still running!"

echo ""
echo "✅ Fresh start complete! Ready for first-run testing."
echo ""
echo "To test: run the latest ./TuxTalk-v*-x86_64.AppImage build"
