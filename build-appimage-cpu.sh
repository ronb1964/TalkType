#!/bin/bash
set -e

# CPU-Only AppImage Build Script for TalkType
# This creates a smaller AppImage without CUDA libraries
# GPU detection and CUDA download offer is handled at runtime

echo "🚀 Building TalkType AppImage"
echo "======================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

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

# Get version from pyproject.toml
VERSION=$(grep -E "^version" pyproject.toml | sed 's/version = "\(.*\)"/\1/')

# Clean up old build
print_status "Cleaning up old build..."
rm -rf AppDir
rm -f TalkType-*.AppImage
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

# Bundle Python shared library (CRITICAL for AppImage to work)
print_status "Bundling Python shared library..."
mkdir -p AppDir/usr/lib
if [ -f "/lib64/libpython${PYTHON_VERSION}.so.1.0" ]; then
    cp "/lib64/libpython${PYTHON_VERSION}.so.1.0" AppDir/usr/lib/
    print_status "Copied libpython${PYTHON_VERSION}.so.1.0 from /lib64"
elif [ -f "/usr/lib64/libpython${PYTHON_VERSION}.so.1.0" ]; then
    cp "/usr/lib64/libpython${PYTHON_VERSION}.so.1.0" AppDir/usr/lib/
    print_status "Copied libpython${PYTHON_VERSION}.so.1.0 from /usr/lib64"
elif [ -f "/usr/lib/x86_64-linux-gnu/libpython${PYTHON_VERSION}.so.1.0" ]; then
    cp "/usr/lib/x86_64-linux-gnu/libpython${PYTHON_VERSION}.so.1.0" AppDir/usr/lib/
    print_status "Copied libpython${PYTHON_VERSION}.so.1.0 from /usr/lib/x86_64-linux-gnu"
else
    print_error "Could not find libpython${PYTHON_VERSION}.so.1.0!"
    exit 1
fi

# Copy Python standard library (encodings, os, etc.)
print_status "Copying Python standard library..."
mkdir -p "AppDir/usr/lib/python${PYTHON_VERSION}"
if [ -d "/usr/lib/python${PYTHON_VERSION}" ]; then
    rsync -a --exclude='site-packages' --exclude='__pycache__' --exclude='*.pyc' \
        "/usr/lib/python${PYTHON_VERSION}/" "AppDir/usr/lib/python${PYTHON_VERSION}/"
    print_status "Copied Python stdlib from /usr/lib/python${PYTHON_VERSION}"
elif [ -d "/usr/lib64/python${PYTHON_VERSION}" ]; then
    rsync -a --exclude='site-packages' --exclude='__pycache__' --exclude='*.pyc' \
        "/usr/lib64/python${PYTHON_VERSION}/" "AppDir/usr/lib/python${PYTHON_VERSION}/"
    print_status "Copied Python stdlib from /usr/lib64/python${PYTHON_VERSION}"
else
    print_error "Could not find Python standard library!"
    exit 1
fi

# Create lib directory structure
mkdir -p "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages"

# Copy Python packages EXCEPT PyTorch and unnecessary packages
print_status "Copying Python packages (excluding PyTorch and unnecessary packages)..."
rsync -a --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='torch' \
    --exclude='torch-*' \
    --exclude='torchvision' \
    --exclude='torchvision-*' \
    --exclude='torchvision.libs' \
    --exclude='torchaudio' \
    --exclude='torchaudio-*' \
    --exclude='nvidia/' \
    --exclude='nvidia_*' \
    --exclude='cuda*' \
    --exclude='triton' \
    --exclude='triton-*' \
    --exclude='cusparselt' \
    --exclude='sympy' \
    --exclude='sympy-*' \
    --exclude='networkx' \
    --exclude='networkx-*' \
    --exclude='pip' \
    --exclude='pip-*' \
    --exclude='setuptools' \
    --exclude='setuptools-*' \
    --exclude='wheel' \
    --exclude='wheel-*' \
    ".venv/lib/python${PYTHON_VERSION}/site-packages/" \
    "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/"

