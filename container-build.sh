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
    gir1.2-ayatanaappindicator3-0.1 \
    libayatana-appindicator3-1 \
    libportaudio2 \
    patchelf \
    python3-gi \
    python3-gi-cairo \
    python3-cairo \
    libcairo2-dev \
    pkg-config \
    file \
    scdoc \
    fuse \
    libfuse2 \
    meson \
    ninja-build \
    libwayland-dev \
    wayland-protocols \
    zsync \
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

# PyTorch is intentionally NOT bundled (removed 2026-08-15). It was never used:
# inference is faster-whisper/CTranslate2, GPU uses cuda_helper's CUDA libs, and model
# downloads use huggingface_hub — all verified torch-free on CPU and GPU. The rsync
# excludes above still drop torch/torchvision/nvidia* defensively in case a dev venv
# happens to have them installed.

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

# Do NOT bundle the Cairo C libraries (libcairo, libcairo-gobject,
# libpangocairo). GTK needs them, so every desktop that can run TalkType has
# them. Bundled, Ubuntu 22.04's cairo 1.16 replaced the system's, and it can't
# draw the color emoji fonts newer distros ship (Fedora's Noto Color Emoji is
# COLRv1 only): every emoji in the app, the language flags included, was
# blank. The Python cairo package and _gi_cairo above are all that's needed.

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

# Bundle wl-clipboard for clipboard paste support. Built from source because
# Ubuntu 22.04 ships 2.0.0, and paste needs 2.3.0's wl-copy --sensitive: it
# keeps dictations out of clipboard managers' history (KDE's Klipper saved
# every one to disk, issue #7). Pinned to a release tag.
WL_CLIPBOARD_VERSION=v2.3.0
echo "📋 Building wl-clipboard $WL_CLIPBOARD_VERSION..."
rm -rf /tmp/wl-clipboard
git clone -q --depth 1 --branch "$WL_CLIPBOARD_VERSION" https://github.com/bugaevc/wl-clipboard /tmp/wl-clipboard
meson setup /tmp/wl-clipboard/build /tmp/wl-clipboard --buildtype=release > /dev/null
ninja -C /tmp/wl-clipboard/build > /dev/null
cp /tmp/wl-clipboard/build/src/wl-copy /tmp/wl-clipboard/build/src/wl-paste /build/AppDir/usr/bin/
/build/AppDir/usr/bin/wl-copy --help | grep -q -- --sensitive \
    || { echo "❌ bundled wl-copy has no --sensitive"; exit 1; }

# Bundle GTK3 and GObject Introspection
echo "   Bundling GTK3 libraries..."
cp /usr/lib/x86_64-linux-gnu/libgirepository-1.0.so.1 AppDir/usr/lib/
cp /usr/lib/x86_64-linux-gnu/libffi.so.* AppDir/usr/lib/

mkdir -p AppDir/usr/lib/girepository-1.0

