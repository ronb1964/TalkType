#!/bin/bash
# Package GNOME Extension for GitHub Release
#
# Creates talktype-gnome-extension.zip from the source extension directory
# This zip is downloaded by the welcome dialog during first-run setup

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTENSION_DIR="$SCRIPT_DIR/gnome-extension/talktype@ronb1964.github.io"
OUTPUT_ZIP="$SCRIPT_DIR/talktype-gnome-extension.zip"

echo "📦 Packaging GNOME Extension..."
echo "================================"

# Verify source directory exists
if [ ! -d "$EXTENSION_DIR" ]; then
    echo "❌ Error: Extension source directory not found: $EXTENSION_DIR"
    exit 1
fi

# Verify required files exist
REQUIRED_FILES=("extension.js" "metadata.json")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$EXTENSION_DIR/$file" ]; then
        echo "❌ Error: Required file not found: $file"
        exit 1
    fi
done

echo "✅ Source directory verified: $EXTENSION_DIR"
echo ""
echo "📄 Files to package:"
ls -lh "$EXTENSION_DIR"
echo ""

# Remove old zip if it exists
if [ -f "$OUTPUT_ZIP" ]; then
    echo "🗑️  Removing old zip file..."
    rm "$OUTPUT_ZIP"
fi

# Create the zip file
# The zip must contain the UUID directory as the root
echo "📦 Creating zip file..."
cd "$SCRIPT_DIR/gnome-extension"

# Remove any existing zip in this directory
rm -f talktype-gnome-extension.zip talktype@ronb1964.github.io.zip

# Create fresh zip
zip -r talktype-gnome-extension.zip talktype@ronb1964.github.io \
    -x "*.git*" \
    -x "*~" \
    -x "*.swp"

# Move to project root
mv talktype-gnome-extension.zip "$OUTPUT_ZIP"

# Verify the zip was created
if [ ! -f "$OUTPUT_ZIP" ]; then
    echo "❌ Error: Failed to create zip file"
    exit 1
fi

# Refresh the extension's entry in SHA256SUMS.txt so the checksums file
# published with the release always matches the freshly-packaged zip.
cd "$SCRIPT_DIR"
if [ -f "SHA256SUMS.txt" ]; then
    grep -v "talktype-gnome-extension.zip" SHA256SUMS.txt > SHA256SUMS.txt.tmp || true
    mv SHA256SUMS.txt.tmp SHA256SUMS.txt
fi
sha256sum "talktype-gnome-extension.zip" >> SHA256SUMS.txt
echo "🔐 Updated SHA256SUMS.txt entry for the extension zip"

# Show zip contents
echo ""
echo "✅ Extension packaged successfully!"
echo "📦 Output: $OUTPUT_ZIP"
echo "📊 Size: $(du -h "$OUTPUT_ZIP" | cut -f1)"
echo ""
echo "📋 Zip contents:"
unzip -l "$OUTPUT_ZIP"
echo ""
echo "✅ Done!"
echo ""
echo "📤 Next steps:"
echo "   1. Test the extension locally:"
echo "      unzip -l $OUTPUT_ZIP"
echo ""
echo "   2. Upload to GitHub release:"
echo "      gh release upload vX.X.X $OUTPUT_ZIP --clobber"
echo ""
echo "   3. Verify download URL:"
echo "      https://github.com/ronb1964/TalkType/releases/latest/download/talktype-gnome-extension.zip"
