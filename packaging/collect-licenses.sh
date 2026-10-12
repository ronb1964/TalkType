#!/bin/bash
# Put the license of everything TuxTalk bundles into the AppImage.
#
# Runs INSIDE the Ubuntu 22.04 build container, from container-build.sh, after
# every file has been copied into AppDir. The .deb and .rpm repackage the
# AppImage's tree, so they carry these too (under /opt/tuxtalk).
#
#   packaging/collect-licenses.sh <AppDir> <ydotool source> <wl-clipboard source>
#
# What it writes, under <AppDir>/usr/share/licenses/:
#   tuxtalk/LICENSE, tuxtalk/THIRD_PARTY_LICENSES.md  - ours, and the overview
#   ydotool/, wl-clipboard/                             - built from source here
#   ctranslate2/, tokenizers/                           - their wheels ship no license
#   <ubuntu package>/copyright                          - every library copied from Ubuntu
#   tuxtalk/bundled-ubuntu-packages.txt                - those packages and exact versions
#
# It FAILS the build if a license can't be found, so a notice can never be
# dropped silently. tests/test_third_party_licenses.py checks the wiring.

set -euo pipefail

APPDIR="$1"
YDOTOOL_SRC="$2"
WLCLIP_SRC="$3"
LIC="$APPDIR/usr/share/licenses"
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(dirname "$HERE")"

mkdir -p "$LIC/tuxtalk" "$LIC/ydotool" "$LIC/wl-clipboard" "$LIC/ctranslate2" "$LIC/tokenizers"
cp "$PROJECT/LICENSE" "$PROJECT/THIRD_PARTY_LICENSES.md" "$LIC/tuxtalk/"
cp "$YDOTOOL_SRC/LICENSE" "$LIC/ydotool/LICENSE"
cp "$WLCLIP_SRC/COPYING" "$LIC/wl-clipboard/COPYING"
cp "$HERE/licenses/ctranslate2-LICENSE" "$LIC/ctranslate2/LICENSE"
cp "$HERE/licenses/tokenizers-LICENSE" "$LIC/tokenizers/LICENSE"

# --- Libraries copied from Ubuntu: find each one's package --------------------
# The system file each bundled file came from. Libraries and typelibs are
# found by name, so a library added to the build later is covered too.
SYSTEM_FILES=()
for f in "$APPDIR"/usr/lib/*.so* "$APPDIR"/usr/lib/portaudio/*.so*; do
    SYSTEM_FILES+=("/usr/lib/x86_64-linux-gnu/$(basename "$f")")
done
for f in "$APPDIR"/usr/lib/girepository-1.0/*.typelib; do
    name=$(basename "$f")
    for dir in /usr/lib/x86_64-linux-gnu/girepository-1.0 /usr/lib/girepository-1.0; do
        [ -e "$dir/$name" ] && SYSTEM_FILES+=("$dir/$name") && break
    done
done
# Python itself and the bindings copied from Ubuntu (gi, cairo, dbus).
PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
SYSTEM_FILES+=("/usr/bin/python$PYVER" "/usr/lib/python$PYVER/os.py")
for mod in gi cairo dbus; do
    SYSTEM_FILES+=("$(python3 -c "import $mod; print($mod.__file__)")")
done

# dpkg records some files under /lib and others under /usr/lib, so try both.
package_of() {
    local path="$1" real out
    real=$(readlink -f "$path")
    for p in "$path" "$real" "${path#/usr}" "${real#/usr}"; do
        # dpkg prints "package:arch: path"; keep the package name.
        out=$(dpkg -S "$p" 2>/dev/null | head -1) || continue
        [ -n "$out" ] && { echo "${out%%:*}"; return 0; }
    done
    return 1
}

declare -A PACKAGES=()
for f in "${SYSTEM_FILES[@]}"; do
    pkg=$(package_of "$f") || { echo "❌ No Ubuntu package found for $f: its license would be missing"; exit 1; }
    PACKAGES[$pkg]=1
done

LIST="$LIC/tuxtalk/bundled-ubuntu-packages.txt"
{
    echo "Libraries TuxTalk copies unmodified from Ubuntu 22.04, with exact versions."
    echo "Each package's copyright file is in the folder of the same name next to"
    echo "this one. Source: apt-get source <package> on Ubuntu 22.04, or"
    echo "https://launchpad.net/ubuntu/jammy/+source/<source package>"
    echo
} > "$LIST"
for pkg in $(printf '%s\n' "${!PACKAGES[@]}" | sort); do
    copyright="/usr/share/doc/$pkg/copyright"
    [ -f "$copyright" ] || { echo "❌ $pkg has no $copyright"; exit 1; }
    mkdir -p "$LIC/$pkg"
    cp "$copyright" "$LIC/$pkg/copyright"
    dpkg-query -W -f='${Package} ${Version} (source: ${source:Package})\n' "$pkg" >> "$LIST"
done

chmod -R a+rX "$LIC"
echo "   ✅ Licenses: TuxTalk, ydotool, wl-clipboard, ctranslate2, tokenizers + ${#PACKAGES[@]} Ubuntu packages"
