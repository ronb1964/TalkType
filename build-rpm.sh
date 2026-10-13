#!/bin/bash
# TuxTalk .rpm Build Script
# ==========================
# Repackages the release AppImage into a Fedora/RHEL/openSUSE .rpm.
#
# Same approach as build-deb.sh: the AppImage already bundles a self-contained
# runtime (its own Python, GTK bindings, faster-whisper/CTranslate2, ydotool,
# wl-clipboard) built on Ubuntu 22.04 for wide glibc compatibility. We extract that
# finished tree and wrap it as an .rpm rather than maintaining a second build.
# Run ./build-release.sh FIRST.
#
# Layout produced (identical to the .deb):
#   /opt/talktype/            <- the whole extracted AppImage tree (AppRun + usr/)
#   /usr/bin/tuxtalk         <- tiny launcher: exec /opt/talktype/AppRun "$@"
#   /usr/share/applications/  <- desktop entry (Exec=tuxtalk tray)
#   /usr/share/icons/hicolor/scalable/apps/  <- crisp SVG icon
#   /usr/share/pixmaps/       <- PNG icon fallback
#
# System deps are DECLARED (the bundle relies on the host's GTK stack). Fedora names:
#   gtk3, libayatana-appindicator-gtk3 (tray), portaudio (mic).
#   ydotool + wl-clipboard ARE bundled inside /opt/talktype, so they are not declared.
#
# Requires: fpm (gem install --user-install fpm) and rpmbuild (rpm-build package).

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

export PATH="$HOME/bin:$PATH"
if ! command -v fpm >/dev/null 2>&1; then
    echo "❌ fpm not found. Install it with:  gem install --user-install fpm"
    exit 1
fi
if ! command -v rpmbuild >/dev/null 2>&1; then
    echo "❌ rpmbuild not found. Install it with:  sudo dnf install rpm-build"
    exit 1
fi

VERSION=$(grep -E "^version = " "$PROJECT_DIR/pyproject.toml" | sed 's/version = "\(.*\)"/\1/')
if [ -z "$VERSION" ]; then
    echo "❌ Could not read version from pyproject.toml"
    exit 1
fi
APPIMAGE="$PROJECT_DIR/TuxTalk-v${VERSION}-x86_64.AppImage"
if [ ! -f "$APPIMAGE" ]; then
    echo "❌ AppImage not found: $APPIMAGE"
    echo "   Run ./build-release.sh first to produce it."
    exit 1
fi

echo "📦 Building TuxTalk .rpm from $(basename "$APPIMAGE")"
echo "========================================"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "📂 Extracting the AppImage..."
( cd "$WORK" && "$APPIMAGE" --appimage-extract >/dev/null 2>&1 )
TREE="$WORK/squashfs-root"
[ -d "$TREE" ] || { echo "❌ extraction failed"; exit 1; }

echo "🏗️  Staging the .rpm filesystem..."
STAGE="$WORK/stage"
mkdir -p "$STAGE/opt" "$STAGE/usr/bin" "$STAGE/usr/share/applications" "$STAGE/usr/share/pixmaps"

# Whole tree -> /opt/talktype. AppRun sits at /opt/talktype/AppRun and derives its
# paths relative to itself, so it works unchanged at this location.
# The folder keeps its name from before the 0.15.0 rename (nobody sees it):
# upgrades then replace files in place, like every earlier one, instead of
# deleting the folder a running 0.14.x tray still imports from.
mv "$TREE" "$STAGE/opt/talktype"

# Third-party licenses ride inside the AppImage's tree (packaging/collect-licenses.sh).
# Refuse to package an AppImage built without them.
LIC_SRC="$STAGE/opt/talktype/usr/share/licenses"
for f in tuxtalk/LICENSE tuxtalk/THIRD_PARTY_LICENSES.md ydotool/LICENSE wl-clipboard/COPYING; do
    [ -f "$LIC_SRC/$f" ] || { echo "❌ The AppImage has no $f: rebuild it with ./build-release.sh"; exit 1; }
