#!/bin/bash
# Fresh Start Script for Kubuntu Testing
# Wipes all TalkType data so you can test the full onboarding experience
#
# Usage:
#   ./fresh-start-kubuntu.sh          # Clean TalkType only
#   ./fresh-start-kubuntu.sh --full   # Also remove ydotool, PortAudio, input group (requires logout)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FULL_RESET=false
if [[ "$1" == "--full" ]]; then
    FULL_RESET=true
fi

echo "========================================"
echo " TalkType Fresh Start (Kubuntu)"
echo "========================================"
echo ""

# Stop any running TalkType processes
echo -e "${YELLOW}Stopping TalkType processes...${NC}"
pkill -f "talktype" 2>/dev/null || true
pkill -f "TalkType" 2>/dev/null || true
sleep 1
echo -e "${GREEN}✓ Processes stopped${NC}"

# Remove AppImage
echo ""
echo -e "${YELLOW}Removing AppImage...${NC}"
if [[ -f ~/AppImages/TalkType.AppImage ]]; then
    rm -f ~/AppImages/TalkType.AppImage
    echo -e "${GREEN}✓ Removed ~/AppImages/TalkType.AppImage${NC}"
else
    echo -e "  (not found)${NC}"
fi

# Also remove any versioned AppImages
rm -f ~/AppImages/TalkType-v*.AppImage 2>/dev/null && echo -e "${GREEN}✓ Removed versioned AppImages${NC}" || true

# Remove the just_updated flag if present
rm -f ~/AppImages/.talktype_just_updated 2>/dev/null || true

# Remove config directory
echo ""
echo -e "${YELLOW}Removing config...${NC}"
if [[ -d ~/.config/talktype ]]; then
    rm -rf ~/.config/talktype
    echo -e "${GREEN}✓ Removed ~/.config/talktype/${NC}"
else
    echo -e "  (not found)${NC}"
fi

# Remove data directory (models, CUDA, first_run flag)
echo ""
echo -e "${YELLOW}Removing data...${NC}"
if [[ -d ~/.local/share/TalkType ]]; then
    rm -rf ~/.local/share/TalkType
    echo -e "${GREEN}✓ Removed ~/.local/share/TalkType/${NC}"
else
    echo -e "  (not found)${NC}"
fi

# Remove Hugging Face model cache (whisper models)
echo ""
echo -e "${YELLOW}Removing Hugging Face model cache...${NC}"
if [[ -d ~/.cache/huggingface/hub ]]; then
    rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-* 2>/dev/null && \
        echo -e "${GREEN}✓ Removed whisper models from cache${NC}" || echo -e "  (no whisper models found)${NC}"
    rm -rf ~/.cache/huggingface/hub/.locks/models--Systran--faster-whisper-* 2>/dev/null || true
else
    echo -e "  (no cache found)${NC}"
fi
# Also clear xet cache (HuggingFace's chunked storage - can be huge!)
if [[ -d ~/.cache/huggingface/xet ]]; then
    rm -rf ~/.cache/huggingface/xet
    echo -e "${GREEN}✓ Removed HuggingFace xet chunk cache${NC}"
fi

# Remove desktop launcher
echo ""
echo -e "${YELLOW}Removing desktop launcher...${NC}"
if [[ -f ~/.local/share/applications/talktype.desktop ]]; then
    rm -f ~/.local/share/applications/talktype.desktop
    echo -e "${GREEN}✓ Removed ~/.local/share/applications/talktype.desktop${NC}"
else
    echo -e "  (not found)${NC}"
fi

# Remove installed icons (all sizes - for KDE/Plasma compatibility)
echo ""
echo -e "${YELLOW}Removing installed icons...${NC}"
icon_found=false
for size in 256x256 128x128 64x64 48x48 32x32; do
    icon_path=~/.local/share/icons/hicolor/$size/apps/talktype.png
    if [[ -f "$icon_path" ]]; then
        rm -f "$icon_path"
        icon_found=true
    fi
done
if [[ "$icon_found" == true ]]; then
    echo -e "${GREEN}✓ Removed talktype icons${NC}"
else
    echo -e "  (not found)${NC}"
fi

# Remove GNOME extension if installed
echo ""
echo -e "${YELLOW}Removing GNOME extension (if installed)...${NC}"
if [[ -d ~/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io ]]; then
    rm -rf ~/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io
    echo -e "${GREEN}✓ Removed GNOME extension${NC}"
else
    echo -e "  (not found - normal for Kubuntu)${NC}"
fi

