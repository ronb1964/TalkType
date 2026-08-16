#!/bin/bash
# Build + install the TalkType Flatpak with flatpak-builder (run as the
# org.flatpak.Builder flatpak so no system package is needed).
#
#   ./packaging/flatpak/build-flatpak.sh            # build + install --user
#   ./packaging/flatpak/build-flatpak.sh bundle     # also emit a .flatpak bundle
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
MANIFEST="$HERE/io.github.ronb1964.TalkType.yml"
BUILDDIR="$ROOT/.flatpak-build"
STATE="$ROOT/.flatpak-builder"
REPO="$ROOT/.flatpak-repo"
APPID=io.github.ronb1964.TalkType

# --filesystem=host so the builder can read the repo sources + write build dirs;
# --share=network for source downloads and the pip module.
flatpak run --filesystem=host --share=network org.flatpak.Builder \
    --user --force-clean --install --install-deps-from=flathub \
    --state-dir="$STATE" --repo="$REPO" \
    "$BUILDDIR" "$MANIFEST"

echo "installed $APPID (--user)"

if [ "$1" = "bundle" ]; then
    OUT="$ROOT/TalkType-flatpak-$(cat "$ROOT/VERSION" 2>/dev/null || echo dev).flatpak"
    flatpak build-bundle "$REPO" "$OUT" "$APPID"
    echo "wrote bundle: $OUT"
fi