done
# Fedora keeps a package's license in /usr/share/licenses/<package>/.
mkdir -p "$STAGE/usr/share/licenses/tuxtalk"
cp "$LIC_SRC/tuxtalk/LICENSE" "$LIC_SRC/tuxtalk/THIRD_PARTY_LICENSES.md" \
    "$STAGE/usr/share/licenses/tuxtalk/"

cat > "$STAGE/usr/bin/tuxtalk" <<'LAUNCHER'
#!/bin/sh
# TuxTalk system launcher — hands off to the bundled AppRun, which sets
# PYTHONHOME/PYTHONPATH/LD_LIBRARY_PATH/GI_TYPELIB_PATH relative to itself.
exec /opt/talktype/AppRun "$@"
LAUNCHER
chmod +x "$STAGE/usr/bin/tuxtalk"
# The command before the 0.15.0 rename: old shortcuts, scripts and a 0.14.x
# updater (which restarts /usr/bin/talktype after installing this) still use it.
ln -s tuxtalk "$STAGE/usr/bin/talktype"

sed 's/^Exec=.*/Exec=tuxtalk tray/' "$PROJECT_DIR/io.github.ronb1964.TuxTalk.desktop" \
    > "$STAGE/usr/share/applications/io.github.ronb1964.TuxTalk.desktop"
cp "$PROJECT_DIR/io.github.ronb1964.TuxTalk.png" "$STAGE/usr/share/pixmaps/"
install -Dm644 "$PROJECT_DIR/icons/OFFICIAL_ICON_DO_NOT_CHANGE.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/io.github.ronb1964.TuxTalk.svg"

# Normalize permissions so nothing installs unreadable (same guard as the .deb).
chmod -R a+rX "$STAGE"

POSTINST="$WORK/postinst.sh"
cat > "$POSTINST" <<'POST'
#!/bin/sh
set -e
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications 2>/dev/null || true
exit 0
POST

echo "🔧 Packaging with fpm..."
rm -f "$PROJECT_DIR"/tuxtalk-"${VERSION}"-*.rpm "$PROJECT_DIR"/tuxtalk-"${VERSION}".*.rpm
fpm -s dir -t rpm \
    -n tuxtalk \
    -v "$VERSION" \
    --architecture x86_64 \
    --maintainer "Ron Brand <ronb1964@gmail.com>" \
    --url "https://github.com/ronb1964/TuxTalk" \
    --description "TuxTalk (formerly TalkType) — voice dictation for Linux.
Hold a hotkey, speak, and your words are typed into any application. Runs fully
offline, on the processor or an NVIDIA, AMD or Intel graphics card." \
    --license "MIT" \
    --category "Applications/Multimedia" \
    --depends "gtk3" \
    --depends "libayatana-appindicator-gtk3" \
    --depends "portaudio" \
    --after-install "$POSTINST" \
    --replaces "talktype < 0.15.0" \
    --conflicts "talktype < 0.15.0" \
    --provides "talktype" \
    -C "$STAGE" \
    -p "$PROJECT_DIR/tuxtalk-${VERSION}-1.x86_64.rpm" \
    opt usr

echo ""
echo "📦 .rpm Details:"
ls -lh "$PROJECT_DIR"/tuxtalk-"${VERSION}"-1.x86_64.rpm

# Add this .rpm to SHA256SUMS.txt so the in-app updater can verify the download
# before installing it with pkexec. build-release.sh created the file first, so
# we append here (dropping any stale entry from a previous build). fail-closed:
# the updater aborts a package download whose hash is missing from this file.
RPM_BASENAME="tuxtalk-${VERSION}-1.x86_64.rpm"
# shellcheck source=packaging/checksums.sh
source "$PROJECT_DIR/packaging/checksums.sh"
replace_checksums "$PROJECT_DIR" "$RPM_BASENAME"
echo "🔐 Added ${RPM_BASENAME} to SHA256SUMS.txt"

echo ""
echo "🚀 To test on Fedora:  sudo dnf install ./tuxtalk-${VERSION}-1.x86_64.rpm"