# Also copy from lib64 if it exists (some packages like PyAV install there)
if [ -d ".venv/lib64/python${PYTHON_VERSION}/site-packages" ]; then
    print_status "Copying packages from lib64 (excluding PyTorch and unnecessary packages)..."
    rsync -a --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='*.pyo' \
        --exclude='torch' \
        --exclude='torch-*' \
        --exclude='torchvision' \
        --exclude='torchvision-*' \
        --exclude='torchvision.libs' \
        --exclude='torchaudio' \
        --exclude='torchaudio-*' \
        --exclude='nvidia/' \
        --exclude='nvidia_*' \
        --exclude='triton' \
        --exclude='triton-*' \
        --exclude='cusparselt' \
        --exclude='sympy' \
        --exclude='sympy-*' \
        --exclude='networkx' \
        --exclude='networkx-*' \
        --exclude='pip' \
        --exclude='pip-*' \
        ".venv/lib64/python${PYTHON_VERSION}/site-packages/" \
        "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/"
fi

# Copy CUDA-enabled PyTorch from venv (full GPU support)
# NOTE: torchvision and torchaudio are NOT copied - they're not needed by faster-whisper
print_status "Copying CUDA-enabled PyTorch from venv..."
# PyTorch is installed in lib64, so copy from there
if [ -d ".venv/lib64/python${PYTHON_VERSION}/site-packages/torch" ]; then
    cp -r ".venv/lib64/python${PYTHON_VERSION}/site-packages/torch" \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/"
    cp -r ".venv/lib64/python${PYTHON_VERSION}/site-packages/torch-"*.dist-info \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
    print_status "PyTorch CUDA version copied from lib64 (torchvision/torchaudio excluded)"
else
    print_warning "PyTorch not found in lib64, trying lib..."
    cp -r ".venv/lib/python${PYTHON_VERSION}/site-packages/torch" \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
fi

# Patch PyTorch's __init__.py to gracefully handle missing CUDA libraries
# This allows CPU mode to work without crashes while preserving GPU support
print_status "Patching PyTorch to gracefully handle missing CUDA libraries..."
TORCH_INIT="AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/torch/__init__.py"

# Add a graceful fallback to _preload_cuda_deps function
python3 -c "
import re

torch_init_path = '${TORCH_INIT}'

with open(torch_init_path, 'r') as f:
    content = f.read()

# Find and wrap the _preload_cuda_deps function to catch exceptions
# Replace the ValueError raise with a warning and continue
old_pattern = r'raise ValueError\(f\"{lib_name} not found in the system path'
new_code = 'import warnings; warnings.warn(f\"{lib_name} not found in the system path'

content = re.sub(old_pattern, new_code, content)

# Also wrap the ctypes.CDLL call in _load_global_deps with try/except
old_ctypes = r'(\s+)(ctypes\.CDLL\(global_deps_lib_path, mode=ctypes\.RTLD_GLOBAL\))'
new_ctypes = r'\1try:\n\1    \2\n\1except (OSError, FileNotFoundError) as e:\n\1    import warnings\n\1    warnings.warn(f\"Could not load CUDA library: {e}\")\n\1    return'

content = re.sub(old_ctypes, new_ctypes, content)

with open(torch_init_path, 'w') as f:
    f.write(content)

print('✓ PyTorch patched successfully')
"

print_status "PyTorch now supports both CPU-only systems and GPU systems with downloaded CUDA"

# Strip unnecessary PyTorch files to reduce AppImage size
print_status "Stripping unnecessary PyTorch files..."
TORCH_DIR="AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/torch"

