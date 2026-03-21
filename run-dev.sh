#!/bin/bash
# TalkType Development Runner
# Uses venv for Python packages but system PyGObject

cd "$(dirname "$0")"

# Enable dev mode to show both GTK and extension trays
export DEV_MODE=1

# Force X11 backend (via XWayland) to enable window positioning
# Native Wayland doesn't allow apps to position their own windows
export GDK_BACKEND=x11

# Set PYTHONPATH to find talktype module AND system PyGObject
export PYTHONPATH="./src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages"

# Set LD_LIBRARY_PATH so ctranslate2/faster-whisper can find cuDNN libs bundled
# in the venv. Without this, CUDA falls back to CPU when launched from desktop/autostart.
export LD_LIBRARY_PATH=".venv/lib64/python3.14/site-packages/ctranslate2.libs:.venv/lib/python3.14/site-packages/nvidia/cudnn/lib"

# Run with venv Python
exec .venv/bin/python -m talktype.tray "$@"
