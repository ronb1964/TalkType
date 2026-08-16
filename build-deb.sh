#!/bin/bash
# TalkType .deb Build Script
# ==========================
# Repackages the release AppImage into a Debian/Ubuntu .deb.
#
# WHY this reuses the AppImage instead of building from scratch:
#   ./build-release.sh already assembles a fully self-contained runtime (its own
#   Python, GTK bindings, faster-whisper/CTranslate2, ydotool, wl-clipboard) inside
#   an Ubuntu 22.04 container for wide glibc compatibility. That same tree is exactly
#   what a .deb needs — so we extract the finished AppImage and wrap it as a .deb
#   rather than maintaining a second, divergent build. Run build-release.sh FIRST.
#
# Layout produced:
#   /opt/talktype/            <- the whole extracted AppImage tree (AppRun + usr/)
#   /usr/bin/talktype         <- tiny launcher: exec /opt/talktype/AppRun "$@"
#   /usr/share/applications/  <- desktop entry (Exec=talktype tray)
#   /usr/share/pixmaps/       <- icon
#
# System deps are DECLARED (not bundled): the bundle relies on the host's GTK stack.
#   libgtk-3-0, libayatana-appindicator3-1 (tray), libportaudio2 (mic).
#   ydotool + wl-clipboard ARE bundled inside /opt/talktype, so they are not declared.
#
# Requires: fpm (gem install --user-install fpm) and ar/tar (binutils/coreutils).
# Builds fine on a non-Debian host (Fedora/Nobara) — no dpkg-deb needed.

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# fpm is commonly installed to ~/bin or the user gem bin dir — make sure it's found.
export PATH="$HOME/bin:$PATH"
if ! command -v fpm >/dev/null 2>&1; then
    echo "❌ fpm not found. Install it with:  gem install --user-install fpm"
    exit 1
fi

# Version comes from pyproject.toml (single source of truth, same as build-release.sh).
VERSION=$(grep -E "^version = " "$PROJECT_DIR/pyproject.toml" | sed 's/version = "\(.*\)"/\1/')
if [ -z "$VERSION" ]; then
    echo "❌ Could not read version from pyproject.toml"
    exit 1
fi
APPIMAGE="$PROJECT_DIR/TalkType-v${VERSION}-x86_64.AppImage"
if [ ! -f "$APPIMAGE" ]; then
    echo "❌ AppImage not found: $APPIMAGE"
    echo "   Run ./build-release.sh first to produce it."
    exit 1
fi

echo "📦 Building TalkType .deb from $(basename "$APPIMAGE")"
echo "========================================"

# Work in a temp dir so nothing litters the project tree.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "📂 Extracting the AppImage..."
( cd "$WORK" && "$APPIMAGE" --appimage-extract >/dev/null 2>&1 )
TREE="$WORK/squashfs-root"
[ -d "$TREE" ] || { echo "❌ extraction failed"; exit 1; }

echo "🏗️  Staging the .deb filesystem..."
STAGE="$WORK/stage"
mkdir -p "$STAGE/opt" "$STAGE/usr/bin" "$STAGE/usr/share/applications" "$STAGE/usr/share/pixmaps"

# The whole tree goes to /opt/talktype. AppRun sits at /opt/talktype/AppRun and derives
# its paths relative to itself (${HERE}/usr/...), so it works unchanged at this location.
mv "$TREE" "$STAGE/opt/talktype"

# System launcher — reuses the tested AppRun rather than duplicating its env setup.
cat > "$STAGE/usr/bin/talktype" <<'LAUNCHER'
#!/bin/sh
# TalkType system launcher — hands off to the bundled AppRun, which sets
# PYTHONHOME/PYTHONPATH/LD_LIBRARY_PATH/GI_TYPELIB_PATH relative to itself.
exec /opt/talktype/AppRun "$@"
LAUNCHER
chmod +x "$STAGE/usr/bin/talktype"

# Desktop entry — same as the AppImage's, but Exec points at the system launcher.
sed 's/^Exec=.*/Exec=talktype tray/' "$PROJECT_DIR/io.github.ronb1964.TalkType.desktop" \
    > "$STAGE/usr/share/applications/io.github.ronb1964.TalkType.desktop"
cp "$PROJECT_DIR/io.github.ronb1964.TalkType.png" "$STAGE/usr/share/pixmaps/"
# Crisp scalable icon in the hicolor theme — used by the app menu AND the first-run
# splash screen (which prefers SVG). Without it, a packaged install has no icon the
# splash can find and shows plain "TalkType" text instead of the glowing logo.
install -Dm644 "$PROJECT_DIR/icons/OFFICIAL_ICON_DO_NOT_CHANGE.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg"

# Post-install: refresh the icon + desktop caches (best-effort, never fail the install).
POSTINST="$WORK/postinst.sh"
cat > "$POSTINST" <<'POST'
#!/bin/sh
set -e
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications 2>/dev/null || true
exit 0
POST

# Normalize permissions so nothing installs unreadable. A stray owner-only file
# (a 0600 .py) would otherwise land as root:root 0600 and break imports for the user
# — update_checker.py did exactly this, killing Preferences/About/Check-for-Updates.
# a+rX = readable everywhere; execute preserved only where already set (launchers, python).
chmod -R a+rX "$STAGE"

echo "🔧 Packaging with fpm..."
rm -f "$PROJECT_DIR/talktype_${VERSION}_amd64.deb"
fpm -s dir -t deb \
    -n talktype \
    -v "$VERSION" \
    --architecture amd64 \
    --maintainer "Ron Brand <ronb1964@gmail.com>" \
    --url "https://github.com/ronb1964/TalkType" \
    --description "TalkType — AI-powered offline speech-to-text dictation for Linux.
 Hold a hotkey, speak, and your words are typed into any application. Runs fully
 offline using faster-whisper; optional NVIDIA GPU acceleration." \
    --license "MIT" \
    --category "sound" \
    --depends "libgtk-3-0" \
    --depends "libayatana-appindicator3-1" \
    --depends "libportaudio2" \
    --after-install "$POSTINST" \
    --deb-no-default-config-files \
    -C "$STAGE" \
    -p "$PROJECT_DIR/talktype_${VERSION}_amd64.deb" \
    opt usr

echo ""
echo "📦 .deb Details:"
ls -lh "$PROJECT_DIR/talktype_${VERSION}_amd64.deb"

# Add this .deb to SHA256SUMS.txt so the in-app updater can verify the download
# before installing it with pkexec. build-release.sh created the file first, so
# we append here (dropping any stale entry from a previous build). fail-closed:
# the updater aborts a package download whose hash is missing from this file.
DEB_BASENAME="talktype_${VERSION}_amd64.deb"
if [ -f "$PROJECT_DIR/SHA256SUMS.txt" ]; then
    grep -v " ${DEB_BASENAME}\$" "$PROJECT_DIR/SHA256SUMS.txt" \
        > "$PROJECT_DIR/SHA256SUMS.txt.tmp" 2>/dev/null || true
    mv "$PROJECT_DIR/SHA256SUMS.txt.tmp" "$PROJECT_DIR/SHA256SUMS.txt"
fi
( cd "$PROJECT_DIR" && sha256sum "$DEB_BASENAME" >> SHA256SUMS.txt )
echo "🔐 Added ${DEB_BASENAME} to SHA256SUMS.txt"

echo ""
echo "🚀 To test on Debian/Ubuntu:  sudo apt install ./talktype_${VERSION}_amd64.deb"
