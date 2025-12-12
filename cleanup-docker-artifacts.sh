#!/bin/bash
# Cleanup Docker Build Artifacts
# These files were created by Docker container with root ownership

echo "🧹 Cleaning up Docker build artifacts (requires sudo)..."
echo ""
echo "The following will be removed:"
echo "  - .venv/ (broken Python 3.10 venv from Docker)"
echo "  - AppDir/ (2.3GB build artifact)"
echo "  - squashfs-root/ (old extracted AppImage)"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo rm -rf .venv AppDir squashfs-root appimagetool-extracted
    echo "✅ Cleanup complete!"
else
    echo "❌ Cleanup cancelled"
fi
