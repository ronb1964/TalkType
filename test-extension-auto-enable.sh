#!/bin/bash
# Test script to verify GNOME extension auto-enables after installation

set -e

EXTENSION_UUID="talktype@ronb1964.github.io"

echo "=========================================="
echo "Testing GNOME Extension Auto-Enable"
echo "=========================================="
echo

# Step 1: Check if extension is currently enabled
echo "Step 1: Checking current extension status..."
if gnome-extensions info "$EXTENSION_UUID" 2>/dev/null | grep -q "State: ACTIVE"; then
    echo "✅ Extension is currently ACTIVE"
    CURRENT_STATE="enabled"
else
    echo "❌ Extension is currently NOT active"
    CURRENT_STATE="disabled"
fi
echo

# Step 2: Check if extension is in gsettings enabled-extensions list
echo "Step 2: Checking gsettings enabled-extensions list..."
if gsettings get org.gnome.shell enabled-extensions | grep -q "$EXTENSION_UUID"; then
    echo "✅ Extension IS in enabled-extensions list (will persist after logout)"
else
    echo "❌ Extension NOT in enabled-extensions list (will NOT persist after logout)"
fi
echo

# Step 3: Simulate uninstall and reinstall
echo "Step 3: Testing reinstallation with auto-enable..."
cd ~/Dropbox/projects/TalkType

# Disable first
echo "  - Disabling extension..."
gnome-extensions disable "$EXTENSION_UUID" 2>/dev/null || true

# Verify it's disabled
if gsettings get org.gnome.shell enabled-extensions | grep -q "$EXTENSION_UUID"; then
    echo "  ❌ Extension still in enabled list after disable!"
else
    echo "  ✅ Extension removed from enabled list"
fi

# Reinstall with auto-enable
echo "  - Reinstalling extension with auto-enable..."
.venv/bin/python -c "from src.talktype import extension_helper; extension_helper.install_extension_from_local('gnome-extension/talktype@ronb1964.github.io', auto_enable=True)"

# Verify it's enabled again
echo
echo "Step 4: Verifying extension is auto-enabled..."
if gsettings get org.gnome.shell enabled-extensions | grep -q "$EXTENSION_UUID"; then
    echo "✅ SUCCESS! Extension is in enabled-extensions list"
    echo "   This means it WILL persist after logout/login"
else
    echo "❌ FAILURE! Extension NOT in enabled-extensions list"
    exit 1
fi

if gnome-extensions info "$EXTENSION_UUID" 2>/dev/null | grep -q "Enabled: Yes"; then
    echo "✅ Extension is marked as Enabled"
else
    echo "⚠️  Extension not marked as enabled (may need logout/login to activate)"
fi

echo
echo "=========================================="
echo "✅ Test PASSED!"
echo "=========================================="
echo
echo "Summary:"
echo "  • Extension auto-enables after installation ✅"
echo "  • Extension persists in gsettings ✅"
echo "  • Extension will remain enabled after logout/login ✅"
echo
