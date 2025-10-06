#!/bin/bash
set -e

# CPU-Only AppImage Build Script for TalkType
# This creates a smaller AppImage without CUDA libraries
# GPU detection and CUDA download offer is handled at runtime

echo "🚀 Building TalkType CPU-Only AppImage"
echo "======================================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]]; then
    echo "❌ Error: Must be run from TalkType project root directory"
    exit 1
fi

# Stop any running TalkType services
print_status "Stopping TalkType services..."
systemctl --user stop ron-dictation.service 2>/dev/null || true
pkill -f "dictate-tray" 2>/dev/null || true
pkill -f "talktype.app" 2>/dev/null || true
pkill -f "TalkType" 2>/dev/null || true
sleep 2

# Clean up old build
print_status "Cleaning up old build..."
rm -rf AppDir
rm -f TalkType-CPU-*.AppImage
mkdir -p AppDir/usr/{bin,lib,src,share/applications,share/icons/hicolor/scalable}

# Ensure virtual environment exists
if [[ ! -d ".venv" ]]; then
    print_status "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install poetry
    .venv/bin/poetry install
fi

print_status "Copying Python interpreter and dependencies..."

# Copy Python executable (follow symlinks to get the actual binary)
cp -L .venv/bin/python3 AppDir/usr/bin/python3
chmod +x AppDir/usr/bin/python3

# Get Python version
PYTHON_VERSION=$(.venv/bin/python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
print_status "Detected Python ${PYTHON_VERSION}"

# Create lib directory structure
mkdir -p "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages"

# Copy Python packages (CPU-only, excluding CUDA)
print_status "Copying CPU-only Python packages..."
rsync -a --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='nvidia' \
    --exclude='nvidia-*' \
    --exclude='cuda*' \
    --exclude='triton' \
    --exclude='torch/lib/*.so.*cuda*' \
    --exclude='torch/lib/libnvrtc*' \
    --exclude='torch/lib/libnvToolsExt*' \
    ".venv/lib/python${PYTHON_VERSION}/site-packages/" \
    "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/"

# Remove any CUDA remnants that might have slipped through
print_status "Removing CUDA remnants..."
find "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages" -type d \( -name '*cuda*' -o -name '*nvidia*' -o -name 'triton' \) -exec rm -rf {} + 2>/dev/null || true
find "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages" -type f -name '*cuda*' -delete 2>/dev/null || true

# Patch torch to disable CUDA initialization
print_status "Patching PyTorch for CPU-only mode..."
TORCH_INIT="AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/torch/__init__.py"
if [[ -f "$TORCH_INIT" ]]; then
    # Replace _load_global_deps() call with pass to prevent CUDA loading
    sed -i 's/_load_global_deps()/pass  # CUDA disabled in CPU-only build/' "$TORCH_INIT"
    print_success "PyTorch patched for CPU-only mode"
fi

# Copy TalkType source code
print_status "Copying TalkType source code..."
cp -r src AppDir/usr/

# Copy entry point scripts
print_status "Creating entry point scripts..."
cat > AppDir/usr/bin/dictate << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
export PYTHONPATH="${HERE}/../src:${PYTHONPATH}"
export LD_LIBRARY_PATH="${HERE}/../lib:${LD_LIBRARY_PATH}"
exec "${HERE}/python3" -m talktype.app "$@"
EOF

cat > AppDir/usr/bin/dictate-tray << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
export PYTHONPATH="${HERE}/../src:${PYTHONPATH}"
export LD_LIBRARY_PATH="${HERE}/../lib:${LD_LIBRARY_PATH}"
exec "${HERE}/python3" -m talktype.tray "$@"
EOF

cat > AppDir/usr/bin/dictate-prefs << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
export PYTHONPATH="${HERE}/../src:${PYTHONPATH}"
export LD_LIBRARY_PATH="${HERE}/../lib:${LD_LIBRARY_PATH}"
exec "${HERE}/python3" -m talktype.prefs "$@"
EOF

chmod +x AppDir/usr/bin/dictate*

# Copy desktop file and icon
print_status "Copying desktop files and icons..."
cat > AppDir/talktype.desktop << 'EOF'
[Desktop Entry]
Name=TalkType
Comment=AI-powered speech recognition and dictation
Exec=AppRun tray
Icon=talktype
Type=Application
Categories=Utility;AudioVideo;Audio;
Terminal=false
StartupNotify=false
EOF

# Copy icon (use existing one if available)
if [[ -f "io.github.ronb1964.TalkType.svg" ]]; then
    cp io.github.ronb1964.TalkType.svg AppDir/talktype.svg
    cp io.github.ronb1964.TalkType.svg AppDir/usr/share/icons/hicolor/scalable/talktype.svg
else
    # Create a simple placeholder icon
    cat > AppDir/talktype.svg << 'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><circle cx="24" cy="24" r="20" fill="#4CAF50"/><path d="M24 14c-3.3 0-6 2.7-6 6v8c0 3.3 2.7 6 6 6s6-2.7 6-6v-8c0-3.3-2.7-6-6-6z" fill="white"/></svg>
EOF
    cp AppDir/talktype.svg AppDir/usr/share/icons/hicolor/scalable/talktype.svg
fi

# Create AppRun script
print_status "Creating AppRun script..."
cat > AppDir/AppRun << 'APPRUN_EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"

# Set up environment
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/lib:$LD_LIBRARY_PATH"
export PYTHONPATH="$HERE/usr/src:$PYTHONPATH"

# Set up audio and GTK
export PULSE_RUNTIME_PATH="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/pulse"
export XDG_DATA_DIRS="$HERE/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

# Check if ydotoold is running, if not start it (needed for text injection)
if ! pgrep -x "ydotoold" > /dev/null; then
    echo "Starting ydotoold daemon for text injection..."
    ydotoold &
    sleep 2
fi

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
APPRUN_EOF

chmod +x AppDir/AppRun

# Download appimagetool if not present
if [[ ! -f "appimagetool" ]]; then
    print_status "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O appimagetool
    chmod +x appimagetool
fi

# Create AppImage
print_status "Creating AppImage..."
ARCH=x86_64 ./appimagetool AppDir "TalkType-CPU-x86_64.AppImage"

if [[ -f "TalkType-CPU-x86_64.AppImage" ]]; then
    chmod +x TalkType-CPU-x86_64.AppImage
    SIZE=$(du -h TalkType-CPU-x86_64.AppImage | cut -f1)
    print_success "AppImage created successfully!"
    echo ""
    echo "📦 File: TalkType-CPU-x86_64.AppImage"
    echo "💾 Size: $SIZE"
    echo ""
    echo "✨ Features:"
    echo "   • CPU-only mode (works on all systems)"
    echo "   • Smart GPU detection on first run"
    echo "   • Offers CUDA download if NVIDIA GPU detected"
    echo "   • GPU management in Preferences > Advanced"
    echo ""
    echo "🚀 To test:"
    echo "   ./TalkType-CPU-x86_64.AppImage"
    echo ""
    echo "📋 To test preferences:"
    echo "   ./TalkType-CPU-x86_64.AppImage prefs"
else
    echo "❌ Failed to create AppImage"
    exit 1
fi

