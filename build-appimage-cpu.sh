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

# Create lib directory structure
mkdir -p "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages"

# Copy Python packages EXCEPT PyTorch and unnecessary packages
print_status "Copying Python packages (excluding PyTorch and unnecessary packages)..."
rsync -a --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='torch' \
    --exclude='torch-*' \
    --exclude='nvidia' \
    --exclude='nvidia-*' \
    --exclude='cuda*' \
    --exclude='triton' \
    --exclude='triton-*' \
    --exclude='cusparselt' \
    --exclude='nvidia_cusparselt*' \
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
        --exclude='triton' \
        --exclude='triton-*' \
        --exclude='cusparselt' \
        --exclude='nvidia_cusparselt*' \
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
print_status "Copying CUDA-enabled PyTorch from venv..."
# PyTorch is installed in lib64, so copy from there
if [ -d ".venv/lib64/python${PYTHON_VERSION}/site-packages/torch" ]; then
    cp -r ".venv/lib64/python${PYTHON_VERSION}/site-packages/torch" \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/"
    cp -r ".venv/lib64/python${PYTHON_VERSION}/site-packages/torch-"*.dist-info \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
    cp -r ".venv/lib64/python${PYTHON_VERSION}/site-packages/torchvision" \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
    cp -r ".venv/lib64/python${PYTHON_VERSION}/site-packages/torchvision-"*.dist-info \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
    cp -r ".venv/lib64/python${PYTHON_VERSION}/site-packages/torchaudio" \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
    cp -r ".venv/lib64/python${PYTHON_VERSION}/site-packages/torchaudio-"*.dist-info \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
    cp -r ".venv/lib64/python${PYTHON_VERSION}/site-packages/torchvision.libs" \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
    print_status "PyTorch CUDA version copied from lib64"
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

# Remove development headers (50 MB)
rm -rf "${TORCH_DIR}/include"

# Remove testing files (4.8 MB)
rm -rf "${TORCH_DIR}/testing"

# Remove binary tools (11 MB) - only needed for development
rm -rf "${TORCH_DIR}/bin"

# Remove distributed training if present (4.6 MB) - not needed for single-user dictation
# Keep it commented out for now in case users want multi-GPU in future
# rm -rf "${TORCH_DIR}/distributed"

# Remove type stub files (save a few MB)
find "${TORCH_DIR}" -name "*.pyi" -delete 2>/dev/null || true

# Remove Python cache files
find "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages" -name "*.pyc" -delete 2>/dev/null || true
find "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages" -name "*.pyo" -delete 2>/dev/null || true

print_status "Stripped ~65 MB of unnecessary files"

# Copy TalkType source code
print_status "Copying TalkType source code..."
cp -r src AppDir/usr/

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
ln -sf io.github.ronb1964.TalkType.desktop AppDir/talktype.desktop  # Backwards compatibility

# Copy icon
if [[ -f "io.github.ronb1964.TalkType.svg" ]]; then
    cp io.github.ronb1964.TalkType.svg AppDir/io.github.ronb1964.TalkType.svg
    cp io.github.ronb1964.TalkType.svg AppDir/.DirIcon
    mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
    cp io.github.ronb1964.TalkType.svg AppDir/usr/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg
else
    print_warning "Icon file io.github.ronb1964.TalkType.svg not found"
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
if ! pgrep -x "ydotoold" > /dev/null; then
    echo "Starting ydotoold daemon for text injection..."
    ydotoold &
    sleep 2
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

# Create AppImage (skip AppStream validation for now as URLs aren't reachable during build)
print_status "Creating AppImage..."
APPIMAGE_NAME="TalkType-v${VERSION}-x86_64.AppImage"
ARCH=x86_64 ./appimagetool --no-appstream AppDir "$APPIMAGE_NAME"

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

