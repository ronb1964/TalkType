#!/bin/bash
set -e

# Manual AppImage Build Script for Fedora/Nobara
# Since appimage-builder is designed for Ubuntu/Debian, we'll build manually

echo "🔧 Manual TalkType AppImage Builder (Fedora/Nobara Compatible)"
echo "=============================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]] || [[ ! -d "src/ron_dictation" ]]; then
    print_error "Must be run from TalkType project root directory"
    exit 1
fi

# Stop services first
print_status "Stopping TalkType services..."
systemctl --user stop ron-dictation.service 2>/dev/null || true
pkill -f "dictate-tray" 2>/dev/null || true
pkill -f "ron_dictation" 2>/dev/null || true
sleep 2

# Clean and create AppDir
print_status "Setting up AppDir structure..."
rm -rf AppDir/usr AppDir/lib AppDir/bin AppDir/python3* 2>/dev/null || true
mkdir -p AppDir/usr/{bin,lib,lib64,share/applications,share/icons/hicolor/scalable/apps}

# Copy Python executable and libraries
print_status "Copying Python runtime..."
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_EXEC=$(which python3)

# Copy Python executable
cp "$PYTHON_EXEC" AppDir/usr/bin/

# Find and copy Python libraries
PYTHON_LIB_DIR="/usr/lib64/python${PYTHON_VERSION}"
if [[ -d "$PYTHON_LIB_DIR" ]]; then
    print_status "Copying Python $PYTHON_VERSION libraries..."
    cp -r "$PYTHON_LIB_DIR" AppDir/usr/lib64/
else
    print_error "Python library directory not found: $PYTHON_LIB_DIR"
    exit 1
fi

# Also copy from /usr/lib if it exists
PYTHON_LIB_DIR32="/usr/lib/python${PYTHON_VERSION}"
if [[ -d "$PYTHON_LIB_DIR32" ]]; then
    mkdir -p AppDir/usr/lib
    cp -r "$PYTHON_LIB_DIR32" AppDir/usr/lib/
fi

# Create virtual environment inside AppDir and install dependencies
print_status "Installing Python dependencies..."
APPDIR_PATH="$PWD/AppDir/usr"
cd AppDir/usr
export PYTHONPATH="$PWD/lib64/python${PYTHON_VERSION}/site-packages:$PWD/lib/python${PYTHON_VERSION}/site-packages"

# Install dependencies using the copied python3 executable
./bin/python3 -m pip install --target="lib64/python${PYTHON_VERSION}/site-packages" \
    faster-whisper sounddevice evdev numpy pyperclip toml

print_status "Copying TalkType source code..."
# Copy our source code
mkdir -p src
cp -r ../../src/* src/

print_status "Creating launcher scripts..."
# Create the main launcher scripts
cat > bin/dictate-tray << EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")/.."
export PYTHONPATH="\$HERE/lib64/python${PYTHON_VERSION}/site-packages:\$HERE/lib/python${PYTHON_VERSION}/site-packages:\$HERE/src:\$PYTHONPATH"
export LD_LIBRARY_PATH="\$HERE/lib64:\$HERE/lib:\$LD_LIBRARY_PATH"
exec "\$HERE/bin/python3" -c "
import sys
sys.path.insert(0, '\$HERE/src')
from src.ron_dictation.tray import main
main()
" "\$@"
EOF

cat > bin/dictate-prefs << EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")/.."
export PYTHONPATH="\$HERE/lib64/python${PYTHON_VERSION}/site-packages:\$HERE/lib/python${PYTHON_VERSION}/site-packages:\$HERE/src:\$PYTHONPATH"
export LD_LIBRARY_PATH="\$HERE/lib64:\$HERE/lib:\$LD_LIBRARY_PATH"
exec "\$HERE/bin/python3" -c "
import sys
sys.path.insert(0, '\$HERE/src')
from src.ron_dictation.prefs import main
main()
" "\$@"
EOF

cat > bin/dictate << EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")/.."
export PYTHONPATH="\$HERE/lib64/python${PYTHON_VERSION}/site-packages:\$HERE/lib/python${PYTHON_VERSION}/site-packages:\$HERE/src:\$PYTHONPATH"
export LD_LIBRARY_PATH="\$HERE/lib64:\$HERE/lib:\$LD_LIBRARY_PATH"
exec "\$HERE/bin/python3" -c "
import sys
sys.path.insert(0, '\$HERE/src')
from src.ron_dictation.app import main
main()
" "\$@"
EOF

chmod +x bin/dictate*

# Go back to project root
cd ../..

print_status "Testing Python environment in AppDir..."
if AppDir/usr/bin/python3 -c "import sys; print('Python works:', sys.version)" 2>/dev/null; then
    print_success "Python runtime is working"
else
    print_error "Python runtime test failed"
    exit 1
fi

print_status "Testing TalkType imports..."
if AppDir/usr/bin/dictate-tray --help >/dev/null 2>&1; then
    print_success "TalkType imports are working"
else
    print_error "TalkType import test failed - checking dependencies..."
    # Try to run and see what's missing
    AppDir/usr/bin/dictate-tray --help 2>&1 | head -10
fi

print_status "Creating AppImage with appimagetool..."
if [[ -f "appimagetool" ]]; then
    ./appimagetool AppDir TalkType-x86_64.AppImage
    if [[ -f "TalkType-x86_64.AppImage" ]]; then
        chmod +x TalkType-x86_64.AppImage
        print_success "AppImage created: TalkType-x86_64.AppImage"
        
        # Quick test
        if ./TalkType-x86_64.AppImage --help >/dev/null 2>&1; then
            print_success "AppImage appears to be working!"
        else
            print_error "AppImage test failed"
        fi
    else
        print_error "AppImage creation failed"
        exit 1
    fi
else
    print_error "appimagetool not found"
    exit 1
fi

print_status "Cleaning up and restoring services..."
systemctl --user start ron-dictation.service 2>/dev/null || true

print_success "Manual AppImage build complete!"
echo "📁 Generated: TalkType-x86_64.AppImage"
echo "🧪 Test with: ./TalkType-x86_64.AppImage tray"
