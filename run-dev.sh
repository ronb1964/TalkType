#!/bin/bash
# TalkType Development Runner
# Uses venv for Python packages but system PyGObject

cd "$(dirname "$0")"

# Enable dev mode to show both GTK and extension trays
export DEV_MODE=1

# Set PYTHONPATH to find talktype module AND system PyGObject
export PYTHONPATH="./src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages"

# Run with venv Python
exec .venv/bin/python -m talktype.tray "$@"
