#!/bin/bash
set -e

# Safe AppImage Build Script
# This script ensures your running TalkType app won't be broken during builds

echo "🔧 TalkType Safe AppImage Builder"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]] || [[ ! -d "src/talktype" ]]; then
    print_error "Must be run from TalkType project root directory"
    exit 1
fi

# Check current branch
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "appimage-builds" ]]; then
    print_warning "Not on appimage-builds branch. Current: $CURRENT_BRANCH"
    
    # Check if appimage-builds branch exists
    if git show-ref --verify --quiet refs/heads/appimage-builds; then
        print_status "Switching to appimage-builds branch..."
        git checkout appimage-builds
    else
        print_status "Creating appimage-builds branch..."
        git checkout -b appimage-builds
    fi
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    print_error "You have uncommitted changes. Please commit or stash them first."
    git status --porcelain
    exit 1
fi

print_status "Stopping TalkType services to prevent conflicts..."

# Stop systemd service if running
if systemctl --user is-active --quiet talktype.service 2>/dev/null; then
    print_status "Stopping talktype.service..."
    systemctl --user stop talktype.service
    RESTART_SERVICE=1
fi

# Kill any running TalkType processes
print_status "Stopping TalkType processes..."
pkill -f "dictate-tray" 2>/dev/null || true
pkill -f "talktype" 2>/dev/null || true
pkill -f "TalkType" 2>/dev/null || true

# Wait a moment for processes to die
sleep 2

print_status "Building AppImage..."

# Check if appimage-builder exists
if [[ ! -f "appimage-builder" ]]; then
    print_error "appimage-builder not found. Please ensure build tools are available."
    exit 1
fi

# Check if AppImageTool exists  
if [[ ! -f "appimagetool" ]]; then
    print_error "appimagetool not found. Please ensure build tools are available."
    exit 1
fi

# Build the AppImage
print_status "Running appimage-builder..."
if ./appimage-builder --recipe appimage-builder.yml; then
    print_success "AppImage built successfully!"
    
    # Find the generated AppImage
    APPIMAGE=$(find . -name "*.AppImage" -type f -newer appimage-builder.yml | head -1)
    if [[ -n "$APPIMAGE" ]]; then
        print_success "Generated: $APPIMAGE"
        
        # Make it executable
        chmod +x "$APPIMAGE"
        
        # Test basic functionality
        print_status "Testing AppImage..."
        if "$APPIMAGE" --help >/dev/null 2>&1; then
            print_success "AppImage appears to be working!"
        else
            print_warning "AppImage test failed, but file was created"
        fi
    fi
else
    print_error "AppImage build failed!"
    exit 1
fi

print_status "Cleaning up and returning to main branch..."

# Switch back to main
git checkout main

# Clean any build artifacts from main branch
print_status "Cleaning build artifacts..."
rm -rf AppDir/usr/ 2>/dev/null || true
git clean -fd

print_status "Restoring TalkType services..."

# Restart service if it was running
if [[ "${RESTART_SERVICE:-0}" == "1" ]]; then
    print_status "Restarting talktype.service..."
    systemctl --user start talktype.service
fi

print_success "Safe AppImage build complete!"
print_status "Your development environment has been restored."
print_status "AppImage location: Check appimage-builds branch for the generated .AppImage file"

echo ""
echo "📋 Next steps:"
echo "  • Test the AppImage on other systems"
echo "  • Upload to GitHub releases if ready"
echo "  • Your local TalkType should be working normally again"

