#!/bin/bash
# Build TalkType's AMD / Intel graphics engine: whisper.cpp's whisper-server
# with the Vulkan backend (Vulkan also runs on NVIDIA). whisper.cpp publishes
# no Linux Vulkan build of its own, so TalkType builds one and hosts it as a
# GitHub PRE-release (never "latest", so the in-app updater and the AppImage's
# update information never mistake it for a TalkType version). TalkType
# downloads it only when someone picks "AMD / Intel graphics" as the device.
#
# Built in Ubuntu 22.04 like the AppImage, so it runs on 22.04 and newer
# (glibc 2.34). 22.04 has no glslc, so the build uses the LunarG Vulkan SDK,
# cached in ~/.cache/talktype-vulkan-sdk.
#
# It also builds whisper.cpp's Parakeet library (libparakeet.so), which
# parakeet_gpu_worker.py loads to run Parakeet on the graphics chip.
#
# Usage: ./build-vulkan-engine.sh <whisper.cpp version> [build number]
# The build number is for rebuilding the SAME whisper.cpp version with
# different contents. Never re-upload a changed tarball under an old name:
# released TalkType versions check its SHA256 and would refuse it.
#
# Output: talktype-whisper-vulkan-<version>[-b<build>]-x64.tar.gz and its
# .sha256. The folder inside is always talktype-whisper-vulkan-<version>, so
# a later build unpacks over an earlier one. Afterwards put the version, build
# and SHA256 into src/talktype/whisper_vulkan.py.
set -e
WHISPER_CPP_VERSION="${1:-1.9.4}"
ENGINE_BUILD="${2:-1}"
if [ "$ENGINE_BUILD" = "1" ]; then
    ASSET="talktype-whisper-vulkan-${WHISPER_CPP_VERSION}-x64.tar.gz"
else
    ASSET="talktype-whisper-vulkan-${WHISPER_CPP_VERSION}-b${ENGINE_BUILD}-x64.tar.gz"
fi
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SDK_CACHE="$HOME/.cache/talktype-vulkan-sdk"
mkdir -p "$SDK_CACHE"
CONTAINER_CMD=$(command -v podman || command -v docker)
# Rootless podman already writes files as you. Docker writes them as root, so
# the container hands them back to your user; under podman that same chown
# would map to a sub-UID and leave files you can't delete.
OWNER_ARGS=()
case "$CONTAINER_CMD" in
    *docker) OWNER_ARGS=(-e BUILD_USER="$(id -u)" -e BUILD_GROUP="$(id -g)") ;;
esac

$CONTAINER_CMD run --rm \
    -v "$PROJECT_DIR:/build:Z" \
    -v "$SDK_CACHE:/cache:Z" \
    -e WHISPER_CPP_VERSION="$WHISPER_CPP_VERSION" -e ASSET="$ASSET" \
    "${OWNER_ARGS[@]}" \
    ubuntu:22.04 bash /build/vulkan-engine-container.sh

ls -lh "$PROJECT_DIR/$ASSET"*
cat "$PROJECT_DIR/$ASSET.sha256"
