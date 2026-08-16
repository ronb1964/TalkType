#!/bin/bash
# Build + install the THROWAWAY portal-spike Flatpak (no flatpak-builder needed).
# Proves the portal typing + hotkey inside a real sandbox. Disposable.
#
#   ./build_spike_flatpak.sh            # build + (re)install
#   flatpak run --user --env=PYTHONUNBUFFERED=1 --command=python3 \
#       io.github.ronb1964.TalkType /app/bin/hotkey_portal.py     # hotkey test
#   flatpak run --user io.github.ronb1964.TalkType                # typing test (default)
#
# Runtime org.gnome.Platform//48 already ships python3 + PyGObject + Gio typelib
# + libei.so, so the spike scripts run unmodified — nothing extra to bundle.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD=/tmp/tt-flatpak-build
REPO=/tmp/tt-spike-repo
APPID=io.github.ronb1964.TalkType
RUNTIME=org.gnome.Platform
BRANCH=48

rm -rf "$BUILD"
flatpak build-init "$BUILD" "$APPID" "$RUNTIME" "$RUNTIME" "$BRANCH"

mkdir -p "$BUILD/files/bin"
cp "$HERE/_portal_common.py" "$HERE/hotkey_portal.py" "$HERE/type_portal.py" "$BUILD/files/bin/"
cat > "$BUILD/files/bin/tt-spike" <<'EOF'
#!/bin/sh
exec python3 /app/bin/type_portal.py "$@"
EOF
chmod +x "$BUILD/files/bin/tt-spike"

# Portals need NO special device perms; the portal proxy is allowed by default.
flatpak build-finish "$BUILD" \
    --socket=wayland --socket=fallback-x11 --share=ipc \
    --talk-name=org.freedesktop.portal.Desktop \
    --command=tt-spike

flatpak build-export "$REPO" "$BUILD"
flatpak remote-add --user --no-gpg-verify --if-not-exists tt-spike "$REPO"
flatpak install --user -y --or-update tt-spike "$APPID"
echo "installed $APPID (throwaway). See the run commands at the top of this script."