# Copy typelibs from both possible locations. The `|| true` is deliberate here:
# only one of these paths exists on any given base image, so one copy is always
# expected to fail. The outcome is asserted below instead of the attempt.
cp /usr/lib/x86_64-linux-gnu/girepository-1.0/*.typelib AppDir/usr/lib/girepository-1.0/ 2>/dev/null || true
cp /usr/lib/girepository-1.0/*.typelib AppDir/usr/lib/girepository-1.0/ 2>/dev/null || true

# Verify every typelib the app imports UNGUARDED. Only AppIndicator3 used to be
# checked, so a missing Gtk, Gdk or GdkPixbuf would sail through the build and
# crash the app on launch with a GI error the user cannot act on.
#
# Typelibs behind a try/except are deliberately NOT listed: Notify (desktop
# notifications) and Atspi (password-field detection) are optional, are not
# bundled, and the code already degrades without them. Requiring them here
# would fail every build for features that are meant to be absent.
#
# tests/test_bundled_typelibs.py derives the unguarded set from the source and
# fails if this list drifts, so do not edit it by hand without running it.
REQUIRED_TYPELIBS=(
    "AyatanaAppIndicator3-0.1.typelib"
    "Gtk-3.0.typelib"
    "Gdk-3.0.typelib"
    "GdkPixbuf-2.0.typelib"
    "Gio-2.0.typelib"
)
MISSING_TYPELIBS=()
for _tl in "${REQUIRED_TYPELIBS[@]}"; do
    [ -f "AppDir/usr/lib/girepository-1.0/${_tl}" ] || MISSING_TYPELIBS+=("$_tl")
done
if [ ${#MISSING_TYPELIBS[@]} -ne 0 ]; then
    echo "❌ ERROR: required typelib(s) missing after copy: ${MISSING_TYPELIBS[*]}"
    echo "   Searched in:"
    echo "     /usr/lib/x86_64-linux-gnu/girepository-1.0/"
    echo "     /usr/lib/girepository-1.0/"
    echo "   The AppImage would build fine and then fail on launch."
    exit 1
fi
echo "   ✅ All ${#REQUIRED_TYPELIBS[@]} required typelibs bundled successfully"

# Bundle the tray icon library itself, not just its typelib. A typelib only
# describes a library; GI still dlopen()s the real .so from the system. On any
# system without libayatana-appindicator3 installed the tray crashed on launch
# with "Could not locate app_indicator_new" (AppImageHub's test, 2026-09-26).
# Its Ayatana/dbusmenu dependencies come along; GTK itself stays the system's.
echo "   Bundling tray icon library (libayatana-appindicator3)..."
APPINDICATOR_LIB=/usr/lib/x86_64-linux-gnu/libayatana-appindicator3.so.1
if [ ! -f "$APPINDICATOR_LIB" ]; then
    echo "❌ ERROR: $APPINDICATOR_LIB not found - the tray would crash wherever it isn't installed"
    exit 1
fi
cp -L "$APPINDICATOR_LIB" AppDir/usr/lib/
for _dep in $(ldd "$APPINDICATOR_LIB" | awk '/libayatana|libdbusmenu/ {print $3}'); do
    cp -L "$_dep" AppDir/usr/lib/
    echo "     ✓ $(basename "$_dep")"
done
# Every Ayatana/dbusmenu library the tray needs must now resolve from AppDir.
if LD_LIBRARY_PATH=AppDir/usr/lib ldd AppDir/usr/lib/libayatana-appindicator3.so.1 \
        | grep -E 'libayatana|libdbusmenu' | grep -qv 'AppDir/usr/lib'; then
    echo "❌ ERROR: some tray icon dependencies were not bundled:"
    LD_LIBRARY_PATH=AppDir/usr/lib ldd AppDir/usr/lib/libayatana-appindicator3.so.1 | grep -E 'libayatana|libdbusmenu'
    exit 1
fi
echo "   ✅ Tray icon library bundled"

# Bundle PortAudio (the microphone library) as a fallback. sounddevice looks it
# up with find_library(), which ignores LD_LIBRARY_PATH, so without a system
# libportaudio TalkType had no microphone (AppImageHub's test, 2026-09-26).
# talktype/__init__.py points find_library here only when the system has none.
#
# It lives in its own folder, NOT usr/lib: that folder is on LD_LIBRARY_PATH,
# and a bundled libjack there would override the system's (e.g. PipeWire's
# JACK) for a system PortAudio too. libjack and its libdb dependency are
# bundled because many desktops lack them; RUNPATH=$ORIGIN makes the bundled
# PortAudio find them. libasound stays the system's, as ALSA needs its config.
echo "   Bundling PortAudio fallback..."
PA_DIR=AppDir/usr/lib/portaudio
mkdir -p "$PA_DIR"
for _lib in libportaudio.so.2 libjack.so.0 libdb-5.3.so; do
    cp -L "/usr/lib/x86_64-linux-gnu/$_lib" "$PA_DIR/"
done
patchelf --set-rpath '$ORIGIN' "$PA_DIR/libportaudio.so.2" "$PA_DIR/libjack.so.0"
if ldd "$PA_DIR/libportaudio.so.2" | grep -E 'libjack|libdb' | grep -qv "$PA_DIR"; then
    echo "❌ ERROR: bundled PortAudio does not resolve its own libjack/libdb:"
    ldd "$PA_DIR/libportaudio.so.2"
    exit 1
fi
echo "   ✅ PortAudio fallback bundled"

# Copy TalkType source
echo "   Copying TalkType source..."
cp -r src/talktype AppDir/usr/src/
# Normalize source permissions so no owner-only file (e.g. a 0600 .py) rides into the
# bundle unreadable. The AppImage's FUSE mount hides this, but a .deb/.rpm built from the
# same tree installs real files and a 0600 module then fails to import for the user.
chmod -R a+rX AppDir/usr/src/talktype

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
# GDK_BACKEND is deliberately NOT exported here. The recording indicator needs
# XWayland to position itself, but the tray sets that for the dictation service
# alone (tray.py _launch_service). Setting it for the whole app breaks every GTK3
# dropdown: under XWayland a combo popup does not latch open on a plain click, so
# the first-run model picker and all Preferences combos become unusable.
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

# The Cairo C libraries stay out of the bundle (see "Do NOT bundle" above).
# Checked last, after every copy step. Fail the build if one got in: blank emoji is easy to miss.
for lib in libcairo.so.2 libcairo-gobject.so.2 libpangocairo-1.0.so.0; do
    if [ -e "AppDir/usr/lib/$lib" ]; then
        echo "     ❌ $lib is bundled; it hides the system's and blanks every emoji"
        exit 1
    fi
done

# Download and extract appimagetool - FUSE does not work in containers.
# This is the current tool from github.com/AppImage/appimagetool, NOT the
# retired AppImageKit one. The old tool embedded a runtime that needs libfuse2
# on the user's system; Ubuntu 26.04 no longer ships it, so the AppImage (and
# the menu/autostart entries pointing at it) silently failed to start there.
# The new tool fetches the static type2 runtime, which needs no libfuse2.
# The cache folder has a new name so an old extracted AppImageKit tool left in
# the project directory can never be picked up by mistake.
echo "   Downloading appimagetool..."
if [ ! -d appimagetool-type2-extracted ]; then
    rm -rf squashfs-root
    wget -q -O appimagetool-type2-x86_64.AppImage \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool-type2-x86_64.AppImage
    ./appimagetool-type2-x86_64.AppImage --appimage-extract > /dev/null 2>&1
    mv squashfs-root appimagetool-type2-extracted
    rm -f appimagetool-type2-x86_64.AppImage
fi

# Update information, so AppImageUpdate and similar tools can update TalkType
# by downloading only the changed parts. It points at the .zsync file in the
# LATEST GitHub release, so every release must upload the .zsync that
# appimagetool writes next to the AppImage (zsyncmake, from the zsync package).
# AppImageHub's test warned about its absence (AppImage/appimage.github.io#4598).
# TalkType's own "Check for Updates" doesn't use this; it is for outside tools.
UPDATE_INFO="gh-releases-zsync|ronb1964|TalkType|latest|TalkType-*x86_64.AppImage.zsync"
ZSYNC_FILE="TalkType-v${VERSION}-x86_64.AppImage.zsync"
rm -f "$ZSYNC_FILE"

# Build AppImage using extracted appimagetool (it downloads the runtime itself)
echo "   Creating AppImage..."
ARCH=x86_64 ./appimagetool-type2-extracted/AppRun --no-appstream -u "$UPDATE_INFO" \
    AppDir "TalkType-v${VERSION}-x86_64.AppImage" > /tmp/appimagetool.log 2>&1 \
    || { echo "❌ ERROR: appimagetool failed:"; cat /tmp/appimagetool.log; exit 1; }
if [ ! -f "$ZSYNC_FILE" ]; then
    echo "❌ ERROR: $ZSYNC_FILE was not created, so the embedded update information"
    echo "   would point at a file the release doesn't have. appimagetool said:"
    cat /tmp/appimagetool.log
    exit 1
fi
echo "   ✅ Update information embedded, $ZSYNC_FILE written"

# Fix ownership of AppImage output
if [ -n "$BUILD_USER" ]; then
    # Not fatal — the AppImage exists either way — but if this fails the file is
    # left owned by root and the host build script cannot copy or delete it
    # without sudo, which is worth saying out loud rather than hiding.
    chown $BUILD_USER:$BUILD_GROUP /build/TalkType-v${VERSION}-x86_64.AppImage \
        "/build/$ZSYNC_FILE" 2>/dev/null \
        || echo "   ⚠️  Warning: could not chown the AppImage to $BUILD_USER:$BUILD_GROUP (it stays root-owned)"
fi

# Clean up build artifacts inside container
echo "   Cleaning up build artifacts..."
rm -rf AppDir

echo ""
echo "✅ Build complete! AppImage is ready."
echo "   Build artifacts cleaned up (AppDir/ removed)"
echo "   NOTE: .venv is NOT removed - this is the user's dev environment!"
