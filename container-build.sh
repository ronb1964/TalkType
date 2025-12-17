#!/bin/bash
# This script runs INSIDE the Ubuntu 22.04 container
# It's called by build-release.sh

set -e

echo "📍 Inside Ubuntu 22.04 container (Python 3.10, glibc 2.35)"
echo "🔧 Installing build dependencies..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3.10 \
    python3.10-venv \
    python3-pip \
    python3-dbus \
    git \
    cmake \
    build-essential \
    wget \
    rsync \
    libgirepository1.0-dev \
    gobject-introspection \
    gir1.2-glib-2.0 \
    gir1.2-appindicator3-0.1 \
    python3-gi \
    python3-gi-cairo \
    python3-cairo \
    libcairo2-dev \
    pkg-config \
    file \
    scdoc \
    fuse \
    libfuse2 \
    wl-clipboard \
    > /dev/null 2>&1

echo "✅ Python version: $(python3 --version)"

# Get version from pyproject.toml
VERSION=$(grep -E "^version" pyproject.toml | sed 's/version = "\(.*\)"/\1/')
echo "✅ TalkType version: $VERSION"
echo ""

# Clean up old build artifacts
echo "🧹 Cleaning up old build artifacts..."
rm -rf AppDir /tmp/talktype-build-venv

# Install Poetry globally in container
echo "🐍 Installing Poetry..."
pip3 install -q poetry

# CRITICAL: Configure Poetry to create venv in /tmp, NOT in /build - which is the users project dir
poetry config virtualenvs.in-project false
poetry config virtualenvs.path /tmp/talktype-build-venv

# Clear any cached Poetry state
echo "🗑️  Clearing Poetry cache..."
rm -rf /tmp/.cache/pypoetry
export POETRY_CACHE_DIR=/tmp/poetry-cache

# Update lock file if pyproject.toml changed
echo "🔒 Updating lock file..."
poetry lock

# Install Python dependencies (fresh install, no cache)
echo "📚 Installing dependencies (this takes a few minutes)..."
poetry install --only main --no-root --no-cache

# Get the venv path from Poetry itself - extract first space-delimited field
# Use tr to convert spaces to tabs, then cut can use default tab delimiter
VENV_PATH=$(poetry env list --full-path 2>/dev/null | head -1 | tr " " "\t" | cut -f1)

echo ""
echo "   Poetry created venv at: $VENV_PATH"

