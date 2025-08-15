#!/bin/bash

# TalkType AppImage Build Script
# This creates a portable AppImage of TalkType

set -e

echo "🚀 Building TalkType AppImage..."

# Clean up any previous builds
rm -rf AppDir TalkType-*.AppImage

# Create AppDir structure
mkdir -p AppDir/usr/{bin,lib,share/{applications,icons/hicolor/scalable/apps}}

echo "📦 Installing Python dependencies..."

# Create a virtual environment in AppDir
python3 -m venv AppDir/usr
source AppDir/usr/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install pyperclip toml evdev sounddevice numpy pygobject faster-whisper

# Install TalkType
pip install .

# Deactivate venv
deactivate

# Copy Python standard library to ensure encodings module is available
echo "📚 Copying Python standard library..."
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_STDLIB="/usr/lib64/python${PYTHON_VERSION}"

if [ -d "$PYTHON_STDLIB" ]; then
    mkdir -p "AppDir/usr/lib64/python${PYTHON_VERSION}"
    cp -r "$PYTHON_STDLIB"/* "AppDir/usr/lib64/python${PYTHON_VERSION}/"
    echo "✅ Copied Python ${PYTHON_VERSION} standard library"
else
    echo "⚠️  Warning: Python standard library not found at $PYTHON_STDLIB"
fi

echo "📋 Copying application files..."

# Copy our custom AppRun script
cp AppRun AppDir/

# Copy desktop file and icon
cp TalkType.desktop AppDir/
cp io.github.ronb1964.TalkType.svg AppDir/

# Copy TalkType source for direct execution
mkdir -p AppDir/usr/src
cp -r src/ AppDir/usr/src/

echo "🔗 Setting up AppImage structure..."

# Make AppRun executable
chmod +x AppDir/AppRun

# Create symlinks for AppImage convention
cd AppDir
ln -sf TalkType.desktop talktype.desktop
ln -sf io.github.ronb1964.TalkType.svg talktype.svg
ln -sf io.github.ronb1964.TalkType.svg .DirIcon
cd ..

echo "🏗️ Building AppImage..."

# Create the AppImage
ARCH=x86_64 ./appimagetool AppDir TalkType-x86_64.AppImage

if [ $? -eq 0 ]; then
    echo "✅ AppImage created successfully: TalkType-x86_64.AppImage"
    echo "📏 Size: $(du -h TalkType-x86_64.AppImage | cut -f1)"
    echo ""
    echo "🧪 To test the AppImage:"
    echo "./TalkType-x86_64.AppImage --help"
    echo ""
    echo "🚀 To run TalkType:"
    echo "./TalkType-x86_64.AppImage"
else
    echo "❌ AppImage creation failed"
    exit 1
fi
