#!/bin/bash
# Step B of the Flatpak GPU spike — real Whisper transcription on the GPU inside a
# throwaway Flatpak. Builds against org.gnome.Sdk//48 to pip faster-whisper for the
# runtime's Python 3.12, mounts the host's downloaded CUDA libs + HF model cache at
# run time (read-only), and transcribes a bundled 16 kHz clip on device=cuda.
#
#   ./build_gpu_transcribe_flatpak.sh
#
# Disposable:
#   flatpak uninstall --user -y io.github.ronb1964.TalkTypeGpuXcribe
#   flatpak remote-delete --user tt-gpu-xcribe
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD=/tmp/tt-gpu-xcribe-build
REPO=/tmp/tt-gpu-xcribe-repo
APPID=io.github.ronb1964.TalkTypeGpuXcribe
CUDA_HOST="$HOME/.local/share/TalkType/cuda/lib"
HF_HOST="$HOME/.cache/huggingface"

command -v flatpak >/dev/null || { echo "flatpak not found"; exit 1; }
flatpak info org.gnome.Sdk//48 >/dev/null 2>&1 || {
    echo "org.gnome.Sdk//48 required — install it first"; exit 1; }
[ -f "$HERE/test.wav" ] || { echo "missing test.wav (generate it first)"; exit 1; }
[ -d "$CUDA_HOST" ] || { echo "missing host CUDA libs at $CUDA_HOST"; exit 1; }

rm -rf "$BUILD"
# SDK as the build sdk so pip3 + a matching python3.12 are available in `flatpak build`.
flatpak build-init "$BUILD" "$APPID" org.gnome.Sdk org.gnome.Platform 48

echo "===== pip install faster-whisper into /app (Python 3.12) ====="
flatpak build --share=network "$BUILD" \
    pip3 install --prefix=/app --no-warn-script-location faster-whisper

mkdir -p "$BUILD/files/bin" "$BUILD/files/share"
cp "$HERE/transcribe_probe.py" "$BUILD/files/bin/"
cp "$HERE/test.wav" "$BUILD/files/share/"

# Launcher: put the bundled site-packages + the mounted CUDA libs on the paths,
# point HF at the mounted cache (read-only, local-only), then run the probe.
cat > "$BUILD/files/bin/tt-gpu-xcribe" <<EOF
#!/bin/sh
export PYTHONPATH=/app/lib/python3.12/site-packages:\$PYTHONPATH
export LD_LIBRARY_PATH=$CUDA_HOST/cudnn/lib:$CUDA_HOST/cublas/lib:$CUDA_HOST/cuda_runtime/lib:\$LD_LIBRARY_PATH
export HF_HOME=$HF_HOST
exec python3 /app/bin/transcribe_probe.py "\$@"
EOF
chmod +x "$BUILD/files/bin/tt-gpu-xcribe"

# Runtime needs GPU (dri) but NO network — model + libs are local.
flatpak build-finish "$BUILD" --device=dri --command=tt-gpu-xcribe
flatpak build-export "$REPO" "$BUILD"
flatpak remote-add --user --no-gpg-verify --if-not-exists tt-gpu-xcribe "$REPO"
flatpak install --user -y --or-update tt-gpu-xcribe "$APPID" >/dev/null

echo "===== running GPU transcription probe ====="
# Mount the host CUDA libs + HF cache read-only into the sandbox.
flatpak run --user \
    --filesystem="$HOME/.local/share/TalkType/cuda:ro" \
    --filesystem="$HF_HOST:ro" \
    "$APPID"