# Verify venv was created and it's NOT in /build
if [[ "$VENV_PATH" == /build/* ]]; then
    echo "❌ CRITICAL ERROR: Poetry created venv inside /build/ - this would overwrite user's dev environment!"
    echo "   Venv path: $VENV_PATH"
    exit 1
fi

if [ -z "$VENV_PATH" ] || [ ! -d "$VENV_PATH" ]; then
    echo "❌ ERROR: Could not find Poetry venv"
    echo "   Expected path: $VENV_PATH"
    ls -la /tmp/talktype-build-venv/ 2>/dev/null || echo "Base directory /tmp/talktype-build-venv/ does not exist"
    exit 1
fi

echo "✅ Dependencies installed at: $VENV_PATH"
echo ""

# ============================================
# Build AppImage
# ============================================

echo "🏗️  Building AppImage..."

mkdir -p AppDir/usr/{bin,lib,src,share/applications,share/icons/hicolor/scalable,share/metainfo}

# Detect Python version from venv
PYTHON_VERSION=$($VENV_PATH/bin/python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "   Python version: $PYTHON_VERSION"

# Copy Python executable
cp -L $VENV_PATH/bin/python3 AppDir/usr/bin/python3
chmod +x AppDir/usr/bin/python3

# Bundle Python shared library
echo "   Bundling libpython..."
if [ -f "/usr/lib/x86_64-linux-gnu/libpython${PYTHON_VERSION}.so.1.0" ]; then
    cp "/usr/lib/x86_64-linux-gnu/libpython${PYTHON_VERSION}.so.1.0" AppDir/usr/lib/
else
    echo "❌ ERROR: Could not find libpython${PYTHON_VERSION}.so.1.0"
    exit 1
fi

# Copy Python standard library
echo "   Copying Python stdlib..."
mkdir -p "AppDir/usr/lib/python${PYTHON_VERSION}"
rsync -a --exclude='site-packages' --exclude='__pycache__' --exclude='*.pyc' \
    "/usr/lib/python${PYTHON_VERSION}/" "AppDir/usr/lib/python${PYTHON_VERSION}/"

# Copy Python packages (excluding large unnecessary ones)
echo "   Copying Python packages..."
mkdir -p "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages"

rsync -a \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='torch' \
    --exclude='torch-*' \
    --exclude='torchvision' \
    --exclude='torchvision-*' \
    --exclude='torchaudio' \
    --exclude='torchaudio-*' \
    --exclude='nvidia*' \
    --exclude='triton*' \
    --exclude='cusparselt' \
    --exclude='sympy' \
    --exclude='sympy-*' \
    --exclude='networkx' \
    --exclude='networkx-*' \
    --exclude='pip' \
    --exclude='setuptools' \
    --exclude='wheel' \
    "$VENV_PATH/lib/python${PYTHON_VERSION}/site-packages/" \
    "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/"

# Copy PyTorch (CPU-only - GPU acceleration uses CTranslate2's separate CUDA support)
echo "   Copying PyTorch (CPU-only)..."
VENV_TORCH="$VENV_PATH/lib/python${PYTHON_VERSION}/site-packages/torch"
if [ -d "$VENV_TORCH" ]; then
    echo "   Found PyTorch at $VENV_TORCH"
    cp -r "$VENV_TORCH" "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/"
    cp -r "$VENV_PATH/lib/python${PYTHON_VERSION}/site-packages/torch-"*.dist-info \
          "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
    # Report size to verify CPU-only (should be ~140MB, not ~1.7GB)
    TORCH_SIZE=$(du -sh "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/torch" | cut -f1)
    echo "   ✅ PyTorch size: $TORCH_SIZE (CPU-only)"
else
    echo "❌ ERROR: Could not find PyTorch installation at $VENV_TORCH"
    ls -la "$VENV_PATH/lib/python${PYTHON_VERSION}/site-packages/" | head -20
    exit 1
fi

# Copy system gi, cairo, and dbus Python packages (not available via pip on Ubuntu 22.04)
echo "   Copying system gi, cairo, and dbus packages..."

# Use Python -c to resolve paths (avoids nested heredoc issues)
GI_DIR=$(python3 -c "import gi, pathlib; print(pathlib.Path(gi.__file__).parent)")
CAIRO_DIR=$(python3 -c "import cairo, pathlib; print(pathlib.Path(cairo.__file__).parent)")
DBUS_DIR=$(python3 -c "import dbus, pathlib; print(pathlib.Path(dbus.__file__).parent)")
PYTHON_VERSION_STR=$(python3 -c "import sys; print(str(sys.version_info.major) + str(sys.version_info.minor))")
PYVER="${PYTHON_VERSION_STR:0:1}.${PYTHON_VERSION_STR:1}"
DEST="AppDir/usr/lib/python${PYVER}/site-packages"

echo "     Found gi at: $GI_DIR"
echo "     Found cairo at: $CAIRO_DIR"
echo "     Found dbus at: $DBUS_DIR"
echo "     Copying to: $DEST"

# Create destination directories
mkdir -p "$DEST/gi" "$DEST/cairo" "$DEST/dbus"

# Copy gi package completely
rsync -a "$GI_DIR/" "$DEST/gi/"
echo "     ✓ Copied gi package"

# Copy Cairo Python package
rsync -a "$CAIRO_DIR/" "$DEST/cairo/"
echo "     ✓ Copied cairo package"

# Copy D-Bus Python package
rsync -a "$DBUS_DIR/" "$DEST/dbus/"
echo "     ✓ Copied dbus package"

# CRITICAL: Copy _gi_cairo bridge module (PyGObject-Cairo integration)
# This provides the foreign struct converter for cairo.Context
if ls "$GI_DIR"/_gi_cairo*.so >/dev/null 2>&1; then
    cp -v "$GI_DIR"/_gi_cairo*.so "$DEST/gi/"
    echo "     ✓ Copied _gi_cairo module (PyGObject-Cairo bridge)"
else
    echo "     ⚠️  WARNING: _gi_cairo module not found - recording indicator may not work"
fi

# Copy D-Bus C bindings
if ls /usr/lib/python3/dist-packages/_dbus*.so >/dev/null 2>&1; then
    cp -v /usr/lib/python3/dist-packages/_dbus*.so "$DEST/"
    echo "     ✓ Copied _dbus C bindings"
elif ls "$DBUS_DIR"/../_dbus*.so >/dev/null 2>&1; then
    cp -v "$DBUS_DIR"/../_dbus*.so "$DEST/"
    echo "     ✓ Copied _dbus C bindings"
else
    echo "     ⚠️  WARNING: _dbus C bindings not found - GNOME extension may not work"
fi

# Copy Cairo C libraries
install -Dm755 /usr/lib/x86_64-linux-gnu/libcairo.so.2 AppDir/usr/lib/libcairo.so.2
install -Dm755 /usr/lib/x86_64-linux-gnu/libcairo-gobject.so.2 AppDir/usr/lib/libcairo-gobject.so.2
install -Dm755 /usr/lib/x86_64-linux-gnu/libpangocairo-1.0.so.0 AppDir/usr/lib/libpangocairo-1.0.so.0
echo "     ✓ Copied Cairo C libraries"

# Patch PyTorch for graceful handling (safety measure - CPU-only torch shouldn't need this)
echo "   Patching PyTorch (safety measure)..."
python3 /build/patch_pytorch.py "AppDir/usr/lib/python${PYTHON_VERSION}/site-packages/torch/__init__.py"

# Build ydotool
echo "   Building ydotool..."
cd /tmp
git clone -q https://github.com/ReimuNotMoe/ydotool.git
cd ydotool
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release .. > /dev/null 2>&1
make -j$(nproc) > /dev/null 2>&1
cp ydotool ydotoold /build/AppDir/usr/bin/
cd /build

# Bundle wl-clipboard for clipboard paste support
echo "📋 Bundling wl-clipboard..."
cp /usr/bin/wl-copy /usr/bin/wl-paste /build/AppDir/usr/bin/

# Bundle GTK3 and GObject Introspection
echo "   Bundling GTK3 libraries..."
cp /usr/lib/x86_64-linux-gnu/libgirepository-1.0.so.1 AppDir/usr/lib/
cp /usr/lib/x86_64-linux-gnu/libffi.so.* AppDir/usr/lib/

# Bundle Cairo libraries (needed for recording indicator)
echo "   Bundling Cairo libraries..."
cp /usr/lib/x86_64-linux-gnu/libcairo.so.2 AppDir/usr/lib/ 2>/dev/null || \
    echo "     ⚠️  Warning: libcairo.so.2 not found"
cp /usr/lib/x86_64-linux-gnu/libcairo-gobject.so.2 AppDir/usr/lib/ 2>/dev/null || \
    echo "     ⚠️  Warning: libcairo-gobject.so.2 not found"
echo "     ✓ Cairo libraries bundled"
mkdir -p AppDir/usr/lib/girepository-1.0

# Copy typelibs from both possible locations
cp /usr/lib/x86_64-linux-gnu/girepository-1.0/*.typelib AppDir/usr/lib/girepository-1.0/ 2>/dev/null || true
cp /usr/lib/girepository-1.0/*.typelib AppDir/usr/lib/girepository-1.0/ 2>/dev/null || true

# Verify AppIndicator3 typelib was copied
if [ ! -f "AppDir/usr/lib/girepository-1.0/AppIndicator3-0.1.typelib" ]; then
    echo "❌ ERROR: AppIndicator3 typelib not found after copy"
    echo "   Searched in:"
    echo "     /usr/lib/x86_64-linux-gnu/girepository-1.0/"
    echo "     /usr/lib/girepository-1.0/"
    exit 1
fi
echo "   ✅ AppIndicator3 typelib bundled successfully"

# Copy TalkType source
echo "   Copying TalkType source..."
cp -r src/talktype AppDir/usr/src/

# NOTE: GNOME extension is NOT bundled - it's downloaded from GitHub releases during onboarding
# This allows users to update the extension independently of the AppImage

# Create entry points
cat > AppDir/usr/bin/dictate-tray << 'EOF'
#!/bin/sh
DIR="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$DIR/../src:$DIR/../lib/python3.10/site-packages"
export LD_LIBRARY_PATH="$DIR/../lib:$LD_LIBRARY_PATH"
export GI_TYPELIB_PATH="$DIR/../lib/girepository-1.0"
exec "$DIR/python3" -m talktype.tray "$@"
EOF
chmod +x AppDir/usr/bin/dictate-tray

# Copy desktop files and icons
echo "   Adding desktop integration..."
cp io.github.ronb1964.TalkType.png AppDir/
cp io.github.ronb1964.TalkType.desktop AppDir/
cp io.github.ronb1964.TalkType.appdata.xml AppDir/usr/share/metainfo/

# Create AppRun
cat > AppDir/AppRun << 'EOF'
#!/bin/sh
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
export PYTHONPATH="${HERE}/usr/src:${HERE}/usr/lib/python3.10/site-packages"
export GI_TYPELIB_PATH="${HERE}/usr/lib/girepository-1.0"
export PYTHONHOME="${HERE}/usr"
# Force XWayland mode to enable recording indicator positioning on Wayland
export GDK_BACKEND=x11
# Disable HuggingFace XET downloads - they bypass progress tracking
export HF_HUB_DISABLE_XET=1
cd "$HOME"
if [ "$1" = "prefs" ]; then
    exec "${HERE}/usr/bin/python3" -m talktype.prefs
else
    exec "${HERE}/usr/bin/python3" -m talktype.tray "$@"
fi
EOF
chmod +x AppDir/AppRun

# Download and extract appimagetool - FUSE does not work in containers
echo "   Downloading appimagetool..."
if [ ! -d appimagetool-extracted ]; then
    wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool-x86_64.AppImage
    ./appimagetool-x86_64.AppImage --appimage-extract > /dev/null 2>&1
    mv squashfs-root appimagetool-extracted
fi

# Build AppImage using extracted appimagetool
echo "   Creating AppImage..."
ARCH=x86_64 ./appimagetool-extracted/AppRun --no-appstream AppDir "TalkType-v${VERSION}-x86_64.AppImage" > /dev/null 2>&1

# Fix ownership of AppImage output
if [ -n "$BUILD_USER" ]; then
    chown $BUILD_USER:$BUILD_GROUP /build/TalkType-v${VERSION}-x86_64.AppImage 2>/dev/null || true
fi

# Clean up build artifacts inside container
echo "   Cleaning up build artifacts..."
rm -rf AppDir

echo ""
echo "✅ Build complete! AppImage is ready."
echo "   Build artifacts cleaned up (AppDir/ removed)"
echo "   NOTE: .venv is NOT removed - this is the user's dev environment!"