# Remove development and training components (not needed for inference)
rm -rf "${TORCH_DIR}/include"        # Development headers (50 MB)
rm -rf "${TORCH_DIR}/testing"        # Testing files (4.8 MB)
rm -rf "${TORCH_DIR}/bin"            # Binary tools (11 MB)
rm -rf "${TORCH_DIR}/distributed"    # Multi-GPU training (4.1 MB)
rm -rf "${TORCH_DIR}/onnx"           # ONNX export (1.9 MB)
rm -rf "${TORCH_DIR}/fx"             # FX graph mode (1.7 MB)
rm -rf "${TORCH_DIR}/ao"             # Quantization tools (2.5 MB)
rm -rf "${TORCH_DIR}/_inductor"      # Compilation backend (5.1 MB)
rm -rf "${TORCH_DIR}/_dynamo"        # Dynamic compilation (2.4 MB)

# Remove type stub files (save a few MB)
find "${TORCH_DIR}" -name "*.pyi" -delete 2>/dev/null || true

# Remove Python cache files from all packages
find "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages" -name "*.pyc" -delete 2>/dev/null || true
find "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages" -name "*.pyo" -delete 2>/dev/null || true

print_status "Stripped ~85 MB of unnecessary files"

# Clean cached bytecode from source to ensure latest code is used
print_status "Cleaning cached Python bytecode..."
find src -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find src -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

# Copy TalkType source code (exclude cached bytecode)
print_status "Copying TalkType source code..."
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' src/ AppDir/usr/src/

# Bundle ydotool for text injection (AppImage MUST be self-contained)
print_status "Building ydotool from source with static linking for maximum compatibility..."
YDOTOOL_BUILD_DIR=$(mktemp -d)
PROJECT_DIR=$(pwd)

if git clone --depth 1 https://github.com/ReimuNotMoe/ydotool.git "$YDOTOOL_BUILD_DIR" 2>/dev/null; then
    cd "$YDOTOOL_BUILD_DIR"

    # Build with static linking to avoid glibc issues (skip docs build)
    if mkdir build && cd build && cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBUILD_DOCS=OFF .. && make; then
        # Copy binaries and verify they work
        if [ -f "ydotool" ] && [ -f "ydotoold" ]; then
            cp ydotool "$PROJECT_DIR/AppDir/usr/bin/"
            cp ydotoold "$PROJECT_DIR/AppDir/usr/bin/"
            cd "$PROJECT_DIR"
            rm -rf "$YDOTOOL_BUILD_DIR"
            print_status "ydotool built and bundled successfully"
        else
            cd "$PROJECT_DIR"
            rm -rf "$YDOTOOL_BUILD_DIR"
            print_error "Failed to build ydotool binaries"
            exit 1
        fi
    else
        cd "$PROJECT_DIR"
        rm -rf "$YDOTOOL_BUILD_DIR"
        print_error "Failed to compile ydotool"
        exit 1
    fi
else
    rm -rf "$YDOTOOL_BUILD_DIR"
    print_error "Failed to download ydotool source"
    exit 1
fi

# Copy entry point scripts
print_status "Creating entry point scripts..."
cat > AppDir/usr/bin/dictate << EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${BASH_SOURCE[0]}")")"
export PYTHONPATH="\${HERE}/../lib/python${PYTHON_VERSION}/site-packages:\${HERE}/../src:\${PYTHONPATH}"

# Add CUDA library paths if they exist (downloaded by user)
CUDA_BASE="\${HOME}/.local/share/TalkType/cuda"
if [ -d "\${CUDA_BASE}" ]; then
    export LD_LIBRARY_PATH="\${CUDA_BASE}/lib:\${CUDA_BASE}/lib64:\${HERE}/../lib:\${LD_LIBRARY_PATH}"

    # Preload critical CUDA libraries to help PyTorch find them
    if [ -f "\${CUDA_BASE}/lib64/libcudart.so.12" ]; then
        export LD_PRELOAD="\${CUDA_BASE}/lib64/libcudart.so.12:\${LD_PRELOAD}"
    fi
    if [ -f "\${CUDA_BASE}/lib64/libcublas.so.12" ]; then
        export LD_PRELOAD="\${CUDA_BASE}/lib64/libcublas.so.12:\${LD_PRELOAD}"
    fi
