#!/bin/bash
# Runs INSIDE the Ubuntu 22.04 container; called by build-vulkan-engine.sh.
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq build-essential cmake git wget xz-utils libvulkan-dev ca-certificates >/dev/null

# Vulkan SDK for glslc and current Vulkan headers (22.04 has neither).
cd /cache
if [ ! -d sdk ]; then
    wget -q -O sdk.tar.xz "https://sdk.lunarg.com/sdk/download/latest/linux/vulkan-sdk.tar.xz"
    mkdir sdk && tar xf sdk.tar.xz -C sdk && rm sdk.tar.xz
fi
export VULKAN_SDK="/cache/sdk/$(ls /cache/sdk | head -1)/x86_64"
export PATH="$VULKAN_SDK/bin:$PATH"

WORK=/tmp/whisper-build
rm -rf "$WORK" && mkdir -p "$WORK" && cd "$WORK"
git clone -q --depth 1 --branch "v${WHISPER_CPP_VERSION}" https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
# GGML_BACKEND_DL + GGML_CPU_ALL_VARIANTS: the CPU part is chosen at run time
# for the user's processor, like the official builds, so one download fits all.
cmake -B build -DGGML_VULKAN=ON -DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON \
      -DGGML_CPU_ALL_VARIANTS=ON -DWHISPER_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build build -j"$(nproc)" --target whisper-server whisper-cli >/dev/null

NAME="talktype-whisper-vulkan-${WHISPER_CPP_VERSION}"
OUT="$WORK/$NAME"
mkdir -p "$OUT"
cp -a build/bin/whisper-server build/bin/whisper-cli "$OUT/"
cp -a build/bin/*.so* "$OUT/" 2>/dev/null || true
cp -a build/src/*.so* build/ggml/src/*.so* "$OUT/" 2>/dev/null || true
strip --strip-unneeded "$OUT"/whisper-* "$OUT"/*.so* 2>/dev/null || true
cp LICENSE "$OUT/LICENSE-whisper.cpp"
# A short public-domain sample (JFK, 1961) for TalkType's speed check.
cp samples/jfk.wav "$OUT/speed-check.wav"

# Refuse to publish a build that can't do what it's for.
test -f "$OUT/libggml-vulkan.so" || { echo "❌ no Vulkan backend in the build"; exit 1; }
MAXGLIBC=$(objdump -T "$OUT"/whisper-server "$OUT"/*.so* 2>/dev/null | grep -oE "GLIBC_[0-9.]+" | sort -Vu | tail -1)
echo "Newest glibc needed: $MAXGLIBC"

cd "$WORK"
TARBALL="$NAME-x64.tar.gz"
tar czf "/build/$TARBALL" "$NAME"
cd /build && sha256sum "$TARBALL" > "$TARBALL.sha256"
chown "$BUILD_USER:$BUILD_GROUP" "/build/$TARBALL" "/build/$TARBALL.sha256" 2>/dev/null || true
echo "✅ Built $TARBALL"
