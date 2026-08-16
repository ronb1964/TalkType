#!/bin/bash
# Step A of the Flatpak GPU spike — build + run a THROWAWAY Flatpak that asks the
# NVIDIA driver, from inside the sandbox, "are you there?" via ctypes/libcuda.
# No flatpak-builder, no bundled deps — the runtime already ships python3.
#
#   ./build_gpu_probe_flatpak.sh          # try --device=dri  (minimal)
#   ./build_gpu_probe_flatpak.sh all      # retry --device=all (exposes /dev/nvidia*)
#
# Disposable: uninstall with
#   flatpak uninstall --user -y io.github.ronb1964.TalkTypeGpuProbe
#   flatpak remote-delete --user tt-gpu
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD=/tmp/tt-gpu-build
REPO=/tmp/tt-gpu-repo
APPID=io.github.ronb1964.TalkTypeGpuProbe
RUNTIME=org.gnome.Platform
BRANCH=48
DEVICE="${1:-dri}"   # 'dri' (minimal) or 'all' (needed if CUDA can't see /dev/nvidia*)

rm -rf "$BUILD"
flatpak build-init "$BUILD" "$APPID" "$RUNTIME" "$RUNTIME" "$BRANCH"

mkdir -p "$BUILD/files/bin"
cp "$HERE/gpu_probe.py" "$BUILD/files/bin/"
cat > "$BUILD/files/bin/tt-gpu-probe" <<'EOF'
#!/bin/sh
exec python3 /app/bin/gpu_probe.py "$@"
EOF
chmod +x "$BUILD/files/bin/tt-gpu-probe"

# --device grants GPU access; the NVIDIA GL extension (libcuda.so) auto-mounts.
flatpak build-finish "$BUILD" --device="$DEVICE" --command=tt-gpu-probe
flatpak build-export "$REPO" "$BUILD"
flatpak remote-add --user --no-gpg-verify --if-not-exists tt-gpu "$REPO"
flatpak install --user -y --or-update tt-gpu "$APPID" >/dev/null

echo "===== running GPU probe (--device=$DEVICE) ====="
flatpak run --user "$APPID"