else
    export LD_LIBRARY_PATH="\${HERE}/../lib:\${LD_LIBRARY_PATH}"
fi

exec "\${HERE}/python3" -m talktype.app "\$@"
EOF

cat > AppDir/usr/bin/dictate-tray << EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${BASH_SOURCE[0]}")")"
export PYTHONPATH="\${HERE}/../lib/python${PYTHON_VERSION}/site-packages:\${HERE}/../src:\${PYTHONPATH}"

# Add CUDA library paths if they exist (downloaded by user)
CUDA_BASE="\${HOME}/.local/share/TalkType/cuda"
if [ -d "\${CUDA_BASE}" ]; then
    export LD_LIBRARY_PATH="\${CUDA_BASE}/lib:\${CUDA_BASE}/lib64:\${HERE}/../lib:\${LD_LIBRARY_PATH}"
else
    export LD_LIBRARY_PATH="\${HERE}/../lib:\${LD_LIBRARY_PATH}"
fi

exec "\${HERE}/python3" -m talktype.tray "\$@"
EOF

cat > AppDir/usr/bin/dictate-prefs << EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${BASH_SOURCE[0]}")")"
export PYTHONPATH="\${HERE}/../lib/python${PYTHON_VERSION}/site-packages:\${HERE}/../src:\${PYTHONPATH}"

# Add CUDA library paths if they exist (downloaded by user)
CUDA_BASE="\${HOME}/.local/share/TalkType/cuda"
if [ -d "\${CUDA_BASE}" ]; then
    export LD_LIBRARY_PATH="\${CUDA_BASE}/lib:\${CUDA_BASE}/lib64:\${HERE}/../lib:\${LD_LIBRARY_PATH}"
else
    export LD_LIBRARY_PATH="\${HERE}/../lib:\${LD_LIBRARY_PATH}"
fi

exec "\${HERE}/python3" -m talktype.prefs "\$@"
EOF

chmod +x AppDir/usr/bin/dictate*

# Copy desktop file, icon, and AppStream metadata
# IMPORTANT: The official icon is icons/TT_retro_square_light.svg
# See ICON_DOCUMENTATION.md for details - DO NOT change the icon!
print_status "Copying desktop files and icons..."

# Use proper AppStream ID for AppImageHub compliance
cp io.github.ronb1964.TalkType.desktop AppDir/io.github.ronb1964.TalkType.desktop

# Copy icon - AppImageHub requires PNG format in AppDir root
if [[ -f "io.github.ronb1964.TalkType.png" ]]; then
    # Copy PNG icon to AppDir root (required by AppImageHub)
    cp io.github.ronb1964.TalkType.png AppDir/io.github.ronb1964.TalkType.png
    cp io.github.ronb1964.TalkType.png AppDir/.DirIcon

    # Copy PNG to icon hierarchy
    mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps
    cp io.github.ronb1964.TalkType.png AppDir/usr/share/icons/hicolor/256x256/apps/io.github.ronb1964.TalkType.png
    print_status "PNG icon copied"
else
    print_warning "Icon file io.github.ronb1964.TalkType.png not found"
fi

# Also copy SVG for scalability
if [[ -f "io.github.ronb1964.TalkType.svg" ]]; then
    mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
    cp io.github.ronb1964.TalkType.svg AppDir/usr/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg
fi

# Copy AppStream metadata
if [[ -f "io.github.ronb1964.TalkType.appdata.xml" ]]; then
    mkdir -p AppDir/usr/share/metainfo
    cp io.github.ronb1964.TalkType.appdata.xml AppDir/usr/share/metainfo/
    print_status "AppStream metadata included"
else
    print_warning "AppStream metadata file not found"
fi

# Create AppRun script
print_status "Creating AppRun script..."
cat > AppDir/AppRun << APPRUN_EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"

