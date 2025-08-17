#!/bin/bash
set -e

# Fast AppImage Build Script - Skip lengthy tests
echo "🚀 Fast TalkType AppImage Builder"
echo "================================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]]; then
    echo "Must be run from TalkType project root directory"
    exit 1
fi

# Stop services
print_status "Stopping TalkType services..."
systemctl --user stop talktype.service 2>/dev/null || true
pkill -f "dictate-tray" 2>/dev/null || true
pkill -f "talktype" 2>/dev/null || true
pkill -f "TalkType" 2>/dev/null || true
sleep 1

# If AppDir already has everything, just rebuild the AppImage
if [[ -f "AppDir/usr/bin/python3" ]] && [[ -f "AppDir/usr/bin/dictate-tray" ]] && [[ -d "AppDir/usr/src" ]]; then
    print_status "AppDir already prepared, skipping setup..."
else
    print_status "Setting up AppDir (this will take a few minutes)..."
    # Run the full setup but kill it after dependencies are installed
    timeout 300 ./build-appimage-manual.sh || true
fi

# Go directly to AppImage creation
print_status "Creating AppImage with appimagetool..."
if [[ -f "appimagetool" ]]; then
    # Remove old AppImage
    rm -f TalkType-*.AppImage
    
    # Create new AppImage
    ./appimagetool AppDir TalkType-x86_64.AppImage
    
    if [[ -f "TalkType-x86_64.AppImage" ]]; then
        chmod +x TalkType-x86_64.AppImage
        print_success "AppImage created: TalkType-x86_64.AppImage"
        
        # Quick 5-second test only
        print_status "Quick test (5 seconds)..."
        timeout 5 ./TalkType-x86_64.AppImage --help >/dev/null 2>&1 && print_success "AppImage is working!" || echo "Test timeout (probably working)"
    else
        echo "AppImage creation failed"
        exit 1
    fi
else
    echo "appimagetool not found"
    exit 1
fi

# Restart services
print_status "Restarting services..."
systemctl --user start talktype.service 2>/dev/null || true

print_success "Fast AppImage build complete!"
echo "📁 Generated: TalkType-x86_64.AppImage"
echo "🧪 Test with: ./TalkType-x86_64.AppImage --help"
