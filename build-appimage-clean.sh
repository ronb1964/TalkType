#!/bin/bash
set -e

# Clean AppImage Build Script - Use Poetry venv only
echo "🧹 Clean TalkType AppImage Builder (Poetry-based)"
echo "================================================"

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
systemctl --user stop ron-dictation.service 2>/dev/null || true
pkill -f "dictate-tray" 2>/dev/null || true
pkill -f "ron_dictation" 2>/dev/null || true
pkill -f "TalkType" 2>/dev/null || true
sleep 1

# Clean start
print_status "Cleaning old AppDir..."
rm -rf AppDir/usr/ 2>/dev/null || true
mkdir -p AppDir/usr/{bin,lib,share/applications,share/icons/hicolor/scalable/apps}

# Use project venv
PROJECT_VENV=".venv"
print_status "Using project venv: $PROJECT_VENV"

# Copy project virtual environment
print_status "Copying project virtual environment..."
mkdir -p AppDir/usr/lib/python3.13/site-packages
cp -r "$PROJECT_VENV"/lib/python3.13/site-packages/* AppDir/usr/lib/python3.13/site-packages/
cp "$PROJECT_VENV"/bin/python* AppDir/usr/bin/
cp "$PROJECT_VENV"/bin/pip* AppDir/usr/bin/ 2>/dev/null || true

# Copy our source code  
print_status "Copying TalkType source code..."
cp -r src AppDir/usr/

# Create simple launcher scripts that use the copied venv
print_status "Creating launcher scripts..."
cat > AppDir/usr/bin/dictate-tray << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")/.."
export PYTHONPATH="$HERE:$PYTHONPATH"
exec "$HERE/bin/python" -m src.talktype.tray "$@"
EOF

cat > AppDir/usr/bin/dictate-prefs << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")/.."
export PYTHONPATH="$HERE:$PYTHONPATH"
exec "$HERE/bin/python" -m src.talktype.prefs "$@"
EOF

cat > AppDir/usr/bin/dictate << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")/.."
export PYTHONPATH="$HERE:$PYTHONPATH"
exec "$HERE/bin/python" -m src.talktype.app "$@"
EOF

chmod +x AppDir/usr/bin/dictate*

# Update AppRun to be simpler
cat > AppDir/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"

# Set up environment
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/lib:$LD_LIBRARY_PATH"
export PYTHONPATH="$HERE/usr/src:$PYTHONPATH"

# Set up audio and GTK
export PULSE_RUNTIME_PATH="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/pulse"
export XDG_DATA_DIRS="$HERE/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

# Parse arguments
case "${1:-tray}" in
    "tray"|"")
        exec "$HERE/usr/bin/dictate-tray" "${@:2}"
        ;;
    "prefs"|"preferences")
        exec "$HERE/usr/bin/dictate-prefs" "${@:2}"
        ;;
    "dictate"|"service")
        exec "$HERE/usr/bin/dictate" "${@:2}"
        ;;
    "--help"|"-h")
        echo "TalkType - AI-powered dictation for Wayland"
        echo ""
        echo "Usage:"
        echo "  $0 [tray]         Start system tray (default)"
        echo "  $0 prefs          Open preferences window"
        echo "  $0 dictate        Run dictation service directly"
        echo "  $0 --help         Show this help"
        echo ""
        echo "Default action: Start system tray"
        ;;
    *)
        exec "$HERE/usr/bin/dictate-tray" "$@"
        ;;
esac
EOF

chmod +x AppDir/AppRun

# Test the environment
print_status "Testing project environment..."
if AppDir/usr/bin/dictate-tray --help >/dev/null 2>&1; then
    print_success "Project environment is working"
else
    echo "❌ Project environment test failed"
    exit 1
fi

# Create AppImage
print_status "Creating AppImage with appimagetool..."
if [[ -f "appimagetool" ]]; then
    rm -f TalkType-*.AppImage
    ./appimagetool AppDir TalkType-x86_64.AppImage
    
    if [[ -f "TalkType-x86_64.AppImage" ]]; then
        chmod +x TalkType-x86_64.AppImage
        print_success "AppImage created: TalkType-x86_64.AppImage"
        
        # Quick test
        if ./TalkType-x86_64.AppImage --help >/dev/null 2>&1; then
            print_success "AppImage basic test passed!"
        fi
    else
        echo "❌ AppImage creation failed"
        exit 1
    fi
else
    echo "❌ appimagetool not found"
    exit 1
fi

# Restart services
print_status "Restarting services..."
systemctl --user start ron-dictation.service 2>/dev/null || true

print_success "Clean AppImage build complete!"
echo "📁 Generated: TalkType-x86_64.AppImage"
echo "🧪 Test preferences: ./TalkType-x86_64.AppImage prefs"