# Set up environment
export PATH="\$HERE/usr/bin:\$PATH"
export PYTHONPATH="\$HERE/usr/lib/python${PYTHON_VERSION}/site-packages:\$HERE/usr/src:\$PYTHONPATH"

# Add CUDA library paths if they exist (downloaded by user)
CUDA_BASE="\${HOME}/.local/share/TalkType/cuda"
if [ -d "\${CUDA_BASE}" ]; then
    export LD_LIBRARY_PATH="\${CUDA_BASE}/lib:\${CUDA_BASE}/lib64:\$HERE/usr/lib:\$LD_LIBRARY_PATH"
else
    export LD_LIBRARY_PATH="\$HERE/usr/lib:\$LD_LIBRARY_PATH"
fi

# Set up audio and GTK
export PULSE_RUNTIME_PATH="\${XDG_RUNTIME_DIR:-/run/user/\$(id -u)}/pulse"
export XDG_DATA_DIRS="\$HERE/usr/share:\${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

# Check if ydotoold is running, if not start it (needed for text injection)
if ! pgrep -x "ydotoold" > /dev/null 2>&1; then
    echo "Starting ydotoold daemon for text injection..."
    if ydotoold 2>/dev/null &
    then
        sleep 2
        echo "ydotoold started successfully"
    else
        echo "Warning: Failed to start ydotoold - text injection may not work"
        echo "You may need to start ydotoold manually or install it system-wide"
    fi
fi

# Parse arguments
case "\${1:-tray}" in
    "tray"|"")
        exec "\$HERE/usr/bin/dictate-tray" "\${@:2}"
        ;;
    "prefs"|"preferences")
        exec "\$HERE/usr/bin/dictate-prefs" "\${@:2}"
        ;;
    "dictate"|"service")
        exec "\$HERE/usr/bin/dictate" "\${@:2}"
        ;;
    "--help"|"-h")
        echo "TalkType - AI-powered dictation for Wayland"
        echo ""
        echo "Usage:"
        echo "  \$0 [tray]         Start system tray (default)"
        echo "  \$0 prefs          Open preferences window"
        echo "  \$0 dictate        Run dictation service directly"
        echo "  \$0 --help         Show this help"
        echo ""
        echo "Default action: Start system tray"
        ;;
    *)
        exec "\$HERE/usr/bin/dictate-tray" "\$@"
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

# Create AppImage with update information for AppImageHub
print_status "Creating AppImage..."
APPIMAGE_NAME="TalkType-v${VERSION}-x86_64.AppImage"
# Add update information for AppImageHub: gh-releases-zsync|user|repo|latest|AppImage-*.AppImage.zsync
UPDATE_INFO="gh-releases-zsync|ronb1964|TalkType|latest|TalkType-*-x86_64.AppImage.zsync"
ARCH=x86_64 ./appimagetool --no-appstream --updateinformation "$UPDATE_INFO" AppDir "$APPIMAGE_NAME"

if [[ -f "$APPIMAGE_NAME" ]]; then
    chmod +x "$APPIMAGE_NAME"
    SIZE=$(du -h "$APPIMAGE_NAME" | cut -f1)
    print_success "AppImage created successfully!"
    echo ""
    echo "📦 File: $APPIMAGE_NAME"
    echo "💾 Size: $SIZE"
    echo "🔖 Version: $VERSION"
    echo ""
    echo "✨ Features:"
    echo "   • Works on all systems (CPU mode)"
    echo "   • Smart GPU detection on first run"
    echo "   • Offers CUDA download if NVIDIA GPU detected"
    echo "   • GPU management in Preferences > Advanced"
    echo ""
    echo "🚀 To test:"
    echo "   ./$APPIMAGE_NAME"
    echo ""
    echo "📋 To test preferences:"
    echo "   ./$APPIMAGE_NAME prefs"
else
    echo "❌ Failed to create AppImage"
    exit 1
fi