# Refresh KDE menu cache
echo ""
echo -e "${YELLOW}Refreshing KDE menu cache...${NC}"
if command -v kbuildsycoca6 &> /dev/null; then
    kbuildsycoca6 --noincremental 2>/dev/null
    echo -e "${GREEN}✓ KDE menu cache refreshed (kbuildsycoca6)${NC}"
elif command -v kbuildsycoca5 &> /dev/null; then
    kbuildsycoca5 --noincremental 2>/dev/null
    echo -e "${GREEN}✓ KDE menu cache refreshed (kbuildsycoca5)${NC}"
else
    echo -e "  (kbuildsycoca not found)${NC}"
fi

# Update icon cache
echo ""
echo -e "${YELLOW}Refreshing icon cache...${NC}"
if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true
    echo -e "${GREEN}✓ Icon cache refreshed${NC}"
fi

# Full reset: remove ydotool setup
if [[ "$FULL_RESET" == true ]]; then
    echo ""
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}FULL RESET: Removing ydotool setup${NC}"
    echo -e "${YELLOW}========================================${NC}"

    # Stop ydotoold service
    echo ""
    echo -e "${YELLOW}Stopping ydotoold service...${NC}"
    systemctl --user stop ydotoold.service 2>/dev/null || true
    systemctl --user disable ydotoold.service 2>/dev/null || true
    echo -e "${GREEN}✓ ydotoold service stopped and disabled${NC}"

    # Remove the systemd service file (created by TalkType onboarding)
    echo ""
    echo -e "${YELLOW}Removing ydotoold service file...${NC}"
    if [[ -f ~/.config/systemd/user/ydotoold.service ]]; then
        rm -f ~/.config/systemd/user/ydotoold.service
        systemctl --user daemon-reload 2>/dev/null || true
        echo -e "${GREEN}✓ Removed ~/.config/systemd/user/ydotoold.service${NC}"
    else
        echo -e "  (not found)${NC}"
    fi

    # Remove user from input group
    echo ""
    echo -e "${YELLOW}Removing $USER from input group...${NC}"
    echo -e "${RED}This requires sudo:${NC}"
    sudo gpasswd -d "$USER" input 2>/dev/null || echo "  (not in group or failed)"
    echo -e "${GREEN}✓ User removed from input group${NC}"

    # Optionally uninstall ydotool package
    echo ""
    echo -e "${YELLOW}Do you want to uninstall the ydotool package? (y/N)${NC}"
    read -r uninstall_ydotool
    if [[ "$uninstall_ydotool" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Uninstalling ydotool...${NC}"
        if command -v dnf &> /dev/null; then
            sudo dnf remove -y ydotool 2>/dev/null && echo -e "${GREEN}✓ ydotool uninstalled${NC}" || echo "  (failed)"
        elif command -v apt &> /dev/null; then
            sudo apt remove -y ydotool 2>/dev/null && echo -e "${GREEN}✓ ydotool uninstalled${NC}" || echo "  (failed)"
        else
            echo "  (unknown package manager - please uninstall manually)"
        fi
    else
        echo "  (skipped - ydotool package kept)"
    fi

    # Optionally uninstall PortAudio library
    echo ""
    echo -e "${YELLOW}Do you want to uninstall the PortAudio library? (y/N)${NC}"
    echo -e "  (This tests the audio library installation during onboarding)"
    read -r uninstall_portaudio
    if [[ "$uninstall_portaudio" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Uninstalling PortAudio...${NC}"
        if command -v dnf &> /dev/null; then
            sudo dnf remove -y portaudio 2>/dev/null && echo -e "${GREEN}✓ PortAudio uninstalled${NC}" || echo "  (failed)"
        elif command -v apt &> /dev/null; then
            sudo apt remove -y libportaudio2 2>/dev/null && echo -e "${GREEN}✓ PortAudio uninstalled${NC}" || echo "  (failed)"
        else
            echo "  (unknown package manager - please uninstall manually)"
        fi
    else
        echo "  (skipped - PortAudio library kept)"
    fi

    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}IMPORTANT: You must LOG OUT and LOG IN${NC}"
    echo -e "${RED}for group changes to take effect!${NC}"
    echo -e "${RED}========================================${NC}"
fi

echo ""
echo -e "${GREEN}========================================"
echo -e " Fresh start complete!"
echo -e "========================================${NC}"
echo ""
echo "TalkType has been completely removed."
echo ""
echo "To test fresh install:"
echo "  1. Download the AppImage from GitHub"
echo "  2. Make it executable: chmod +x TalkType-*.AppImage"
echo "  3. Run it: ./TalkType-*.AppImage"
echo ""

if [[ "$FULL_RESET" == true ]]; then
    echo -e "${YELLOW}Remember: Log out and back in before testing!${NC}"
    echo ""
fi
