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
# Output: talktype-whisper-vulkan-<version>-x64.tar.gz and its .sha256.
# Afterwards put the version and SHA256 into src/talktype/whisper_vulkan.py.
set -e
WHISPER_CPP_VERSION="${1:-1.9.4}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SDK_CACHE="$HOME/.cache/talktype-vulkan-sdk"
mkdir -p "$SDK_CACHE"
CONTAINER_CMD=$(command -v podman || command -v docker)

$CONTAINER_CMD run --rm \
    -v "$PROJECT_DIR:/build:Z" \
    -v "$SDK_CACHE:/cache:Z" \
    -e WHISPER_CPP_VERSION="$WHISPER_CPP_VERSION" \
    -e BUILD_USER="$(id -u)" -e BUILD_GROUP="$(id -g)" \
    ubuntu:22.04 bash /build/vulkan-engine-container.sh

ls -lh "$PROJECT_DIR"/talktype-whisper-vulkan-"$WHISPER_CPP_VERSION"-x64.tar.gz*
cat "$PROJECT_DIR"/talktype-whisper-vulkan-"$WHISPER_CPP_VERSION"-x64.tar.gz.sha256
